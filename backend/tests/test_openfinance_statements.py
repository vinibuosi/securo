import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.providers.base import BillData
from app.providers.pluggy import _build_bill_data
from app.services.card_statement_service import project_statements
from app.services.connection_service import _sync_credit_card_bills


def account():
    return SimpleNamespace(balance=Decimal("1200"), currency="BRL", statement_close_day=25, payment_due_day=5)


def bill(external="oct", due="2026-10-05", close="2026-09-25", total="100", payments=None):
    raw = {"billClosingDate": close}
    if payments is not None:
        raw["payments"] = payments
    return SimpleNamespace(id=uuid.uuid4(), external_id=external, due_date=date.fromisoformat(due),
        total_amount=Decimal(total), currency="BRL", raw_data=raw)


def tx(amount="100", day="2026-09-10", bill=None, **extra):
    values = dict(id=uuid.uuid4(), external_id=str(uuid.uuid4()), description="Compra fictícia",
        amount=Decimal(amount), currency="BRL", date=date.fromisoformat(day), type="debit", status="posted",
        is_ignored=False, is_opening_balance=False, bill_id=bill.id if bill else None,
        effective_bill_date=None, raw_data={}, installment_number=None, total_installments=None,
        installment_total_amount=None)
    values.update(extra)
    return SimpleNamespace(**values)


def test_xp_1200_purchase_is_not_added_to_first_100_installment():
    october = bill(payments=[{"id": "p1", "amount": 40}, {"id": "p1", "amount": 40}])
    november = bill("nov", "2026-11-05", "2026-10-25", payments=[])
    family = {"creditCardMetadata": {"purchaseId": "purchase-1"}}
    full = tx("1200", raw_data=family, total_installments=12, installment_number=1,
              installment_total_amount=Decimal(1200))
    first = tx(bill=october, raw_data=family, total_installments=12, installment_number=1,
               installment_total_amount=Decimal(1200))
    second = tx(bill=november, day="2026-10-10", total_installments=12, installment_number=2,
                installment_total_amount=Decimal(1200))
    payment = tx("40", bill=october, type="credit", raw_data={"operationType": "PAYMENT"})
    legitimate = tx("22", day="2026-08-01")
    future = tx("100", day="2026-12-10", status="pending", total_installments=12, installment_number=4,
                installment_total_amount=Decimal(1200))
    result = project_statements(account(), [october, november],
        [full, first, second, payment, legitimate, future], date(2026, 10, 28))
    current = next(c for c in result["cycles"] if c["id"] == str(october.id))
    assert current["total"] == current["detail_total"] == 100
    assert current["paid"] == 40  # never 80 from both feeds
    assert current["remaining"] == 60
    assert current["status"] == "partially_paid"
    assert result["total_debt"] == 1200
    assert result["aggregate_purchases"][0]["amount"] == 1200
    assert result["aggregate_purchases"][0]["reason"] == "aggregate_with_linked_installments"
    assert len(result["future_installments"]) == 1
    assert any(c["estimated"] and c["total"] == 22 for c in result["cycles"])


def test_equal_due_dates_keep_distinct_identity_and_ambiguous_unlinked_rows():
    a, b = bill(), bill("other")
    override = tx(effective_bill_date=a.due_date)
    result = project_statements(account(), [a, b], [tx(bill=a), tx("50", bill=b), override])
    assert len(result["cycles"]) == 2
    assert result["cycles"][0]["id"] != result["cycles"][1]["id"]
    assert result["unresolved"][0]["reason"] == "ambiguous_cycle"


def test_unknown_payments_are_not_zero_and_refunds_reduce_details():
    official = bill(total="80")
    result = project_statements(account(), [official], [tx(bill=official), tx("20", bill=official, type="credit")])
    cycle = result["cycles"][0]
    assert cycle["paid"] is None and cycle["remaining"] is None
    assert cycle["detail_total"] == 80
    assert cycle["incomplete"]


def test_duplicate_anonymous_payment_is_ambiguous_not_summed():
    official = bill(payments=[{"amount": 40, "date": "2026-10-01"}] * 2)
    result = project_statements(account(), [official], [])
    assert result["cycles"][0]["paid"] is None


def test_pending_and_future_never_join_closed_statement_details():
    official = bill()
    result = project_statements(account(), [official], [tx(bill=official, status="pending")])
    assert result["cycles"][0]["detail_total"] == 0
    assert len(result["pending"]) == 1


def test_bill_parser_preserves_negative_total_and_due_alias():
    parsed = _build_bill_data({"id": "official", "balanceDueDate": "2026-10-05", "totalAmount": "-10"})
    assert parsed is not None
    assert parsed.total_amount == -10
    assert _build_bill_data({"id": "nan", "dueDate": "2026-10-05", "totalAmount": "NaN"}) is None


async def test_bill_sync_retimes_old_transactions_and_survives_failure(session, test_account, test_user):
    test_account.type = "credit_card"
    provider = AsyncMock()
    provider.get_bills.return_value = [BillData("oct", date(2026, 10, 5), Decimal(100), raw_data={"billClosingDate": "2026-09-25"})]
    bills = await _sync_credit_card_bills(session, test_user.id, test_account, provider, {})
    official = bills["oct"]
    transaction = Transaction(user_id=test_user.id, workspace_id=test_account.workspace_id,
        account_id=test_account.id, external_id="old", amount=Decimal(100), type="debit", currency="BRL",
        description="Compra", date=date(2026, 9, 1), effective_date=official.due_date, bill_id=official.id, source="sync")
    session.add(transaction)
    await session.flush()
    provider.get_bills.return_value = [BillData("oct", date(2026, 10, 7), Decimal(100))]
    await _sync_credit_card_bills(session, test_user.id, test_account, provider, {})
    assert transaction.effective_date == date(2026, 10, 7)
    assert official.raw_data is not None
    assert official.raw_data["billClosingDate"] == "2026-09-25"
    provider.get_bills.side_effect = RuntimeError("temporary")
    cached = await _sync_credit_card_bills(session, test_user.id, test_account, provider, {})
    assert cached["oct"].id == official.id
    assert len(list((await session.scalars(select(CreditCardBill))).all())) == 1
