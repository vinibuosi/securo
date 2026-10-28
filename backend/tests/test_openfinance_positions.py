from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select, func

from app.models.asset import Asset
from app.models.asset_group import AssetGroup
from app.models.asset_value import AssetValue
from app.providers.pluggy import _build_holding_data
from app.services.connection_service import _sync_holdings
from app.services.asset_group_service import consolidate_positions, _rollup


def lot(i, value, **extra):
    return _build_holding_data({"id": str(i), "name": "RDB Nubank", "balance": str(value),
        "amountOriginal": str(i * 100), "currencyCode": "BRL", "type": "FIXED_INCOME",
        "issueDate": "2020-01-01", "purchaseDate": "2026-09-01", **extra})


def test_purchase_date_and_no_name_based_grouping():
    holding = lot(1, 101)
    assert holding.purchase_date == date(2026, 9, 1)
    assert "_securo_savings_group" not in holding.metadata
    assert lot(1, 80, status="PARTIAL_WITHDRAWAL").metadata["_securo_return_incomplete"]


async def test_manual_group_preserves_lots_resync_and_net_worth(session, test_user, test_connection):
    test_connection.provider = "pluggy"
    holdings = [lot(i, i * 101) for i in range(1, 4)]
    await _sync_holdings(session, test_user.id, test_connection, {}, holdings)
    assets = list((await session.scalars(select(Asset))).all())
    assert len(assets) == 3
    group = await consolidate_positions(session, test_connection.workspace_id, test_user.id,
        SimpleNamespace(name="Minha Caixinha", asset_ids=[a.id for a in assets]))
    await _sync_holdings(session, test_user.id, test_connection, {}, holdings)
    stored = await session.get(AssetGroup, group.id)
    count, value, _ = await _rollup(session, stored, "BRL")
    assert count == 3
    assert value == Decimal("606")
    assert sum(a.purchase_price for a in assets) == 600
    assert value - sum(a.purchase_price for a in assets) == 6
    assert all(a.group_id == group.id for a in assets)
    assert await session.scalar(select(func.count()).select_from(Asset)) == 3
    # One cost snapshot and one current snapshot per lot, no group valuation.
    assert await session.scalar(select(func.count()).select_from(AssetValue)) == 6


async def test_explicit_container_id_groups_but_other_positions_stay_individual(session, test_user, test_connection):
    test_connection.provider = "pluggy"
    holdings = [lot(i, i * 101, caixinhaId="box-1", caixinhaName="Reserva") for i in range(1, 4)]
    holdings.append(lot(4, 400))
    await _sync_holdings(session, test_user.id, test_connection, {}, holdings)
    assets = list((await session.scalars(select(Asset))).all())
    assert len({a.group_id for a in assets[:3]}) == 1
    assert assets[3].group_id != assets[0].group_id


async def test_auto_invested_multiple_lots_require_identity_not_equal_values(session, test_connection):
    from app.providers.base import AccountData
    from app.services.connection_service import _prepare_auto_invested, _auto_invested_deductions, _CountedHolding
    test_connection.provider = "pluggy"
    account = AccountData(external_id="bank", name="Nubank", type="checking",
                          balance=Decimal("938.79"), currency="BRL", auto_invested_balance=Decimal(600))
    unknown = [lot(1, 600)]  # equal value alone is deliberately insufficient
    await _prepare_auto_invested(session, test_connection, unknown, [account])
    assert unknown[0].current_value == 0
    assert unknown[0].metadata["_securo_reported_value"] == "600"
    assert _auto_invested_deductions([account], [_CountedHolding(None, Decimal(600), "BRL")]) == {}
    known = [lot(i, i * 100, accountId="bank", isAutomaticallyInvested=True) for i in range(1, 4)]
    await _prepare_auto_invested(session, test_connection, known, [account])
    deduction = _auto_invested_deductions([account], [
        _CountedHolding(h.account_external_id, h.current_value, h.currency, h.external_id, True)
        for h in known])
    assert deduction == {"bank": Decimal(600)}
    assert account.balance - deduction["bank"] + sum(h.current_value for h in known) == account.balance
