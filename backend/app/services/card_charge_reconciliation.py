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
