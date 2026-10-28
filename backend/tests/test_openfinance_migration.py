"""The additive revision must preserve pre-existing financial rows and credentials."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = Path(__file__).resolve().parents[1] / "alembic/versions/101_openfinance_account_metadata.py"
SPEC = importlib.util.spec_from_file_location("openfinance_101", PATH)
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


async def test_revision_101_preserves_existing_rows(postgres_sessions):
    # A separate schema is created by the fixture, never a production schema.
    async with postgres_sessions() as session:
        connection = await session.connection()
        def check(sync):
            # The fixture represents a new schema already at model head. Remove
            # ONLY the empty test column to model an existing revision-100 DB.
            schema = sync.get_execution_options()["schema_translate_map"][None]
            sync.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            sync.exec_driver_sql('ALTER TABLE accounts DROP COLUMN provider_metadata')
            sync.exec_driver_sql('CREATE TABLE financial_sentinel (id integer PRIMARY KEY, balance numeric(15,2), credentials json)')
            sync.exec_driver_sql('INSERT INTO financial_sentinel VALUES (1, 338.79, \'{"item_id":"synthetic"}\')')
            with Operations.context(MigrationContext.configure(sync)):
                migration.upgrade()
            columns = {c["name"]: c for c in sa.inspect(sync).get_columns("accounts", schema=schema)}
            assert columns["provider_metadata"]["nullable"]
            row = sync.exec_driver_sql('SELECT balance, credentials FROM financial_sentinel').one()
            assert str(row.balance) == "338.79"
            assert row.credentials == {"item_id": "synthetic"}
        await connection.run_sync(check)


def test_revision_101_has_no_destructive_downgrade():
    from alembic.util import CommandError
    with pytest.raises(CommandError, match="restore a backup"):
        migration.downgrade()
