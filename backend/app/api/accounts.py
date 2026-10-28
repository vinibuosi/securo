import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.reports import _add_years
from app.core.app_clock import app_today
from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    current_writable_workspace,
)
from app.schemas.account import (
    AccountCreate,
    AccountRead,
    AccountRunningBalancePoint,
    LoanBalanceAdjustment,
    LoanBalanceUpdate,
    LoanScheduleRead,
    AccountSummary,
    AccountUpdate,
    CreditCardBillRead,
)
from app.services import account_service
from app.services.admin_service import get_credit_card_accounting_mode
from app.services.fx_rate_service import _resolve_rate

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

# Same cap as the reports' custom range (`_MAX_CUSTOM_RANGE_YEARS`), counted
# the same way: the series has one point per day. The account page charts the
# latest part of a longer range (#1202).
_MAX_RUNNING_BALANCE_YEARS = 10


@router.get("", response_model=list[AccountRead])
async def list_accounts(
    include_closed: bool = False,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    accounts = await account_service.get_accounts(session, ctx.workspace.id, include_closed=include_closed)
    for acc in accounts:
        await _convert_to_primary(session, acc, ctx.user.primary_currency)
    return accounts


async def _convert_to_primary(session: AsyncSession, acc: dict, primary_currency: str) -> None:
    """Fill the primary-currency balance and open bill of a serialized account."""
    if acc["currency"] == primary_currency:
        return
    # Use the real rate only: the 1:1 fallback would present a foreign
    # balance as already converted (issue #1165). Leaving it unset makes
    # the UI show the native currency and flag the missing rate.
    rate = await _resolve_rate(session, acc["currency"], primary_currency)
    if rate is None:
        acc["fx_fallback"] = True
        return
    converted = Decimal(str(acc["current_balance"])) * rate
    acc["balance_primary"] = float(converted.quantize(Decimal("0.01")))
    if acc["open_bill_total"] is not None:
        bill = Decimal(str(acc["open_bill_total"])) * rate
        acc["open_bill_total_primary"] = float(bill.quantize(Decimal("0.01")))


@router.get("/{account_id}/summary", response_model=AccountSummary)
async def get_account_summary(
    account_id: uuid.UUID,
    date_from: Optional[str] = Query(None, alias="from", description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="YYYY-MM-DD"),
    bill_id: Optional[uuid.UUID] = Query(None, description="Aggregate by bill_id (issue #92); takes precedence over from/to"),
    unbilled_only: bool = Query(False, description="Cycle-math fallback only: exclude txs already linked to any bill"),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    from_date = date.fromisoformat(date_from) if date_from else None
    to_date = date.fromisoformat(date_to) if date_to else None
    summary = await account_service.get_account_summary(
        session, account_id, ctx.workspace.id, date_from=from_date, date_to=to_date,
        bill_id=bill_id, unbilled_only=unbilled_only,
    )
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    account = await account_service.get_account(session, account_id, ctx.workspace.id)
    primary_currency = ctx.user.primary_currency
    if account and account.currency != primary_currency:
        # Same rule as list_accounts: without a real rate, leave the *_primary
        # fields unset instead of returning 1:1 values as if converted (#1165).
        rate = await _resolve_rate(session, account.currency, primary_currency)
        if rate is None:
            summary["fx_fallback"] = True
        else:
            for field in (
                "current_balance", "opening_balance", "monthly_income",
                "monthly_expenses", "projected_income", "projected_expenses",
            ):
                converted = Decimal(str(summary[field])) * rate
                summary[f"{field}_primary"] = float(converted.quantize(Decimal("0.01")))

    return summary


@router.get("/{account_id}/balance-history")
async def get_account_balance_history(
    account_id: uuid.UUID,
    date_from: Optional[str] = Query(None, alias="from", description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, alias="to", description="YYYY-MM-DD"),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    from_date = date.fromisoformat(date_from) if date_from else None
    to_date = date.fromisoformat(date_to) if date_to else None
    history = await account_service.get_account_balance_history(
        session, account_id, ctx.workspace.id, date_from=from_date, date_to=to_date,
    )
    if history is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    account = await account_service.get_account(session, account_id, ctx.workspace.id)
    primary_currency = ctx.user.primary_currency
    if account and account.currency != primary_currency:
        for point in history:
            point_date = date.fromisoformat(point["date"])
            rate = await _resolve_rate(session, account.currency, primary_currency, point_date)
            if rate is None:
                point["fx_fallback"] = True
            else:
                converted = Decimal(str(point["balance"])) * rate
                point["balance_primary"] = float(converted.quantize(Decimal("0.01")))

    return history


@router.get("/{account_id}/running-balance", response_model=list[AccountRunningBalancePoint])
async def get_account_running_balance(
    account_id: uuid.UUID,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """Daily balance matching the transaction list's `running_balance` (#1202).

    Missing bounds default like the summary's: month start to today.
    """
    today = app_today()
    date_from = date_from or today.replace(day=1)
    date_to = date_to or today
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="to must be on or after from")
    if date_to > _add_years(date_from, _MAX_RUNNING_BALANCE_YEARS):
        raise HTTPException(
            status_code=422,
            detail=f"Range is too wide (max {_MAX_RUNNING_BALANCE_YEARS} years)",
        )

    accounting_mode = await get_credit_card_accounting_mode(session)
    try:
        series = await account_service.get_account_running_balance(
            session, account_id, ctx.workspace.id, ctx.user.primary_currency,
            date_from, date_to, accounting_mode=accounting_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return series


@router.get("/{account_id}/bills", response_model=list[CreditCardBillRead])
async def get_account_bills(
    account_id: uuid.UUID,
    limit: int = Query(24, ge=1, le=200, description="Max bills to return, newest due_date first"),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """List credit-card bills for an account, newest due_date first.

    Returns an empty list for non-CC accounts and for CC accounts that have
    no synced bills (provider doesn't expose them, or first sync hasn't
    happened). Issue #92.
    """
    bills = await account_service.get_credit_card_bills(
        session, account_id, ctx.workspace.id, limit=limit,
    )
    if bills is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return bills


@router.get("/{account_id}/loan-schedule", response_model=LoanScheduleRead)
async def get_loan_schedule(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    schedule = await account_service.get_loan_schedule(session, account_id, ctx.workspace.id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan account not found")
    return schedule


@router.post("/{account_id}/loan-balance", response_model=LoanBalanceAdjustment)
async def adjust_loan_balance(
    account_id: uuid.UUID,
    data: LoanBalanceUpdate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        result = await account_service.adjust_loan_balance(
            session, account_id, ctx.workspace.id, ctx.user_id, data
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan account not found")
    return result


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    account = await account_service.get_account_with_balances(session, account_id, ctx.workspace.id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    await _convert_to_primary(session, account, ctx.user.primary_currency)
    return account


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        account = await account_service.create_account(session, ctx.workspace.id, ctx.user_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return account_service.serialize_account(account, None, None)


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: uuid.UUID,
    data: AccountUpdate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        account = await account_service.update_account(session, account_id, ctx.workspace.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    # Re-read post-commit so the response resolves the institution/display
    # name pair exactly like GET (update_account leaves the row expired).
    account = await account_service.get_account_with_balances(session, account_id, ctx.workspace.id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        deleted = await account_service.delete_account(session, account_id, ctx.workspace.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


@router.post("/{account_id}/close", response_model=AccountRead)
async def close_account(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        account = await account_service.close_account(session, account_id, ctx.workspace.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.post("/{account_id}/reopen", response_model=AccountRead)
async def reopen_account(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        account = await account_service.reopen_account(session, account_id, ctx.workspace.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account




async def _locked_reconciliation_account(session, account_id, workspace_id):
    """Serialize user reconciliation with the same connection lock as sync."""
    account = await account_service.get_account(session, account_id, workspace_id)
    if account is None:
        return None
    if account.connection_id:
        from app.services.connection_service import get_connection
        connection = await get_connection(session, account.connection_id, workspace_id, for_update=True)
        if connection is None:
            return None
    from sqlalchemy import select
    from app.models.account import Account
    await session.execute(select(Account.id).where(Account.id == account.id).with_for_update())
    await session.refresh(account)
    return account


class ReserveReconciliation(BaseModel):
    relationship: Literal["pending", "included", "outside", "investment"]
    classification: Literal["savings_pot", "generic_reserve", "blocked_balance", "judicial_block"] | None = None


@router.put("/{account_id}/reserves/{reserve_id}/reconciliation", status_code=204)
async def reconcile_reserve(
    account_id: uuid.UUID,
    reserve_id: str,
    data: ReserveReconciliation,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    from app.services.reserve_service import materialize
    account = await _locked_reconciliation_account(session, account_id, ctx.workspace.id)
    if account is None:
        raise HTTPException(404, "Account not found")
    metadata = dict(account.provider_metadata or {})
    rows = [dict(r) for r in metadata.get("reserves", [])]
    reserve = next((r for r in rows if r["id"] == reserve_id), None)
    if reserve is None:
        raise HTTPException(404, "Reserve not found")
    if data.relationship == "outside" and (
        not reserve.get("stable_identity") or reserve.get("stale")
        or reserve.get("amount") is None or reserve.get("investment_id")
    ):
        raise HTTPException(422, "A fresh, identified reserve without an investment reference is required")
    reserve["reconciliation"] = data.relationship
    if data.classification is not None:
        reserve["classification"] = data.classification
        reserve["classification_source"] = "user"
    metadata["reserves"] = rows
    account.provider_metadata = metadata
    await materialize(session, account)
    await session.commit()


class AutoInvestmentReconciliation(BaseModel):
    mirror_ids: list[uuid.UUID]
    independent_ids: list[uuid.UUID]


@router.put("/{account_id}/auto-investments", status_code=204)
async def reconcile_auto_investments(
    account_id: uuid.UUID,
    data: AutoInvestmentReconciliation,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    from sqlalchemy import select
    from app.models.asset import Asset
    account = await _locked_reconciliation_account(session, account_id, ctx.workspace.id)
    if account is None or not account.connection_id:
        raise HTTPException(404, "Connected account not found")
    mirror = set(data.mirror_ids)
    independent = set(data.independent_ids)
    if mirror & independent or len(mirror | independent) > 500:
        raise HTTPException(422, "Invalid reconciliation selection")
    assets = list((await session.scalars(select(Asset).where(
        Asset.workspace_id == ctx.workspace.id, Asset.connection_id == account.connection_id,
        Asset.source == "pluggy", Asset.id.in_(mirror | independent),
        Asset.currency == account.currency,
    ))).all())
    if len(assets) != len(mirror | independent):
        raise HTTPException(404, "Position not found")
    from app.models.account import Account
    siblings = list((await session.scalars(select(Account).where(
        Account.connection_id == account.connection_id, Account.id != account.id))).all())
    ext_mirror = {a.external_id for a in assets if a.id in mirror and a.external_id}
    for sibling in siblings:
        prior = (sibling.provider_metadata or {}).get("auto_investment_ids", [])
        if ext_mirror.intersection(prior):
            raise HTTPException(422, "A position is already reconciled to another account")
    account.provider_metadata = {**(account.provider_metadata or {}),
        "auto_investment_ids": sorted(ext_mirror),
        "independent_investment_ids": sorted(a.external_id for a in assets if a.id in independent and a.external_id)}
    await session.commit()


@router.get("/{account_id}/billing-overview")
async def billing_overview(
    account_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    from app.services.card_statement_service import get_overview
    account = await account_service.get_account(session, account_id, ctx.workspace.id)
    if account is None or account.type != "credit_card":
        raise HTTPException(404, "Credit card not found")
    return await get_overview(session, account)
