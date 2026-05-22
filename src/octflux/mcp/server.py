"""MCP server exposing the same control/query surface as the REST API.

Built with FastMCP and served over streamable HTTP, mounted into the FastAPI app
so one container offers both REST and MCP. Tools read the running engine, which
the app's lifespan injects via ``set_engine``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..core.engine import Engine
from ..core.logging import ring_handler

_engine: Engine | None = None


def set_engine(engine: Engine) -> None:
    global _engine  # noqa: PLW0603
    _engine = engine


def _require() -> Engine:
    if _engine is None:  # pragma: no cover
        raise RuntimeError("engine not started")
    return _engine


def build_mcp() -> FastMCP:
    mcp = FastMCP("octflux", stateless_http=True, streamable_http_path="/")

    @mcp.tool()
    async def status() -> dict:
        """Engine status: started time, configured sinks, and every collector's
        schedule, last run, last result and next run."""
        return _require().status()

    @mcp.tool()
    async def run_collector(name: str) -> dict:
        """Run a named collector once, immediately, and return what it wrote."""
        engine = _require()
        if name not in engine.collectors:
            return {"ok": False, "error": f"unknown collector {name!r}"}
        try:
            return {"ok": True, "collector": name, "summary": await engine.run_collector(name)}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @mcp.tool()
    async def recent_data(dataset: str, limit: int = 20) -> dict:
        """Most recently collected rows of a dataset from the SQL sink."""
        try:
            rows = await _require().query(dataset, limit)
        except KeyError:
            return {"ok": False, "error": f"unknown dataset {dataset!r}"}
        return {"ok": True, "dataset": dataset, "rows": rows}

    @mcp.tool()
    async def recent_logs(n: int = 50) -> list[dict]:
        """The last N log lines from the in-memory ring buffer."""
        return ring_handler.recent(n)

    return mcp
