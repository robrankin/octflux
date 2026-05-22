"""The collection engine: schedule collectors, resolve the account once, fan
each produced batch out to every enabled sink, and track status."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..account import resolve_account
from ..clients.graphql import GraphQlClient
from ..clients.rest import RestClient
from ..collectors import build_collector
from ..config.schema import Config
from ..sinks import build_sink
from .protocols import CollectContext, Collector, Sink

log = structlog.get_logger(__name__)


def make_trigger(schedule: str):
    s = schedule.strip()
    if s.endswith("s") and s[:-1].isdigit():
        return IntervalTrigger(seconds=int(s[:-1]))
    if s.isdigit():
        return IntervalTrigger(seconds=int(s))
    return CronTrigger.from_crontab(s)


@dataclass
class CollectorRuntime:
    name: str
    driver: str
    collector: Collector
    schedule: str
    options: dict
    runs: int = 0
    last_run: datetime | None = None
    last_ok: bool | None = None
    last_error: str | None = None
    last_summary: dict = field(default_factory=dict)

    def status(self, next_run: datetime | None) -> dict:
        return {
            "name": self.name, "driver": self.driver, "schedule": self.schedule,
            "datasets": list(self.collector.datasets), "runs": self.runs,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_ok": self.last_ok, "last_error": self.last_error,
            "last_summary": self.last_summary,
            "next_run": next_run.isoformat() if next_run else None,
        }


class Engine:
    def __init__(self, config: Config, *, account_ttl_seconds: int = 600):
        self.config = config
        self.sinks: list[Sink] = []
        self.collectors: dict[str, CollectorRuntime] = {}
        self.started_at: datetime | None = None
        self._rest: RestClient | None = None
        self._graphql: GraphQlClient | None = None
        self._scheduler = AsyncIOScheduler()
        self._account = None
        self._account_at: datetime | None = None
        self._account_ttl = timedelta(seconds=account_ttl_seconds)
        self._lock = asyncio.Lock()

    # -- lifecycle ------------------------------------------------------------
    async def start(self, *, schedule: bool = True, run_initial: bool = True) -> None:
        # Clients may be pre-set (tests inject fakes); otherwise build the real ones.
        self._rest = self._rest or RestClient(self.config.octopus)
        self._graphql = self._graphql or GraphQlClient(self.config.octopus)

        for name, cfg in self.config.sinks.items():
            if not cfg.enabled:
                continue
            sink = build_sink(name, cfg.driver or name, cfg.options)
            await sink.start()
            self.sinks.append(sink)
            log.info("sink_started", sink=name, driver=cfg.driver or name)

        for name, cfg in self.config.collectors.items():
            if not cfg.enabled:
                continue
            driver = cfg.driver or name
            rt = CollectorRuntime(name, driver, build_collector(driver, cfg.options),
                                  cfg.schedule, cfg.options)
            self.collectors[name] = rt
            if schedule:
                self._scheduler.add_job(
                    self.run_collector, make_trigger(cfg.schedule), args=[name],
                    id=name, name=name, max_instances=1, coalesce=True,
                )
                log.info("collector_scheduled", collector=name, driver=driver, schedule=cfg.schedule)

        if schedule and self.config.medallion.enabled and self._sql_sink() is not None:
            self._scheduler.add_job(
                self.refresh_medallion, make_trigger(self.config.medallion.schedule),
                id="medallion", name="medallion", max_instances=1, coalesce=True,
            )
            log.info("medallion_scheduled", schedule=self.config.medallion.schedule)

        if schedule:
            self._scheduler.start()
        self.started_at = datetime.now(UTC)
        log.info("engine_started", sinks=len(self.sinks), collectors=len(self.collectors))
        if schedule and run_initial:
            asyncio.create_task(self._initial_run())

    async def _initial_run(self) -> None:
        for name in list(self.collectors):
            await self.run_collector(name)
        await self.refresh_medallion()

    async def refresh_medallion(self) -> dict:
        """Rebuild the silver fact_cost on every SQL sink (gold caggs refresh via
        their own Timescale policies)."""
        if not self.config.medallion.enabled:
            return {}
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(run_id=uuid.uuid4().hex[:8], task="medallion")
        out: dict = {}
        try:
            for sink in self.sinks:
                if hasattr(sink, "refresh_silver"):
                    rows = await sink.refresh_silver(self.config.medallion.window_days)
                    out[sink.name] = rows
                    log.info("silver_refreshed", sink=sink.name, fact_cost_rows=rows)
        except Exception:
            log.error("medallion_refresh_failed", exc_info=True)
        finally:
            structlog.contextvars.clear_contextvars()
        return out

    async def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        for sink in self.sinks:
            try:
                await sink.close()
            except Exception:  # pragma: no cover
                log.error("sink_close_failed", exc_info=True)
        for client in (self._rest, self._graphql):
            if client is not None:
                await client.aclose()

    # -- account caching ------------------------------------------------------
    async def _account_for(self, now: datetime):
        async with self._lock:
            if self._account is None or self._account_at is None or (
                now - self._account_at
            ) > self._account_ttl:
                self._account = await resolve_account(self._rest, self._graphql, self.config.octopus)
                self._account_at = now
            return self._account

    # -- running --------------------------------------------------------------
    async def run_collector(self, name: str) -> dict:
        rt = self.collectors[name]
        run_id = uuid.uuid4().hex[:8]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(run_id=run_id, collector=name)
        now = datetime.now(UTC)
        rt.last_run = now
        rt.runs += 1
        try:
            account = await self._account_for(now)
            ctx = CollectContext(self._rest, self._graphql, self.config.octopus, now, account, rt.options)
            batches = await rt.collector.collect(ctx)
            summary: dict = {}
            for batch in batches:
                ds = summary.setdefault(batch.spec.name, {"records": 0, "sinks": {}})
                ds["records"] += len(batch)
                for sink in self.sinks:
                    res = await sink.write(batch)
                    agg = ds["sinks"].setdefault(sink.name, {})
                    for k, v in res.as_log().items():
                        agg[k] = agg.get(k, 0) + v
            rt.last_ok = True
            rt.last_error = None
            rt.last_summary = summary
            log.info("collector_ok", summary=summary)
            return summary
        except Exception as exc:
            rt.last_ok = False
            rt.last_error = f"{type(exc).__name__}: {exc}"
            log.error("collector_failed", exc_info=True)
            raise
        finally:
            structlog.contextvars.clear_contextvars()

    # -- introspection for the control surface --------------------------------
    def _next_run(self, name: str) -> datetime | None:
        job = self._scheduler.get_job(name)
        return getattr(job, "next_run_time", None) if job else None

    def status(self) -> dict:
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "sinks": [s.name for s in self.sinks],
            "collectors": [rt.status(self._next_run(n)) for n, rt in self.collectors.items()],
        }

    def _sql_sink(self):
        return next((s for s in self.sinks if hasattr(s, "recent")), None)

    async def query(self, dataset: str, limit: int = 50) -> list[dict] | None:
        from ..schema.datasets import DATASETS

        if dataset not in DATASETS:
            raise KeyError(dataset)
        sink = self._sql_sink()
        return None if sink is None else await sink.recent(DATASETS[dataset], limit)
