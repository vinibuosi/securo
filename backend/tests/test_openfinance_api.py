"""Real API contracts for the new views; viewer guards are in the sweep."""
from datetime import date
from decimal import Decimal

from app.models.asset import Asset
from app.models.credit_card_bill import CreditCardBill
from app.services.reserve_service import sync_metadata, parse_reserves


async def test_connected_card_api_uses_official_total(client, auth_headers, session, test_account, test_user):
    test_account.type = "credit_card"
    test_account.balance = Decimal(1200)
    session.add(CreditCardBill(user_id=test_user.id, workspace_id=test_account.workspace_id,
        account_id=test_account.id, external_id="official", due_date=date(2026, 10, 5),
        total_amount=Decimal(100), currency="BRL", raw_data={"payments": [{"id": "p", "amount": 40}]}))
    await session.commit()
    response = await client.get(f"/api/accounts/{test_account.id}/billing-overview", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total_debt"] == 1200
    assert response.json()["cycles"][0]["remaining"] == 60
    assert response.json()["cycles"][0]["total"] == 100


async def test_manual_group_api_preserves_positions(client, auth_headers, session, test_user, test_connection):
    positions = [Asset(user_id=test_user.id, workspace_id=test_connection.workspace_id,
        connection_id=test_connection.id, source="pluggy", external_id=f"lot-{i}",
        name="RDB", type="investment", currency="BRL", purchase_price=i * 100)
        for i in [1, 2, 3]]
    session.add_all(positions)
    await session.commit()
    response = await client.post('/api/asset-groups/consolidate', headers=auth_headers,
        json={"name": "Minha Caixinha Nubank", "asset_ids": [str(a.id) for a in positions]})
    assert response.status_code == 201
    assert response.json()["asset_count"] == 3
    for position in positions:
        await session.refresh(position)
        assert str(position.group_id) == response.json()["id"]


async def test_reserve_classification_survives_resync(client, auth_headers, session, test_account):
    payload = {"reservedBalances": [{"identification": "mp", "name": "Viagem", "availableAmounts": [{"amount": 8720, "currencyCode": "BRL"}]}]}
    incoming = {"reserves": parse_reserves(payload, "BRL")}
    await sync_metadata(session, test_account, incoming)
    await session.commit()
    response = await client.put(f'/api/accounts/{test_account.id}/reserves/mp:BRL/reconciliation',
        headers=auth_headers, json={"relationship": "included", "classification": "savings_pot"})
    assert response.status_code == 204
    await session.refresh(test_account)
    await sync_metadata(session, test_account, incoming)
    assert test_account.provider_metadata is not None
    assert test_account.provider_metadata["reserves"][0]["classification"] == "savings_pot"
    assert test_account.provider_metadata["reserves"][0]["reconciliation"] == "included"


async def test_available_credit_uses_official_value_even_when_negative(client, auth_headers, session, test_account):
    test_account.type = "credit_card"
    test_account.balance = Decimal(1200)
    test_account.credit_limit = Decimal(1000)
    test_account.provider_metadata = {"available_credit_limit": "-10.00"}
    await session.commit()
    response = await client.get(f"/api/accounts/{test_account.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["available_credit"] == -10
