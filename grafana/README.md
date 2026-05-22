# octflux Grafana dashboards (as code)

Starter dashboard over the octflux **gold** layer (the TimescaleDB `bill_*` views
and `cagg_*` rollups). Dashboards live here as JSON and go into a dashboard folder
named **Octopus** on an **existing** Grafana (≥12). octflux does not bundle Grafana.

```
grafana/
  dashboards/
    octflux-overview.json         # cost & bill (gold layer), adaptive
    octflux-usage.json            # electricity/gas usage, adaptive + Resolution selector
  provisioning/                   # optional: only if you self-host a Grafana
    dashboards/octopus.yaml
    datasources/octflux-timescaledb.yaml
```

`octflux-usage.json` picks resolution from the selected time range (a 4-tier
ladder): **<7d** raw 30-min, **<90d** `cagg_consumption_hourly`, **<2y**
`cagg_consumption_daily`, else `cagg_consumption_monthly` — each re-bucketed to
`$__interval`, so it stays fast at any zoom (a multi-year view reads ~tens of rows,
not 100k+). A **Resolution** dropdown overrides the auto tier
(auto/raw/hourly/daily/monthly). The cost dashboard (`octflux-overview.json`) is
adaptive the same way: the bill switches daily↔monthly (it's daily-grained because
of the standing charge), consumption uses the full ladder. octflux also
exposes v1 `octopus_*` compatibility views (built on sink start, see
`src/octflux/schema/compat.py`) so legacy v1 dashboards run unchanged.

The dashboard reads these objects (created by the warehouse sink):
`bill_monthly`, `bill_daily`, `cagg_consumption_daily`, `cagg_consumption_hourly`,
`cagg_carbon_daily`. Panels reference a datasource via the `${DS_PG}` variable,
defaulting to a datasource with uid `octflux-timescaledb`.

## Push to an existing Grafana with `gcx` (the way we deploy)

```bash
gcx login <ctx> --server https://grafana.example --token glsa_xxx --yes
gcx config check                      # needs Grafana >= 12

# datasource -> the octflux TimescaleDB (DB published on host :5433)
gcx api -X POST /api/datasources -d '{
  "name":"octflux-timescaledb","uid":"octflux-timescaledb","type":"grafana-postgresql-datasource",
  "access":"proxy","url":"<DB_HOST>:5433","user":"octflux","database":"octflux",
  "jsonData":{"database":"octflux","sslmode":"disable","postgresVersion":1700,"timescaledb":true},
  "secureJsonData":{"password":"octflux"}}'

# folder + dashboard
FOLDER=$(gcx api -X POST /api/folders -d '{"title":"Octopus"}' | jq -r .uid)
jq "{dashboard: ., folderUid: \"$FOLDER\", overwrite: true}" dashboards/octflux-overview.json \
  | gcx api -X POST /api/dashboards/db -d @-
```

The dashboard's `${DS_PG}` resolves to the `octflux-timescaledb` datasource uid.
For GitOps going forward: `gcx resources pull dashboards -p ./resources -o yaml`,
commit, then `gcx resources validate && gcx resources push -p ./resources`.

## Alternative — provisioning (if you self-host a Grafana)

Mount `provisioning/` + `dashboards/` into a Grafana you control; the provider's
`folder: Octopus` creates the folder and the datasource is provisioned. Set
`OCTFLUX_DB_HOST` / `OCTFLUX_DB_PORT` (5433) + `POSTGRES_*` in that Grafana's env
(Grafana does not support `${VAR:-default}` — set them explicitly).

> `gcx` is the successor to `grafanactl`; needs Grafana 12+.
> See basic-memory `main/setup/gcx-grafana-cli-observability-as-code`.
