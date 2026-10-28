"""Integration against a disposable PostgreSQL schema, with synthetic money only."""
import uuid
from decimal import Decimal
from datetime import date

from sqlalchemy import select, func

from app.models.user import User
from app.models.workspace import Workspace
from app.models.bank_connection import BankConnection
from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_value import AssetValue
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.providers.pluggy import _build_holding_data
from app.services.connection_service import _sync_holdings
from app.services.reserve_service import parse_reserves, sync_metadata, materialize
from app.services.card_statement_service import get_overview


async def test_postgres_financial_identity_and_repeat_sync(postgres_sessions):
    async with postgres_sessions() as session:
        user = User(id=uuid.uuid4(), email="synthetic@example.invalid", hashed_password="not-a-password", is_active=True)
        session.add(user)
        await session.flush()
        workspace = Workspace(id=uuid.uuid4(), name="Synthetic", created_by_user_id=user.id)
        session.add(workspace)
        await session.flush()
        conn = BankConnection(id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
                              provider="pluggy", external_id="synthetic-item", institution_name="Synthetic")
        session.add(conn)
        await session.flush()
        account = Account(id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
                          connection_id=conn.id, external_id="mp", name="Mercado Pago", type="checking",
                          balance=Decimal("338.79"), currency="BRL")
        session.add(account)
        await session.flush()
        incoming = {"reserves": parse_reserves({"reservedBalances": [
            {"identification": "pot", "name": "Viagem", "availableAmounts": [{"amount": "8720.00", "currencyCode": "BRL"}]}
        ]}, "BRL")}
        await sync_metadata(session, account, incoming)
        assert await session.scalar(select(func.count()).select_from(Asset)) == 0
        assert account.provider_metadata is not None
        account.provider_metadata["reserves"][0]["reconciliation"] = "outside"
        await materialize(session, account)
        await sync_metadata(session, account, incoming)
        assert await session.scalar(select(func.count()).select_from(Asset)) == 1
        assert await session.scalar(select(AssetValue.amount)) + account.balance == Decimal("9058.79")
        holdings = [_build_holding_data({"id": f"lot-{n}", "name": "RDB Nubank", "balance": n * 101,
                    "amountOriginal": n * 100, "currencyCode": "BRL"}) for n in [1, 2, 3]]
        await _sync_holdings(session, user.id, conn, {}, holdings)
        await _sync_holdings(session, user.id, conn, {}, holdings)
        assert await session.scalar(select(func.count()).select_from(Asset)) == 4
        assert await session.scalar(select(func.sum(AssetValue.amount))) == Decimal("9326")
        card = Account(id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
                       connection_id=conn.id, external_id="xp", name="XP", type="credit_card",
                       balance=Decimal("1200"), currency="BRL", statement_close_day=25, payment_due_day=5)
        session.add(card)
        await session.flush()
        bill = CreditCardBill(user_id=user.id, workspace_id=workspace.id, account_id=card.id,
                external_id="oct", due_date=date(2026, 10, 5), total_amount=Decimal(100),
                currency="BRL", raw_data={"billClosingDate": "2026-09-25", "payments": [{"id": "payment", "amount": 40}]})
        session.add(bill)
        await session.flush()
        for external, value, linked in [("purchase-full", 1200, False), ("purchase-1", 100, True)]:
            session.add(Transaction(user_id=user.id, workspace_id=workspace.id, account_id=card.id,
                external_id=external, description="Compra 12x", date=date(2026, 9, 10),
                effective_date=bill.due_date, amount=Decimal(value), currency="BRL", type="debit",
                status="posted", source="sync", bill_id=bill.id if linked else None,
                total_installments=12, installment_number=1, installment_total_amount=Decimal(1200)))
        await session.flush()
        result = await get_overview(session, card)
        assert result["total_debt"] == 1200
        assert result["cycles"][0]["remaining"] == 60
        assert result["cycles"][0]["detail_total"] == 100
        assert result["aggregate_purchases"][0]["amount"] == 1200
        assert account.balance + Decimal("9326") - card.balance == Decimal("8464.79")
