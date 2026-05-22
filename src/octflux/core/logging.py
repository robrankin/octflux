"""structlog logging + an in-memory ring buffer the control surface exposes.

Console or JSON rendering; third-party stdlib logs (httpx, sqlalchemy, apscheduler)
are routed through the same formatter and quieted. The ring buffer keeps the last
N rendered lines so the API/MCP can return "recent logs" without a log file.
"""

from __future__ import annotations

import logging
import logging.config
from collections import deque

import structlog


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 500):
        super().__init__()
        self.records: deque[dict] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover
            message = record.getMessage()
        self.records.append(
            {"ts": record.created, "level": record.levelname, "message": message}
        )

    def recent(self, n: int = 100) -> list[dict]:
        return list(self.records)[-n:]


ring_handler = RingBufferHandler()


def _renderer(fmt: str):
    return structlog.processors.JSONRenderer() if fmt == "json" else structlog.dev.ConsoleRenderer()


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    ts = "iso" if fmt == "json" else "%H:%M:%S"
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt=ts),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(lvl),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    pre_chain = [structlog.stdlib.add_log_level, structlog.processors.TimeStamper(fmt=ts)]
    ring_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.KeyValueRenderer(key_order=["timestamp", "level", "event"]),
            foreign_pre_chain=pre_chain,
        )
    )
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": _renderer(fmt),
                    "foreign_pre_chain": pre_chain,
                }
            },
            "handlers": {
                "stderr": {"class": "logging.StreamHandler", "formatter": "default",
                           "stream": "ext://sys.stderr"},
            },
            "root": {"handlers": ["stderr"], "level": lvl},
            "loggers": {
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
                "apscheduler": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "WARNING"},
                "aiosqlite": {"level": "WARNING"},
            },
        }
    )
    root = logging.getLogger()
    if ring_handler not in root.handlers:
        root.addHandler(ring_handler)
