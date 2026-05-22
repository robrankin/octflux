"""FastAPI dependencies: hand routes the running Engine from app.state."""

from __future__ import annotations

from fastapi import Request

from ..core.engine import Engine


def get_engine(request: Request) -> Engine:
    return request.app.state.engine
