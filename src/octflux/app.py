"""CLI entry point / composition root.

  octflux --config config.yaml            # run the service (scheduler + API + MCP)
  octflux --config config.yaml --once consumption   # run one collector and exit
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal

from .config.loader import load_config
from .core.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="octflux", description="Octopus Energy collector service")
    p.add_argument("--config", "-c", required=True, help="path to config.yaml")
    p.add_argument("--once", metavar="COLLECTOR", help="run one collector once, then exit")
    p.add_argument("--log-level", help="override logging.level")
    p.add_argument("--log-format", choices=["console", "json"], help="override logging.format")
    return p


async def _run(config, args) -> None:
    from .core.engine import Engine

    if args.once:
        engine = Engine(config)
        await engine.start(schedule=False, run_initial=False)
        try:
            await engine.run_collector(args.once)
        finally:
            await engine.stop()
        return

    if config.api.enabled:
        import uvicorn

        from .api.app import build_app

        server = uvicorn.Server(
            uvicorn.Config(build_app(config), host=config.api.host, port=config.api.port,
                           log_config=None)
        )
        await server.serve()
        return

    engine = Engine(config)
    await engine.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    await engine.stop()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    configure_logging(args.log_level or config.logging.level, args.log_format or config.logging.format)
    asyncio.run(_run(config, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
