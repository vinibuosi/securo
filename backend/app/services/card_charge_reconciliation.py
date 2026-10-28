"""Reconcile only explicit finance-charge references, retaining both raw sources."""
from sqlalchemy import select
from app.models.transaction import Transaction


async def reconcile_charges(session, account):
    if account.type != "credit_card":
        return
    rows = list((await session.scalars(select(Transaction).where(
        Transaction.account_id == account.id))).all())
    references = set()
    for tx in rows:
        if tx.external_id and tx.external_id.startswith("bill_charge:"):
            continue
        raw = tx.raw_data or {}
        meta = raw.get("creditCardMetadata") or {}
        ref = meta.get("financeChargeId") or raw.get("financeChargeId")
        if ref and tx.bill_id and not tx.is_ignored:
            references.add((tx.bill_id, str(ref)))
    for tx in rows:
        if not tx.external_id or not tx.external_id.startswith("bill_charge:"):
            continue
        raw = dict(tx.raw_data or {})
        matched = (tx.bill_id, str(raw.get("id"))) in references
        marker = raw.get("_securo_duplicate_charge")
        if matched and not tx.is_ignored:
            tx.is_ignored = True
            raw["_securo_duplicate_charge"] = True
            tx.raw_data = raw
        elif not matched and marker:
            tx.is_ignored = False
            raw.pop("_securo_duplicate_charge", None)
            tx.raw_data = raw


async def reconcile_installment_representations(session, account):
    """Unresolved full purchases remain auditable but cannot inflate P&L.

    This affects reporting only. Provider account balance remains the debt
    authority; the original row/amount is never deleted or divided.
    """
    if account.type != "credit_card":
        return
    from app.services.card_statement_service import aggregate_candidate
    rows = list((await session.scalars(select(Transaction).where(
        Transaction.account_id == account.id, Transaction.source == "sync"))).all())
    for tx in rows:
        raw = dict(tx.raw_data or {})
        if "_securo_manual_pnl_exclusion" in raw:
            continue
        marked = raw.get("_securo_provider_pnl_exclusion")
        if aggregate_candidate(tx) and not tx.is_ignored and not tx.exclude_from_pnl:
            tx.exclude_from_pnl = True
            raw["_securo_provider_pnl_exclusion"] = True
            tx.raw_data = raw
        elif marked and not aggregate_candidate(tx):
            tx.exclude_from_pnl = False
            raw.pop("_securo_provider_pnl_exclusion", None)
            tx.raw_data = raw
