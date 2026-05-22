"""In-memory fake Octopus clients for hermetic tests."""

from __future__ import annotations


class FakeRest:
    def __init__(self, *, account=None, unit_rates=None, standing=None, consumption=None):
        self._account = account or {"number": "A-TEST", "properties": []}
        self._unit_rates = unit_rates or []
        self._standing = standing or []
        self._consumption = consumption or []

    async def get_account(self):
        return self._account

    async def get_unit_rates(self, **kw):
        return self._unit_rates

    async def get_standing_charges(self, **kw):
        return self._standing

    async def get_consumption(self, **kw):
        return self._consumption

    async def aclose(self):
        pass


class FakeGraphQl:
    """Routes by a marker in the query text -> a canned data dict."""

    def __init__(self, responses: dict[str, dict] | None = None):
        self._responses = responses or {}

    async def execute(self, query: str, variables=None):
        for marker, data in self._responses.items():
            if marker in query:
                return data
        raise KeyError(f"no fake response for query: {query[:40]!r}")

    async def aclose(self):
        pass
