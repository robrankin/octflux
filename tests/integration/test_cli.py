from __future__ import annotations

import pytest

from octflux import app


def test_build_parser():
    args = app.build_parser().parse_args(["--config", "c.yaml", "--once", "consumption",
                                          "--log-level", "DEBUG", "--log-format", "json"])
    assert args.config == "c.yaml" and args.once == "consumption"
    assert args.log_level == "DEBUG" and args.log_format == "json"


@pytest.mark.integration
def test_main_once_runs_one_collector(monkeypatch, tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("octopus:\n  api_key: k\n  account_number: A-1\n")
    calls = {}

    class FakeEngine:
        def __init__(self, config, **kw):
            calls["init"] = True

        async def start(self, **kw):
            calls["start"] = kw

        async def run_collector(self, name):
            calls["ran"] = name

        async def stop(self):
            calls["stopped"] = True

    monkeypatch.setattr("octflux.core.engine.Engine", FakeEngine)
    rc = app.main(["--config", str(cfg), "--once", "consumption"])
    assert rc == 0
    assert calls["ran"] == "consumption"
    assert calls["start"] == {"schedule": False, "run_initial": False}
    assert calls["stopped"] is True
