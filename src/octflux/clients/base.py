"""Client protocols + the GraphQL error type. The only HTTP lives in this package."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

JsonDict = dict[str, Any]


class GraphQlError(RuntimeError):
    def __init__(self, errors: list[JsonDict]):
        self.errors = errors
        super().__init__("; ".join(e.get("message", str(e)) for e in errors))


@runtime_checkable
class RestApi(Protocol):
    async def get_account(self) -> JsonDict: ...
    async def get_unit_rates(
        self, *, product_code: str, tariff_code: str,
        period_from: datetime | None = None, period_to: datetime | None = None,
    ) -> list[JsonDict]: ...
    async def get_standing_charges(
        self, *, product_code: str, tariff_code: str, fuel: str = "electricity",
        period_from: datetime | None = None, period_to: datetime | None = None,
    ) -> list[JsonDict]: ...
    async def get_consumption(
        self, *, fuel: str, identifier: str, serial_number: str,
        period_from: datetime | None = None, period_to: datetime | None = None,
    ) -> list[JsonDict]: ...


@runtime_checkable
class GraphQlApi(Protocol):
    async def execute(self, query: str, variables: JsonDict | None = None) -> JsonDict: ...
