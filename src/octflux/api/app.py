"""FastAPI application factory.

Versioned ``/api/v1`` control surface (status, collectors, data). The engine is
created and started in the lifespan and shared via ``app.state.engine``. When MCP
is enabled, its streamable-HTTP app is mounted and its session manager runs inside
the same lifespan, so one process serves both REST and MCP.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from ..config.schema import Config
from ..core.engine import Engine
from .routes_collectors import router as collectors_router
from .routes_data import router as data_router
from .routes_status import router as status_router

_DESCRIPTION = "octflux control surface. /api/v1 is the canonical REST API; MCP is at the mount path."


def build_app(config: Config) -> FastAPI:
    mcp_obj = None
    mcp_app = None
    if config.mcp.enabled:
        from ..mcp import server as mcp_server

        mcp_obj = mcp_server.build_mcp()
        mcp_app = mcp_obj.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = Engine(config)
        await engine.start()
        app.state.engine = engine
        try:
            if mcp_obj is not None:
                from ..mcp import server as mcp_server

                mcp_server.set_engine(engine)
                async with mcp_obj.session_manager.run():
                    yield
            else:
                yield
        finally:
            await engine.stop()

    app = FastAPI(
        title="octflux",
        version="1.0.0",
        description=_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(collectors_router, prefix="/api/v1")
    app.include_router(data_router, prefix="/api/v1")

    if mcp_app is not None:
        app.mount(config.mcp.mount_path, mcp_app)

    return app
