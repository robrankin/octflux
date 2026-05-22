"""The narrow seams between the engine and its pluggable drivers.

A *collector* turns the Octopus API into batches of records; a *sink* writes a
batch somewhere. The engine knows only these Protocols; concrete drivers are
chosen at runtime from config via the registries in ``collectors`` / ``sinks``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..clients.base import GraphQlApi, RestApi
    from ..config.schema import OctopusSettings
    from ..schema.datasets import DatasetSpec
    from .models import Account


@dataclass(frozen=True)
class Batch:
    """Records of one dataset produced by a collector run."""

    spec: "DatasetSpec"
    records: list

    def __len__(self) -> int:
        return len(self.records)


@dataclass
class WriteResult:
    """Per-sink outcome of writing a batch. Sinks fill the fields they support."""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    published: int = 0

    def as_log(self) -> dict:
        return {k: v for k, v in vars(self).items() if v}


@dataclass
class CollectContext:
    """What a collector is handed for one run. The account is resolved once by
    the engine and shared, so collectors never re-fetch it."""

    rest: "RestApi"
    graphql: "GraphQlApi"
    settings: "OctopusSettings"
    now: datetime
    account: "Account"
    options: dict = field(default_factory=dict)


@runtime_checkable
class Collector(Protocol):
    name: str
    datasets: tuple[str, ...]

    async def collect(self, ctx: CollectContext) -> list[Batch]: ...


@runtime_checkable
class Sink(Protocol):
    name: str

    async def start(self) -> None: ...
    async def write(self, batch: Batch) -> WriteResult: ...
    async def close(self) -> None: ...
