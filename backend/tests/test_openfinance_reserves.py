from decimal import Decimal

import pytest
from sqlalchemy import select, func

from app.models.asset import Asset
from app.models.asset_value import AssetValue
from app.services.reserve_service import parse_reserves, sync_metadata, materialize


def payload(amount="8720.00", **extra):
    return {"hasReservedBalance": True, "reservedBalances": [
        {"id": "pot-1", "name": "Viagem", "type": "SAVINGS", "balance": amount, **extra}]}


@pytest.mark.parametrize("value", [None, True, "NaN", "Infinity", "-1", {}])
def test_invalid_amount_never_becomes_money(value):
    assert parse_reserves(payload(value), "BRL")[0]["amount"] is None


async def test_reserve_reconciliation_and_idempotence(session, test_account):
    test_account.balance = Decimal("338.79")
    incoming = {"reserves": parse_reserves(payload(), "BRL")}
    await sync_metadata(session, test_account, incoming)
    assert await session.scalar(select(func.count()).select_from(Asset)) == 0
    row = test_account.provider_metadata["reserves"][0]
    assert row["amount"] == "8720.00"
    row["reconciliation"] = "included"
    await materialize(session, test_account)
    assert await session.scalar(select(func.count()).select_from(Asset)) == 0
    row["reconciliation"] = "outside"
    await materialize(session, test_account)
    await sync_metadata(session, test_account, incoming)
    assert await session.scalar(select(func.count()).select_from(Asset)) == 1
    assert await session.scalar(select(func.count()).select_from(AssetValue)) == 1
    value = await session.scalar(select(AssetValue.amount))
    assert test_account.balance + value == Decimal("9058.79")
    await sync_metadata(session, test_account, {"reserves": None})
    assert test_account.provider_metadata["reserves"][0]["stale"]
    assert await session.scalar(select(AssetValue.amount)) == Decimal("8720")
    await sync_metadata(session, test_account, {"reserves": parse_reserves(payload("0"), "BRL")})
    assert await session.scalar(select(AssetValue.amount)) == 0


async def test_investment_reference_overrides_outside_without_double_count(session, test_account):
    await sync_metadata(session, test_account, {"reserves": parse_reserves(payload(), "BRL")})
    test_account.provider_metadata["reserves"][0]["reconciliation"] = "outside"
    await materialize(session, test_account)
    await sync_metadata(session, test_account, {"reserves": parse_reserves(payload(investmentId="inv-1"), "BRL")})
    assert await session.scalar(select(AssetValue.amount)) == 0


def test_multiple_reserves_and_blocks_are_distinct():
    rows = parse_reserves({"reservedBalances": [
        {"id": "a", "name": "Viagem", "type": "SAVINGS", "amount": 100},
        {"id": "b", "name": "Viagem", "type": "JUDICIAL_BLOCK", "balance": 200},
        {"name": "Cofrinho", "amount": 300},
    ]}, "BRL")
    assert len({r["id"] for r in rows}) == 3
    assert [r["classification"] for r in rows] == ["savings_pot", "judicial_block", "generic_reserve"]
    assert not rows[2]["stable_identity"]
