from __future__ import annotations

import textwrap

import pytest
from pydantic import ValidationError

from octflux.config.loader import load_config


def test_env_interpolation_and_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk_live_x")
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(textwrap.dedent("""
        octopus:
          api_key: ${MY_KEY}
          account_number: A-123
        collectors:
          consumption: { schedule: "0 * * * *", options: { days_back: 3 } }
        sinks:
          local: { driver: sqlite, options: { path: x.db } }
    """))
    cfg = load_config(cfg_file)
    assert cfg.octopus.api_key == "sk_live_x"
    assert cfg.octopus.account_number == "A-123"
    assert cfg.collectors["consumption"].options["days_back"] == 3
    assert cfg.sinks["local"].driver == "sqlite"
    assert cfg.api.enabled is True  # default


def test_env_default_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("ABSENT", raising=False)
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(
        "octopus:\n  api_key: ${ABSENT:-fallback}\n  account_number: A-1\n"
    )
    cfg = load_config(cfg_file)
    assert cfg.octopus.api_key == "fallback"


def test_missing_required_octopus_field_raises(tmp_path):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text("octopus:\n  api_key: k\n")  # no account_number
    with pytest.raises(ValidationError):
        load_config(cfg_file)


def test_defaults_applied_for_optional_sections(tmp_path):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text("octopus:\n  api_key: k\n  account_number: A-1\n")
    cfg = load_config(cfg_file)
    assert cfg.api.port == 8088 and cfg.mcp.mount_path == "/mcp"
    assert cfg.medallion.enabled is True and cfg.medallion.window_days == 7
    assert cfg.collectors == {} and cfg.sinks == {}
    assert cfg.octopus.rest_base_url.startswith("https://")
