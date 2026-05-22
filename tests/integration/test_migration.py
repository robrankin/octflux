from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config as AlembicConfig

from octflux.schema.tables import metadata

V2 = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_alembic_upgrade_builds_the_full_schema(tmp_path, monkeypatch):
    db = tmp_path / "m.db"
    monkeypatch.setenv("OCTFLUX_DB_URL", f"sqlite:///{db}")
    cfg = AlembicConfig(str(V2 / "alembic.ini"))
    cfg.set_main_option("script_location", str(V2 / "migrations"))

    command.upgrade(cfg, "head")  # runs migrations/env.py online (create_hypertables no-ops on sqlite)

    eng = sa.create_engine(f"sqlite:///{db}")
    tables = set(sa.inspect(eng).get_table_names())
    assert {t.name for t in metadata.tables.values()} <= tables   # every modelled table created
    assert "alembic_version" in tables
    eng.dispose()
