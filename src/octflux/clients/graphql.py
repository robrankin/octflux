"""Async client for the Octopus (Kraken) GraphQL API.

Exchanges the API key for a short-lived Kraken token, then sends it in the
Authorization header; refreshes once on a failure.
"""

from __future__ import annotations

import httpx
import structlog

from ..config.schema import OctopusSettings
from .base import GraphQlError, JsonDict

log = structlog.get_logger(__name__)

_OBTAIN_TOKEN = """
mutation ObtainToken($apiKey: String!) {
  obtainKrakenToken(input: {APIKey: $apiKey}) { token }
}
"""


class GraphQlClient:
    def __init__(self, settings: OctopusSettings, *, client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._url = settings.graphql_url
        self._owns = client is None
        self._http = client or httpx.AsyncClient(timeout=30.0)
        self._token: str | None = None

    async def __aenter__(self) -> "GraphQlClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns:
            await self._http.aclose()

    async def _post(self, query: str, variables: JsonDict, headers: JsonDict) -> JsonDict:
        resp = await self._http.post(
            self._url, json={"query": query, "variables": variables}, headers=headers
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            raise GraphQlError(body["errors"])
        return body["data"]

    async def _obtain_token(self) -> str:
        data = await self._post(_OBTAIN_TOKEN, {"apiKey": self._settings.api_key}, {})
        self._token = data["obtainKrakenToken"]["token"]
        return self._token

    async def execute(self, query: str, variables: JsonDict | None = None) -> JsonDict:
        if self._token is None:
            await self._obtain_token()
        try:
            return await self._post(query, variables or {}, {"Authorization": self._token or ""})
        except GraphQlError:
            log.info("kraken_token_refresh")
            await self._obtain_token()
            return await self._post(query, variables or {}, {"Authorization": self._token or ""})
