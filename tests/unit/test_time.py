from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from freezegun import freeze_time

from octflux.core.time import now_naive, parse_dt, to_naive_utc


def test_now_naive_is_naive_utc():
    with freeze_time("2026-05-22 07:30:00"):
        n = now_naive()
    assert n.tzinfo is None
    assert n == datetime(2026, 5, 22, 7, 30, 0)


def test_to_naive_utc_converts_aware_to_utc():
    aware = datetime(2026, 5, 22, 8, 0, tzinfo=timezone(timedelta(hours=1)))  # +01:00
    out = to_naive_utc(aware)
    assert out == datetime(2026, 5, 22, 7, 0)  # shifted to UTC
    assert out.tzinfo is None


def test_to_naive_utc_passthrough():
    naive = datetime(2026, 5, 22, 7, 0)
    assert to_naive_utc(naive) is naive       # already naive -> unchanged
    assert to_naive_utc("not-a-date") == "not-a-date"
    assert to_naive_utc(None) is None


def test_parse_dt():
    assert parse_dt(None) is None
    assert parse_dt("") is None
    assert parse_dt("2026-05-01T00:00:00Z") == datetime(2026, 5, 1, tzinfo=UTC)
