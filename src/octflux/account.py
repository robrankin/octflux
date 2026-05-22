"""Resolve the Account once per cycle from REST (+ GraphQL for meter ids/postcode).

REST gives meter points, serials, agreements and is_export; the GraphQL meta
query supplies each meter's Kraken id (needed by the meter-readings collector)
and the supply postcode (needed by carbon intensity). Resolved once and shared
to every collector via the CollectContext, so the account is fetched once.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import structlog

from .clients.base import GraphQlApi, JsonDict, RestApi
from .clients.queries import ACCOUNT_META
from .core.models import Account, Agreement, Fuel, Meter, MeterPoint
from .core.time import parse_dt

log = structlog.get_logger(__name__)

_PRODUCT_RE = re.compile(r"^[EG]-\d+R-(.*)-[A-Z]$")
_EPOCH = datetime.min.replace(tzinfo=UTC)  # aware, to match aware agreement comparisons


def product_code(tariff_code: str) -> str:
    m = _PRODUCT_RE.match(tariff_code)
    return m.group(1) if m else tariff_code


def _agreements(raw: list[JsonDict], fuel: Fuel, is_export: bool) -> tuple[Agreement, ...]:
    out = []
    for a in raw:
        tc = a.get("tariff_code")
        if not tc:
            continue
        out.append(Agreement(
            fuel=fuel, tariff_code=tc, product_code=product_code(tc),
            valid_from=parse_dt(a.get("valid_from")) or _EPOCH,
            valid_to=parse_dt(a.get("valid_to")), is_export=is_export,
        ))
    return tuple(out)


def parse_rest_account(data: JsonDict) -> Account:
    points: list[MeterPoint] = []
    for prop in data.get("properties", []):
        for mp in prop.get("electricity_meter_points", []):
            is_export = bool(mp.get("is_export"))
            points.append(MeterPoint(
                fuel=Fuel.ELECTRICITY, identifier=mp["mpan"], is_export=is_export,
                meters=tuple(Meter(m["serial_number"], None) for m in mp.get("meters", [])),
                agreements=_agreements(mp.get("agreements", []), Fuel.ELECTRICITY, is_export),
            ))
        for mp in prop.get("gas_meter_points", []):
            points.append(MeterPoint(
                fuel=Fuel.GAS, identifier=mp["mprn"], is_export=False,
                meters=tuple(Meter(m["serial_number"], None) for m in mp.get("meters", [])),
                agreements=_agreements(mp.get("agreements", []), Fuel.GAS, False),
            ))
    return Account(number=data.get("number", ""), postcode=None, meter_points=tuple(points))


def _meta_index(meta: JsonDict) -> tuple[dict[tuple[str, str], str], str | None]:
    """Return {(identifier, serial): meter_id} and the postcode."""
    ids: dict[tuple[str, str], str] = {}
    postcode = None
    for prop in (meta.get("account") or {}).get("properties", []) or []:
        postcode = postcode or prop.get("postcode")
        for mp in prop.get("electricityMeterPoints", []) or []:
            for m in mp.get("meters", []) or []:
                ids[(mp["mpan"], m["serialNumber"])] = m["id"]
        for mp in prop.get("gasMeterPoints", []) or []:
            for m in mp.get("meters", []) or []:
                ids[(mp["mprn"], m["serialNumber"])] = m["id"]
    return ids, postcode


def _with_meta(account: Account, ids: dict, postcode: str | None) -> Account:
    points = []
    for mp in account.meter_points:
        meters = tuple(
            Meter(m.serial_number, ids.get((mp.identifier, m.serial_number))) for m in mp.meters
        )
        points.append(MeterPoint(mp.fuel, mp.identifier, mp.is_export, meters, mp.agreements))
    return Account(account.number, postcode, tuple(points))


async def resolve_account(rest: RestApi, graphql: GraphQlApi, settings) -> Account:
    account = parse_rest_account(await rest.get_account())
    try:
        meta = await graphql.execute(ACCOUNT_META, {"accountNumber": settings.account_number})
        ids, postcode = _meta_index(meta)
        account = _with_meta(account, ids, postcode or settings.postcode)
    except Exception:  # GraphQL meta is best-effort enrichment; REST account still works
        log.warning("account_meta_enrichment_failed", exc_info=True)
    return account
