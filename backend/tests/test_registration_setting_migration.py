"""The ambiguous legacy 099 must preserve saved registration preferences."""

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.util import CommandError
from sqlalchemy.ext.asyncio import create_async_engine
from unittest.mock import patch

_PATH = Path(__file__).resolve().parents[1] / "alembic/versions/100_reconcile_legacy_099.py"
_SPEC = importlib.util.spec_from_file_location("reconcile_legacy_099", _PATH)
assert _SPEC and _SPEC.loader
migration = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migration)


@pytest.fixture
async def migration_connection():
    url = os.environ.get("POSTGRES_TEST_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("CI must supply POSTGRES_TEST_URL")
        pytest.skip("isolated PostgreSQL not configured")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = f"migration_099_{uuid.uuid4().hex}"
                await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.execute(sa.text("CREATE TABLE accounts (id integer PRIMARY KEY)"))
                await connection.execute(sa.text("INSERT INTO accounts VALUES (1)"))
                await connection.execute(sa.text(
                    "CREATE TABLE app_settings (key text PRIMARY KEY, value text NOT NULL)"
                ))
                await connection.execute(sa.text(
                    "INSERT INTO app_settings VALUES ('timezone', 'America/Sao_Paulo')"
                ))
                yield connection
            finally:
                # All DDL/data belong to this test transaction; no existing DB is touched.
                await transaction.rollback()
    finally:
        await engine.dispose()


def _upgrade(connection):
    with Operations.context(MigrationContext.configure(connection)):
        with patch.object(migration.context, "is_offline_mode", return_value=False):
            migration.upgrade()


@pytest.mark.parametrize("saved", [None, "true", "false"])
@pytest.mark.parametrize("existing_count", [0, 3, 7])
async def test_reconciles_legacy_states_without_changing_data(migration_connection, saved, existing_count):
    connection = migration_connection
    if saved is not None:
        await connection.execute(sa.text(
            "INSERT INTO app_settings VALUES ('registration_enabled', :value)"
        ), {"value": saved})

    def prepare(sync):
        with Operations.context(MigrationContext.configure(sync)):
            for column in migration._columns()[:existing_count]:
                migration.op.add_column("accounts", column)
    await connection.run_sync(prepare)
    if existing_count:
        await connection.execute(sa.text(
            "UPDATE accounts SET loan_kind='mortgage', loan_original_amount=1234.56"
        ))
    before = (await connection.execute(sa.text("SELECT * FROM app_settings ORDER BY key"))).all()
    await connection.run_sync(_upgrade)
    await connection.run_sync(_upgrade)  # safe if explicitly retried inside a transaction
    columns = await connection.run_sync(lambda c: sa.inspect(c).get_columns("accounts"))
    assert {c["name"] for c in columns} == {"id", *(c.name for c in migration._columns())}
    assert (await connection.execute(sa.text("SELECT * FROM app_settings ORDER BY key"))).all() == before
    row = (await connection.execute(sa.text("SELECT * FROM accounts"))).mappings().one()
    assert row["id"] == 1
    if existing_count:
        from decimal import Decimal
        assert row["loan_kind"] == "mortgage"
        assert row["loan_original_amount"] == Decimal("1234.56")
    else:
        assert all(row[c.name] is None for c in migration._columns())


@pytest.mark.parametrize("definition", [
    "numeric(10, 2)", "numeric(15, 2) NOT NULL DEFAULT 0", "numeric(15, 2) DEFAULT 0",
])
async def test_incompatible_definition_aborts_before_adding_columns(migration_connection, definition):
    connection = migration_connection
    await connection.execute(sa.text(f"ALTER TABLE accounts ADD loan_original_amount {definition}"))
    with pytest.raises(CommandError, match="incompatible accounts.loan_original_amount"):
        await connection.run_sync(_upgrade)
    columns = await connection.run_sync(lambda c: sa.inspect(c).get_columns("accounts"))
    assert {c["name"] for c in columns} == {"id", "loan_original_amount"}
    assert (await connection.execute(sa.text("SELECT count(*) FROM accounts"))).scalar_one() == 1


def test_offline_mode_requires_inspection():
    with patch.object(migration.context, "is_offline_mode", return_value=True):
        with pytest.raises(CommandError, match="online PostgreSQL"):
            migration.upgrade()


def test_downgrade_is_refused_before_any_database_operation():
    with pytest.raises(CommandError, match="cannot be downgraded automatically"):
        migration.downgrade()
