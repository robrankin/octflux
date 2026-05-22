"""Async REST client for the public Octopus Energy API (HTTP + retry + paging)."""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
import structlog

from ..config.schema import OctopusSettings
from .base import JsonDict

log = structlog.get_logger(__name__)


class RestClient:
    def __init__(
        self,
        settings: OctopusSettings,
        *,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 4,
        base_backoff: float = 0.5,
    ):
        self._base = settings.rest_base_url.rstrip("/")
        self._acct = settings.account_number
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._owns = client is None
        self._http = client or httpx.AsyncClient(auth=(settings.api_key, ""), timeout=30.0)

    async def __aenter__(self) -> "RestClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns:
            await self._http.aclose()

    def _url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"

    @staticmethod
    def _period(params: JsonDict, pf: datetime | None, pt: datetime | None) -> JsonDict:
        if pf is not None:
            params["period_from"] = pf.isoformat()
        if pt is not None:
            params["period_to"] = pt.isoformat()
        return params

    async def _get(self, url: str, params: JsonDict | None = None) -> JsonDict:
        delay = self._base_backoff
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._http.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                retryable = isinstance(exc, httpx.TransportError) or (
                    isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
                )
                if not retryable or attempt == self._max_retries:
                    raise
                log.warning("http_get_retry", url=url, attempt=attempt, error=str(exc))
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")  # pragma: no cover

    async def _paginate(self, url: str, params: JsonDict | None = None) -> list[JsonDict]:
        page = await self._get(url, params=params)
        out = list(page.get("results", []))
        nxt = page.get("next")
        while nxt:
            page = await self._get(nxt)
            out.extend(page.get("results", []))
            nxt = page.get("next")
        return out

    async def get_account(self) -> JsonDict:
        return await self._get(self._url(f"accounts/{self._acct}/"))

    async def get_unit_rates(self, *, product_code, tariff_code, period_from=None, period_to=None):
        path = f"products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/"
        return await self._paginate(self._url(path), self._period({}, period_from, period_to))

    async def get_standing_charges(
        self, *, product_code, tariff_code, fuel="electricity", period_from=None, period_to=None
    ):
        path = f"products/{product_code}/{fuel}-tariffs/{tariff_code}/standing-charges/"
        return await self._paginate(self._url(path), self._period({}, period_from, period_to))

    async def get_consumption(
        self, *, fuel, identifier, serial_number, period_from=None, period_to=None
    ):
        seg = "electricity-meter-points" if fuel == "electricity" else "gas-meter-points"
        path = f"{seg}/{identifier}/meters/{serial_number}/consumption/"
        params = self._period({"page_size": 25000, "order_by": "period"}, period_from, period_to)
        return await self._paginate(self._url(path), params)
