"""Status / health / recent-logs endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.engine import Engine
from ..core.logging import ring_handler
from .deps import get_engine

router = APIRouter(tags=["status"])


@router.get("/health")
async def health() -> dict:
    return {"ok": True}


@router.get("/status")
async def status(engine: Engine = Depends(get_engine)) -> dict:
    return engine.status()


@router.get("/logs")
async def logs(n: int = 100) -> dict:
    return {"logs": ring_handler.recent(n)}
