from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from octflux.api.app import build_app
from octflux.config.schema import ApiConfig, Config, McpConfig, OctopusSettings, SinkConfig


def _config(tmp_path) -> Config:
    return Config(
        octopus=OctopusSettings(api_key="x", account_number="A-1"),
        collectors={},  # none enabled -> no network on startup
        sinks={"local": SinkConfig(driver="sqlite", options={"path": str(tmp_path / "api.db")})},
        api=ApiConfig(enabled=True),
        mcp=McpConfig(enabled=False),
    )


@pytest.mark.integration
def test_api_surface(tmp_path):
    with TestClient(build_app(_config(tmp_path))) as client:
        assert client.get("/api/v1/health").json() == {"ok": True}

        status = client.get("/api/v1/status").json()
        assert status["sinks"] == ["local"]
        assert status["collectors"] == []

        ds = client.get("/api/v1/data").json()
        assert "consumption" in ds["datasets"]

        empty = client.get("/api/v1/data/consumption").json()
        assert empty == {"dataset": "consumption", "count": 0, "rows": []}

        assert client.get("/api/v1/data/nonsense").status_code == 404
        assert client.post("/api/v1/collectors/nope/run").status_code == 404

        # collectors list (empty here) + logs ring buffer + OpenAPI
        assert client.get("/api/v1/collectors").json() == []
        logs = client.get("/api/v1/logs?n=5").json()
        assert "logs" in logs and isinstance(logs["logs"], list)
        assert client.get("/api/v1/openapi.json").status_code == 200
        assert client.get("/api/v1/docs").status_code == 200
