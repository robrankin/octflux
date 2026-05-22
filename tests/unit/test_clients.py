"""REST + GraphQL client behaviour via httpx.MockTransport (no network)."""

from __future__ import annotations

import httpx
import pytest

from octflux.clients.base import GraphQlError
from octflux.clients.graphql import GraphQlClient
from octflux.clients.rest import RestClient
from octflux.config.schema import OctopusSettings


def _settings(**kw):
    return OctopusSettings(api_key="k", account_number="A-1", **kw)


def _rest(handler, **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RestClient(_settings(), client=client, base_backoff=0, **kw)


async def test_rest_paginates_following_next():
    base = "https://api.octopus.energy/v1"
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.params.get("page") == "2":
            return httpx.Response(200, json={"results": [{"v": 3}], "next": None})
        return httpx.Response(200, json={"results": [{"v": 1}, {"v": 2}], "next": f"{base}/x/?page=2"})
    rows = await _rest(handler).get_unit_rates(product_code="P", tariff_code="T")
    assert [r["v"] for r in rows] == [1, 2, 3]


async def test_rest_retries_5xx_then_succeeds():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"results": [{"ok": 1}]})
    rows = await _rest(handler, max_retries=4).get_unit_rates(product_code="P", tariff_code="T")
    assert rows == [{"ok": 1}] and calls["n"] == 3


async def test_rest_does_not_retry_4xx():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(404)
    with pytest.raises(httpx.HTTPStatusError):
        await _rest(handler).get_account()
    assert calls["n"] == 1  # 4xx is not retried


async def test_rest_consumption_url_and_period_params():
    seen = {}
    def handler(req):
        seen["path"] = req.url.path
        seen["params"] = dict(req.url.params)
        return httpx.Response(200, json={"results": []})
    from datetime import UTC, datetime
    await _rest(handler).get_consumption(
        fuel="gas", identifier="G99", serial_number="G4F",
        period_from=datetime(2026, 5, 1, tzinfo=UTC), period_to=datetime(2026, 5, 2, tzinfo=UTC),
    )
    assert seen["path"] == "/v1/gas-meter-points/G99/meters/G4F/consumption/"
    assert seen["params"]["period_from"].startswith("2026-05-01")
    assert seen["params"]["order_by"] == "period"


# -- GraphQL --

def _graphql(handler):
    return GraphQlClient(_settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_graphql_obtains_token_then_authorises():
    seen = []
    def handler(req):
        import json as _json
        body = _json.loads(req.content)
        seen.append((body["query"], dict(req.headers)))
        if "obtainKrakenToken" in body["query"]:
            return httpx.Response(200, json={"data": {"obtainKrakenToken": {"token": "TK"}}})
        return httpx.Response(200, json={"data": {"hello": "world"}})
    out = await _graphql(handler).execute("query { hello }")
    assert out == {"hello": "world"}
    # first call obtains the token (no auth), second carries it
    assert "obtainKrakenToken" in seen[0][0]
    assert seen[1][1]["authorization"] == "TK"


async def test_graphql_refreshes_token_once_on_error():
    state = {"queries": 0, "tokens": 0}
    def handler(req):
        import json as _json
        q = _json.loads(req.content)["query"]
        if "obtainKrakenToken" in q:
            state["tokens"] += 1
            return httpx.Response(200, json={"data": {"obtainKrakenToken": {"token": f"T{state['tokens']}"}}})
        state["queries"] += 1
        if state["queries"] == 1:
            return httpx.Response(200, json={"errors": [{"message": "KT-CT-1139: expired"}]})
        return httpx.Response(200, json={"data": {"ok": True}})
    out = await _graphql(handler).execute("query { ok }")
    assert out == {"ok": True}
    assert state["tokens"] == 2 and state["queries"] == 2  # obtained, failed, re-obtained, retried


async def test_graphql_raises_when_error_persists():
    def handler(req):
        import json as _json
        if "obtainKrakenToken" in _json.loads(req.content)["query"]:
            return httpx.Response(200, json={"data": {"obtainKrakenToken": {"token": "T"}}})
        return httpx.Response(200, json={"errors": [{"message": "boom"}]})
    with pytest.raises(GraphQlError):
        await _graphql(handler).execute("query { ok }")
