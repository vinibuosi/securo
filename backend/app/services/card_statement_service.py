"""Auditable statement projection; never changes the provider's total card debt.

A provider bill id is identity, a due date is only a label. Unresolved aggregate
installment purchases stay visible outside estimated monthly totals. We never
manufacture monthly installments by dividing a full purchase amount.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.core.app_clock import app_today
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services.credit_card_service import compute_effective_date


def decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def iso_date(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def closing_date(bill):
    raw = bill.raw_data or {}
    return iso_date(raw.get("billClosingDate") or raw.get("closingDate"))


def payment(tx):
    raw = tx.raw_data or {}
    meta = raw.get("creditCardMetadata") or {}
    category = str(raw.get("category") or "").casefold()
    return tx.type == "credit" and (
        str(meta.get("transactionType") or raw.get("operationType") or "").upper() == "PAYMENT"
        or category in {"credit card payment", "pagamento de cartão de crédito"}
    )


def purchase_id(tx):
    meta = (tx.raw_data or {}).get("creditCardMetadata") or {}
    # These are explicit transaction-family references, never merchant names.
    return meta.get("purchaseId") or meta.get("originalTransactionId")


def aggregate_candidate(tx):
    return (tx.bill_id is None and tx.type == "debit" and
            (tx.total_installments or 0) > 1 and (tx.installment_total_amount is None
            or abs(tx.amount) == abs(tx.installment_total_amount)))


def payment_total(bill, transactions):
    raw = bill.raw_data or {}
    official = raw.get("payments")
    if not isinstance(official, list):
        # Transaction feed is a fallback, never added on top of the bill feed.
        found = [t for t in transactions if payment(t)]
        return sum((abs(t.amount) for t in found), Decimal(0)) if found else None
    seen = set()
    anonymous = set()
    total = Decimal(0)
    for entry in official:
        if not isinstance(entry, dict):
            return None
        value = decimal(entry.get("amount"))
        if value is None:
            return None
        currency = entry.get("currencyCode") or entry.get("currency")
        if currency and currency != bill.currency:
            return None
        key = entry.get("id") or entry.get("transactionId")
        if key:
            if str(key) in seen:
                continue
            seen.add(str(key))
        else:
            # Two anonymous equal entries may be two legitimate payments or
            # duplicate sources: leave unknown instead of guessing either way.
            fingerprint = (str(value), entry.get("date"), entry.get("paymentDate"))
            if fingerprint in anonymous:
                return None
            anonymous.add(fingerprint)
        total += abs(value)
    return total


def transaction_read(tx, reason=None):
    return {"id": str(tx.id), "external_id": tx.external_id, "description": tx.description,
            "amount": float(tx.amount), "currency": tx.currency, "date": tx.date.isoformat(),
            "type": tx.type, "status": tx.status,
            "installment_number": tx.installment_number, "total_installments": tx.total_installments,
            "reason": reason}


def project_statements(account, bills, transactions, today=None):
    today = today or app_today()
    bills_by_id = {b.id: b for b in bills}
    linked = defaultdict(list)
    estimated = defaultdict(list)
    pending, future, unresolved, aggregates = [], [], [], []
    seen_external = set()
    clean = []
    for tx in transactions:
        if tx.is_ignored or getattr(tx, "source", None) == "opening_balance":
            continue
        if tx.external_id:
            if tx.external_id in seen_external:
                continue
            seen_external.add(tx.external_id)
        clean.append(tx)
    lots_by_purchase = defaultdict(list)
    for tx in clean:
        if purchase_id(tx) and not aggregate_candidate(tx):
            lots_by_purchase[str(purchase_id(tx))].append(tx)
    for tx in clean:
        if aggregate_candidate(tx):
            reason = "aggregate_with_linked_installments" if lots_by_purchase.get(str(purchase_id(tx))) and purchase_id(tx) else "unresolved_full_purchase"
            aggregates.append(transaction_read(tx, reason))
            continue
        if tx.status == "pending":
            pending.append(transaction_read(tx))
            if tx.date > today and tx.total_installments:
                future.append(transaction_read(tx))
            continue
        if tx.bill_id in bills_by_id:
            linked[tx.bill_id].append(tx)
            continue
        if tx.date > today:
            future.append(transaction_read(tx))
            continue
        raw_bill_id = ((tx.raw_data or {}).get("creditCardMetadata") or {}).get("billId")
        if raw_bill_id:
            unresolved.append(transaction_read(tx, "bill_not_available"))
            continue
        due = tx.effective_bill_date or compute_effective_date(tx.date, account.statement_close_day, account.payment_due_day)
        # An unlinked row is a candidate for a known statement only with
        # official close anchors. Equal due dates remain ambiguous.
        candidates = []
        for bill in bills:
            close = closing_date(bill)
            prior = [closing_date(b) for b in bills if closing_date(b) and close and closing_date(b) < close]
            start = max(prior) if prior else None
            if tx.effective_bill_date:
                matches = bill.due_date == tx.effective_bill_date
            else:
                matches = close is not None and start is not None and start < tx.date <= close
                if not matches and (close is None or start is None):
                    matches = bool(account.statement_close_day and account.payment_due_day and due == bill.due_date)
            if matches:
                candidates.append(bill)
        if len(candidates) == 1:
            linked[candidates[0].id].append(tx)
        elif len(candidates) > 1:
            unresolved.append(transaction_read(tx, "ambiguous_cycle"))
        else:
            estimated[due].append(tx)
    cycles = []
    for bill in bills:
        rows = linked[bill.id]
        paid = payment_total(bill, rows)
        details = sum((-abs(t.amount) if t.type == "credit" else abs(t.amount)
                       for t in rows if not payment(t)), Decimal(0))
        close = closing_date(bill)
        raw_status = str((bill.raw_data or {}).get("status") or "").upper()
        closed = close <= today if close else raw_status in {"CLOSED", "PAID", "OVERDUE"}
        remaining = max(Decimal(0), bill.total_amount - paid) if paid is not None else None
        status = "paid" if remaining == 0 else "partially_paid" if paid is not None and paid > 0 else "closed" if closed else "open" if close else "unknown"
        cycles.append({"id": str(bill.id), "external_id": bill.external_id,
                       "due_date": bill.due_date.isoformat(),
                       "closing_date": close.isoformat() if close else None,
                       "currency": bill.currency, "status": status, "estimated": False,
                       "total": float(bill.total_amount), "paid": float(paid) if paid is not None else None,
                       "remaining": float(remaining) if remaining is not None else None,
                       "detail_total": float(details), "discrepancy": float(bill.total_amount - details),
                       "incomplete": paid is None or close is None or bill.total_amount != details,
                       "transactions": [transaction_read(t) for t in rows]})
    for due, rows in estimated.items():
        total = sum((-abs(t.amount) if t.type == "credit" else abs(t.amount)
                     for t in rows if not payment(t)), Decimal(0))
        cycles.append({"id": f"estimated:{due}", "external_id": None, "due_date": due.isoformat(),
                       "closing_date": None, "currency": account.currency,
                       "status": "estimated", "estimated": True, "total": float(total),
                       "paid": None, "remaining": None, "detail_total": float(total),
                       "discrepancy": None, "incomplete": True,
                       "transactions": [transaction_read(t) for t in rows]})
    return {"total_debt": float(account.balance), "currency": account.currency,
            "cycles": sorted(cycles, key=lambda c: (c["due_date"], c["id"]), reverse=True),
            "pending": pending, "future_installments": future,
            "unresolved": unresolved, "aggregate_purchases": aggregates}


async def get_overview(session, account):
    bills = list((await session.scalars(select(CreditCardBill).where(
        CreditCardBill.account_id == account.id))).all())
    rows = list((await session.scalars(select(Transaction).where(
        Transaction.account_id == account.id).order_by(Transaction.created_at, Transaction.id))).all())
    return project_statements(account, bills, rows)
