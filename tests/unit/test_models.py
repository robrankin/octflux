from __future__ import annotations

from datetime import UTC, datetime

from octflux.core.models import Account, Agreement, Fuel, MeterPoint

WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _account(product_code: str, *, is_export: bool = False) -> Account:
    ag = Agreement(Fuel.ELECTRICITY, f"E-1R-{product_code}-F", product_code,
                   datetime(2024, 1, 1, tzinfo=UTC), None, is_export)
    mp = MeterPoint(Fuel.ELECTRICITY, "1591016047308", is_export, (), (ag,))
    return Account("A-1", None, (mp,))


def test_go_account_not_intelligent():
    assert _account("GO-VAR-22-10-14").is_intelligent(WHEN) is False


def test_intelligent_account():
    assert _account("INTELLI-VAR-22-10-14").is_intelligent(WHEN) is True


def test_export_intelli_does_not_count():
    assert _account("INTELLI-VAR-22-10-14", is_export=True).is_intelligent(WHEN) is False


def _ag(vf: datetime, vt: datetime | None) -> Agreement:
    return Agreement(Fuel.ELECTRICITY, "E-1R-GO-F", "GO", vf, vt, False)


def test_is_active_at_window_boundaries():
    a = _ag(datetime(2024, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC))
    assert a.is_active_at(datetime(2024, 1, 1, tzinfo=UTC)) is True    # inclusive start
    assert a.is_active_at(datetime(2024, 6, 1, tzinfo=UTC)) is True    # within
    assert a.is_active_at(datetime(2025, 1, 1, tzinfo=UTC)) is False   # exclusive end
    assert a.is_active_at(datetime(2023, 1, 1, tzinfo=UTC)) is False   # before


def test_is_active_at_open_ended():
    a = _ag(datetime(2024, 1, 1, tzinfo=UTC), None)
    assert a.is_active_at(datetime(2099, 1, 1, tzinfo=UTC)) is True


def test_active_agreement_picks_the_one_in_force():
    old = _ag(datetime(2023, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC))
    cur = _ag(datetime(2024, 1, 1, tzinfo=UTC), None)
    mp = MeterPoint(Fuel.ELECTRICITY, "159", False, (), (old, cur))
    assert mp.active_agreement(datetime(2026, 1, 1, tzinfo=UTC)) is cur
    assert mp.active_agreement(datetime(2023, 6, 1, tzinfo=UTC)) is old
    assert mp.active_agreement(datetime(2020, 1, 1, tzinfo=UTC)) is None


def test_account_electricity_gas_split():
    e = MeterPoint(Fuel.ELECTRICITY, "159", False, (), ())
    g = MeterPoint(Fuel.GAS, "G99", False, (), ())
    acct = Account("A-1", None, (e, g))
    assert acct.electricity == (e,) and acct.gas == (g,)
