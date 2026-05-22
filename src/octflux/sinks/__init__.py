"""Sink registry: driver name -> builder(name, options) -> Sink."""

from __future__ import annotations

from collections.abc import Callable

from ..core.protocols import Sink
from . import mqtt, postgres, sqlite

SinkBuilder = Callable[[str, dict], Sink]

SINK_BUILDERS: dict[str, SinkBuilder] = {
    "sqlite": sqlite.build,
    "postgres": postgres.build,
    "mqtt": mqtt.build,
}


def build_sink(name: str, driver: str, options: dict) -> Sink:
    try:
        builder = SINK_BUILDERS[driver]
    except KeyError:
        raise ValueError(f"unknown sink driver {driver!r}; known: {sorted(SINK_BUILDERS)}") from None
    return builder(name, options)
