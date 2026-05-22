"""Read recently collected rows of a dataset (from the first SQL sink)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..core.engine import Engine
from ..schema.datasets import DATASETS
from .deps import get_engine

router = APIRouter(prefix="/data", tags=["data"])


@router.get("")
async def datasets() -> dict:
    return {"datasets": sorted(DATASETS)}


@router.get("/{dataset}")
async def data(dataset: str, limit: int = 50, engine: Engine = Depends(get_engine)) -> dict:
    try:
        rows = await engine.query(dataset, limit)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown dataset {dataset!r}") from None
    if rows is None:
        raise HTTPException(status_code=503, detail="no SQL sink configured to query")
    return {"dataset": dataset, "count": len(rows), "rows": rows}
