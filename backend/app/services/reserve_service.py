"""Reserved balances are disclosures until their accounting relationship is confirmed.

Only an explicit outside-balance reconciliation creates a valued asset. All other
states keep the disclosure but contribute zero additional net worth. Missing
payloads retain the last valid snapshot and mark it stale, never imply redemption.
"""
import hashlib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.app_clock import app_today
from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_value import AssetValue


def money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_reserves(bank: dict, currency: str) -> list[dict] | None:
    raw = bank.get("reservedBalances")
    if not isinstance(raw, list):
        return None
    result = []
    occurrences: dict[str, int] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("description") or entry.get("type") or "Reserva")[:255]
        native_id = entry.get("id") or entry.get("reservedBalanceId")
        kind = str(entry.get("type") or "").upper()
        # A name by itself never proves that a generic block is a savings pot.
        classification = {
            "SAVINGS": "savings_pot", "SAVINGS_POT": "savings_pot",
            "COFRINHO": "savings_pot", "JUDICIAL": "judicial_block",
            "JUDICIAL_BLOCK": "judicial_block", "BLOCKED": "blocked_balance",
        }.get(kind, "generic_reserve")
        base = str(native_id) if native_id is not None else hashlib.sha256(
            f"{kind}:{name}".encode()
        ).hexdigest()
        occurrence = occurrences.get(base, 0)
        occurrences[base] = occurrence + 1
        identity = base if occurrence == 0 else f"{base}:{occurrence}"
        amount = money(entry.get("balance", entry.get("amount", entry.get("value"))))
        result.append({
            "id": identity, "name": name, "amount": str(amount) if amount is not None else None,
            "currency": str(entry.get("currencyCode") or currency),
            "classification": classification, "reconciliation": "pending",
            "stable_identity": native_id is not None and occurrence == 0,
            "investment_id": str(entry["investmentId"]) if entry.get("investmentId") else None,
            "raw": entry,
        })
    # Duplicate provider ids are ambiguous, including the first occurrence.
    for row in result:
        if occurrences.get(row["id"], 0) > 1:
            row["stable_identity"] = False
    return result


def merge_metadata(previous: dict | None, incoming: dict) -> dict:
    merged = {**(previous or {}), **incoming}
    old = {r["id"]: r for r in (previous or {}).get("reserves", [])}
    current = incoming.get("reserves")
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for row in current or []:
        prior = old.pop(row["id"], {})
        valid = row.get("amount") is not None
        rows.append({**prior, **row,
                     "amount": row.get("amount") if valid else prior.get("amount"),
                     "reconciliation": prior.get("reconciliation", "pending"),
                     "updated_at": now if valid else prior.get("updated_at", now),
                     "stale": not valid})
    # Even an empty list cannot prove redemption: require an explicit zero.
    rows.extend({**row, "stale": True} for row in old.values())
    merged["reserves"] = rows
    return merged


async def materialize(session: AsyncSession, account: Account) -> None:
    metadata = account.provider_metadata or {}
    for reserve in metadata.get("reserves", []):
        key = "reserve:" + hashlib.sha256(f'{account.id}:{reserve["id"]}'.encode()).hexdigest()
        asset = await session.scalar(select(Asset).where(
            Asset.workspace_id == account.workspace_id, Asset.source == "pluggy_reserve",
            Asset.external_id == key,
        ))
        # An explicit cross-reference to /investments takes precedence over a
        # manual outside decision, including when it appears on a later sync.
        mirrored = bool(reserve.get("investment_id"))
        amount = money(reserve.get("amount"))
        counted = (reserve.get("reconciliation") == "outside" and
                   reserve.get("stable_identity") and not mirrored and amount is not None)
        if asset is None and not counted:
            continue
        if asset is None:
            asset = Asset(user_id=account.user_id, workspace_id=account.workspace_id,
                          source="pluggy_reserve", external_id=key, type="investment",
                          name=reserve["name"], currency=reserve["currency"],
                          valuation_method="manual", connection_id=account.connection_id)
            session.add(asset)
            await session.flush()
        asset.name = reserve["name"]
        asset.currency = reserve["currency"]
        asset.connection_id = account.connection_id
        asset.external_metadata = {"reserve": reserve, "account_id": str(account.id)}
        # No deletion or archive: retain history, replace today's valuation.
        value = amount if counted else Decimal(0)
        today = app_today()
        snapshot = await session.scalar(select(AssetValue).where(
            AssetValue.asset_id == asset.id, AssetValue.date == today))
        if snapshot is None:
            session.add(AssetValue(asset_id=asset.id, date=today, amount=value, source="pluggy_reserve"))
        else:
            snapshot.amount = value
    await session.flush()


async def sync_metadata(session: AsyncSession, account: Account, incoming: dict | None) -> None:
    if incoming is None:
        return
    account.provider_metadata = merge_metadata(account.provider_metadata, incoming)
    await materialize(session, account)
