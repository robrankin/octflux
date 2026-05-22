from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fakes.clients import FakeGraphQl, FakeRest

from octflux.config.schema import Config, OctopusSettings
from octflux.core.engine import CollectorRuntime, Engine, make_trigger

ACCT = {"number": "A-1", "properties": []}


def _cfg():
    return Config(octopus=OctopusSettings(api_key="k", account_number="A-1"))


class CountingRest(FakeRest):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls = 0

    async def get_account(self):
        self.calls += 1
        return await super().get_account()


def test_make_trigger_interval_and_cron():
    assert isinstance(make_trigger("30s"), IntervalTrigger)
    assert isinstance(make_trigger("45"), IntervalTrigger)
    assert isinstance(make_trigger("0 * * * *"), CronTrigger)


@pytest.mark.integration
async def test_account_cache_respects_ttl():
    e = Engine(_cfg(), account_ttl_seconds=100)
    e._rest = CountingRest(account=ACCT)
    e._graphql = FakeGraphQl({})
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    await e._account_for(t0)
    await e._account_for(t0 + timedelta(seconds=50))     # within TTL -> cached
    assert e._rest.calls == 1
    await e._account_for(t0 + timedelta(seconds=200))    # past TTL -> re-resolved
    assert e._rest.calls == 2


@pytest.mark.integration
async def test_run_collector_records_failure_and_reraises():
    e = Engine(_cfg())
    e._rest, e._graphql = FakeRest(account=ACCT), FakeGraphQl({})

    class Boom:
        name, datasets = "boom", ()
        async def collect(self, ctx):
            raise RuntimeError("kaboom")

    e.collectors["boom"] = CollectorRuntime("boom", "boom", Boom(), "3600s", {})
    with pytest.raises(RuntimeError):
        await e.run_collector("boom")
    rt = e.collectors["boom"]
    assert rt.last_ok is False and "kaboom" in rt.last_error and rt.runs == 1


@pytest.mark.integration
async def test_status_shape():
    e = Engine(_cfg())
    e._rest, e._graphql = FakeRest(account=ACCT), FakeGraphQl({})

    class Noop:
        name, datasets = "x", ()
        async def collect(self, ctx):
            return []

    e.collectors["x"] = CollectorRuntime("x", "x", Noop(), "3600s", {})
    s = e.status()
    assert {"started_at", "sinks", "collectors"} <= s.keys()
    assert s["collectors"][0]["name"] == "x"
