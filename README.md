# octflux

octflux is a small service that collects Octopus Energy data into your own database and keeps it for as long as you want — so electricity and gas usage, costs and carbon can be tracked over time, independently of the Octopus app.

## What it collects

On a schedule, for each account:

- Half-hourly **electricity & gas consumption** (import and export)
- **Tariffs** — unit rates and standing charges
- **Balance, transactions and statements**
- **Meter readings**, **Octoplus** status, and **Intelligent Octopus** dispatches
- Regional **carbon intensity** for the supply postcode

## What it does with it

Everything is stored in **TimescaleDB** and built up in layers: the raw half-hourly readings, a **costed view** (every interval priced against the tariff in force at the time), and **daily/monthly rollups** of usage, cost and the full bill — import + standing charge − export. Old high-resolution data can be pruned automatically, or kept forever (the default).

## Seeing it

Grafana dashboards (an **Octopus** folder) show **usage** and **cost / bill** over any time range, automatically choosing the right resolution as the view zooms in or out. A small **REST API** and an **MCP** endpoint let other tools — and AI assistants — check status and trigger collections.

## Running it

```bash
cp .env.example .env               # Octopus + database details
cp config.example.yaml config.yaml
docker compose up -d               # starts TimescaleDB + octflux
```

## Configuration

Two files: **`config.yaml`** for behaviour (what to collect, how often, where it goes) and **`.env`** for secrets and host details (API key, account number, database password). Nothing sensitive is committed.

## Development

Python 3.11+, packaged under `src/octflux`. To work on it:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest            # fast, hermetic suite
ruff check .      # lint
```

Most tests need no network or Docker; the TimescaleDB-specific tests (`pytest -m timescale`) spin up a throwaway database via Docker. Architecture and conventions are in `AGENTS.md`.

## Contributing

Issues and pull requests are welcome. Please keep the test suite green and `ruff` clean, and add tests for new behaviour.
