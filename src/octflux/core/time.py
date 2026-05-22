"""Datetime helpers. octflux stores datetimes as naive UTC everywhere (see
schema/tables.py) -- this is the single place that convention is implemented."""

from __future__ import annotations

from datetime import UTC, datetime


def now_naive() -> datetime:
    """Current time as naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(value: object) -> object:
    """Aware datetime -> UTC -> drop tzinfo; non-datetimes/naive pass through."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string (e.g. an Octopus API timestamp)."""
    return datetime.fromisoformat(value) if value else None
