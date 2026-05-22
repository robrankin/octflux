from __future__ import annotations

import logging

import structlog

from octflux.core.logging import RingBufferHandler, configure_logging, ring_handler


def _rec(msg: str) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)


def test_ring_buffer_is_bounded():
    h = RingBufferHandler(capacity=3)
    for i in range(6):
        h.emit(_rec(f"m{i}"))
    assert len(h.records) == 3                       # oldest dropped
    assert [r["message"] for r in h.records] == ["m3", "m4", "m5"]


def test_recent_returns_tail():
    h = RingBufferHandler(capacity=10)
    for i in range(5):
        h.emit(_rec(f"m{i}"))
    assert [r["message"] for r in h.recent(2)] == ["m3", "m4"]
    assert {"ts", "level", "message"} <= h.recent(1)[0].keys()


def test_configure_logging_routes_into_ring_buffer():
    configure_logging("INFO", "json")
    structlog.get_logger("octflux.test").info("hello_event", foo="bar")
    assert any("hello_event" in r["message"] for r in ring_handler.recent(20))
