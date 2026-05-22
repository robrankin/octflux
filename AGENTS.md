# AGENTS.md

Guidance for AI agents and humans working in `octflux`, a configurable collector
for Octopus Energy data.

## What this is

A configurable service that **collects** Octopus Energy data on schedules and
fans it out to one or more **outputs** (TimescaleDB/Postgres primary, SQLite, MQTT),
with a control surface (REST `/api/v1` + MCP). One process runs the scheduler, the
API and MCP. `docker-compose.yml` ships the whole stack (TimescaleDB + octflux).

## Medallion (on TimescaleDB)
- **Bronze**: raw collected tables (hypertables where high-volume).
- **Silver**: conformed dimensions (`dim_meter`, `dim_tariff`) + `fact_cost`
  (consumption × the unit rate in force, via `schema/medallion.py: refresh_silver`,
  cross-dialect; the engine schedules it).
- **Gold**: real-time continuous aggregates of consumption & cost at
  hourly/daily/monthly grain (`cagg_{consumption,cost}_{hourly,daily,monthly}`),
  `cagg_carbon_daily`, and the total-bill views `bill_daily` / `bill_monthly`
  (import + standing charge − export) + compression + optional retention
  (`schema/medallion.py: create_gold`, Timescale-only, built in the sink on start).

## The shape (dimensions × drivers × registry × Protocol, config-selected)

Each pluggable thing is a *dimension* with multiple *driver* implementations; the
active drivers are chosen at runtime from `config.yaml`, not by editing code.

| Dimension | Dir | Protocol (`core/protocols.py`) | Registry |
|---|---|---|---|
| Data feed | `collectors/` | `Collector` | `collectors/__init__.py: COLLECTOR_BUILDERS` |
| Output | `sinks/` | `Sink` | `sinks/__init__.py: SINK_BUILDERS` |
| Octopus transport | `clients/` | `RestApi` / `GraphQlApi` | — |

Flow: **collectors** (what to fetch) → **engine** (`core/engine.py`: schedule +
resolve account once + fan-out) → **sinks** (where it goes).

### Add a collector
1. A model in `core/models.py`, a table in `schema/tables.py`, a `DatasetSpec`
   in `schema/datasets.py` (key + change-comparison columns + model→row).
2. A module in `collectors/` with a pure `parse_*` function, a `Collector` class
   (`name`, `datasets`, `async collect(ctx)`), and `build(options)`.
3. Register it in `collectors/__init__.py`.

### Add a sink
A module in `sinks/` exposing `build(name, options) -> Sink`; register it. SQL
backends just build a URL and reuse `sinks/base.py: SqlSink` (one dialect-agnostic
implementation; change-detection is a Python diff so counts are accurate and there
is no write churn on any backend).

## Conventions
- Async throughout; never block the loop (async drivers).
- Datetimes are stored **naive UTC** (cross-dialect safe); the sink normalises.
- structlog events with a per-run `run_id`; recent lines are in the ring buffer
  exposed at `/api/v1/logs`.
- Config is Pydantic (`config/schema.py`), YAML with `${ENV}` for secrets.

## Tests
`tests/{unit,integration,contracts,property,timescale}` + `fakes/`. Tiers:
- **default** (`pytest`): hermetic — unit, integration (fakes + SQLite), contracts,
  property (`hypothesis`). No network, no Docker. ~92% coverage.
- **`-m timescale`**: spins an ephemeral TimescaleDB via **testcontainers** (needs
  Docker) and exercises hypertables, the gold caggs/compression/retention, the bill
  views, compat views, and the sink contract on real Postgres. Auto-skips if Docker
  isn't available.
- **`-m live`**: opt-in, hits the real Octopus API (not currently populated).

Clients are tested with `httpx.MockTransport` (no network); time logic with
`freezegun`. Coverage gate (`fail_under=90`) applies when run as
`pytest --cov=octflux`.

## Migrations
Alembic, multi-dialect, URL from `$OCTFLUX_DB_URL` (a *sync* URL). Baseline
`0001` creates the schema from the single `MetaData`; later changes autogenerate.

## TimescaleDB
On Postgres with the `timescaledb` extension, the high-volume time-series tables
become hypertables (`schema/timescale.py: HYPERTABLES`), partitioned on their time
column. This is why every table's PK is its natural key (which includes the time
column) and there is no surrogate `id` -- Timescale requires the partition column
to be in the PK/unique index. It is a no-op without the extension (plain Postgres,
SQLite gets regular tables). Conversion runs in the sink's auto-create and in
migration `0001`.
