"""Ephemeral TimescaleDB for the `timescale`-marked tests (testcontainers).

Skips cleanly if testcontainers or Docker isn't available, so the default suite
stays green without it.
"""

from __future__ import annotations

import pytest

_IMAGE = "timescale/timescaledb:2.27.1-pg17"


@pytest.fixture(scope="session")
def timescale():
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")
    try:
        pg = PostgresContainer(_IMAGE, username="octflux", password="octflux",
                               dbname="octflux", driver="psycopg")
        pg.start()
    except Exception as exc:  # no Docker, image pull failure, etc.
        pytest.skip(f"cannot start TimescaleDB container: {exc}")
    try:
        url = (f"postgresql+psycopg://octflux:octflux@"
               f"{pg.get_container_host_ip()}:{pg.get_exposed_port(5432)}/octflux")
        yield url
    finally:
        pg.stop()
