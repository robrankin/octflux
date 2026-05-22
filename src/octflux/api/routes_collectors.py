"""List collectors and trigger an on-demand run."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..core.engine import Engine
from .deps import get_engine

router = APIRouter(prefix="/collectors", tags=["collectors"])


@router.get("")
async def list_collectors(engine: Engine = Depends(get_engine)) -> list[dict]:
    return engine.status()["collectors"]


@router.post("/{name}/run")
async def run_collector(name: str, engine: Engine = Depends(get_engine)) -> dict:
    if name not in engine.collectors:
        raise HTTPException(status_code=404, detail=f"unknown collector {name!r}")
    try:
        summary = await engine.run_collector(name)
        return {"collector": name, "ok": True, "summary": summary}
    except Exception as exc:
        return {"collector": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
