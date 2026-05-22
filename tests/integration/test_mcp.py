from __future__ import annotations

import pytest

from octflux.mcp import server as mcp_server


class FakeEngine:
    collectors = {"consumption": object()}

    def status(self):
        return {"started_at": "t0", "sinks": ["local"], "collectors": [{"name": "consumption"}]}

    async def run_collector(self, name):
        return {"consumption": {"records": 3}}

    async def query(self, dataset, limit):
        if dataset == "nope":
            raise KeyError(dataset)
        return [{"x": 1}]


@pytest.fixture
def mcp():
    m = mcp_server.build_mcp()
    mcp_server.set_engine(FakeEngine())
    return m


@pytest.mark.integration
async def test_mcp_status(mcp):
    assert "local" in str(await mcp.call_tool("status", {}))


@pytest.mark.integration
async def test_mcp_run_collector_ok_and_unknown(mcp):
    assert "records" in str(await mcp.call_tool("run_collector", {"name": "consumption"}))
    assert "unknown" in str(await mcp.call_tool("run_collector", {"name": "missing"}))


@pytest.mark.integration
async def test_mcp_recent_data_ok_and_unknown(mcp):
    assert "rows" in str(await mcp.call_tool("recent_data", {"dataset": "consumption"}))
    assert "unknown" in str(await mcp.call_tool("recent_data", {"dataset": "nope"}))
