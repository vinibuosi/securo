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
    rows = parse_reserves(payload(value), "BRL")
    assert rows is not None
    assert rows[0]["amount"] is None


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
    assert rows is not None
    assert len({r["id"] for r in rows}) == 3
    assert [r["classification"] for r in rows] == ["savings_pot", "judicial_block", "generic_reserve"]
    assert not rows[2]["stable_identity"]


def test_documented_available_amounts_and_identification():
    rows = parse_reserves({"reservedBalances": [
        {"identification": "mp-goal", "name": "Cofrinho Viagem", "availableAmounts": [
            {"amount": "8720.00", "currencyCode": "BRL", "remuneration": {"indexer": "CDI"}},
            {"amount": "10.00", "currencyCode": "USD"},
        ]},
        {"identification": "mp-goal-2", "name": "Emergência", "availableAmounts": [{"amount": 100, "currencyCode": "BRL"}]},
    ]}, "BRL")
    assert rows is not None
    assert [(r["id"], r["amount"], r["currency"]) for r in rows] == [
        ("mp-goal:BRL", "8720.00", "BRL"), ("mp-goal:USD", "10.00", "USD"), ("mp-goal-2:BRL", "100", "BRL")]
    assert all(r["stable_identity"] for r in rows)
    assert rows[0]["raw"]["availableAmounts"][0]["remuneration"]["indexer"] == "CDI"


async def test_reconciliation_api_requires_identity_and_workspace_access(client, auth_headers, session, test_account):
    import uuid
    await sync_metadata(session, test_account, {"reserves": parse_reserves(payload(), "BRL")})
    await session.commit()
    url = f"/api/accounts/{test_account.id}/reserves/pot-1/reconciliation"
    response = await client.put(url, headers=auth_headers, json={"relationship": "outside", "classification": "savings_pot"})
    assert response.status_code == 204
    response = await client.put(f"/api/accounts/{uuid.uuid4()}/reserves/pot-1/reconciliation", headers=auth_headers, json={"relationship": "outside"})
    assert response.status_code == 404
    response = await client.put(url, json={"relationship": "outside"})
    assert response.status_code == 401
