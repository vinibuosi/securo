# Reconciling legacy revision 099

The affected history contains 100 migration files but only 99 unique revision
IDs. The chain is linear from 001 through 098; both `099_loan_terms.py`
(commit 7cbe880, PR #1234) and `099_registration_setting_follows_env.py`
(commit 565f209, PR #1277) declared revision 099 with parent 098. There are no
other duplicate IDs, missing parents or cycles in that history.

Alembic cannot resolve the duplicate identity. This is not a pair of distinct
branches that can be repaired by a merge revision. The version table stores
only the revision ID, so a database already marked 099 does not identify which
operation ran. Renumbering just one migration would either skip necessary loan
columns or try to create columns already present.

## Forward repair

`099_loan_terms.py` retains its original identity and contents. Revision
`100_reconcile_legacy_099.py` replaces the conflicting registration migration
and follows 099. It inspects the seven loan columns, validates any existing
definitions, and adds only missing nullable columns. It does not overwrite
loan values or update/delete application settings. A schema with incompatible
types, precision, lengths, nullability, defaults, identity or computed columns
requires manual investigation; it fails before adding any columns.

| Starting state | Upgrade behavior |
| --- | --- |
| Fresh database or revision 098 | Original loan migration runs; reconciliation validates its result |
| 099 with loan columns | Existing columns and values remain intact |
| 099 from the registration migration alone | Missing loan columns are added |
| 099 with both effects | Existing state is preserved |
| Partial loan schema | Compatible columns remain; missing columns are added |
| Incompatible loan schema | Upgrade fails without coercing existing columns |

Run the normal `alembic upgrade head` from `backend/`, using the intended
local development database configuration. Do not manually stamp or rewrite a
real database's revision to work around this collision. The reconciliation
requires an online PostgreSQL connection; offline SQL generation is refused.
Only one migration runner should operate on a database at a time.

## Registration behavior

The removed migration deleted `registration_enabled=true`. The 020 migration
seeded that value, but an administrator could later save exactly the same value.
The database cannot distinguish those cases. This repair deliberately preserves
all saved preferences, including true, false, and the absence of a preference.
A saved value continues to override `REGISTRATION_ENABLED`; only an absent value
falls back to the environment. In particular, this repair does **not** implement
the automatic cleanup intended by #1277. Review the registration setting through
the application if the environment variable should determine it. Previously
removed preferences cannot be reconstructed and are not guessed.

The original historical migrations through 099 are unchanged. Consequently,
upgrading a much older installation can still execute their existing data
transformations. This repair is not a guarantee that the entire historical
migration chain is additive.

## Rollback limitation

Revision 100 refuses automatic downgrade. The ambiguous legacy marker cannot
tell which loan columns existed beforehand; removing them could destroy data.
The operator must review any rollback separately. No downgrade or production
migration was performed while validating this change.

## Validation

The regression tests cover all combinations of zero, three, and seven existing
loan columns and registration values absent/true/false. They verify preservation
of saved settings, existing financial values and unrelated data, repeated
reconciliation, rejection of incompatible definitions before adding columns,
and refusal of offline generation and automatic downgrade. Tests run inside
rolled-back transactions in unique PostgreSQL schemas.

The backend suite now also checks the committed migration tree, in addition to
the separate CI migration-chain job. Previously its graph tests only exercised
synthetic trees, allowing the backend suite to pass despite the real collision.

Local integration trials used a dedicated PostgreSQL container and separate
synthetic databases for a fresh install, revision 098, loan-only 099, and a
registration-only 099 state with a subsequently saved false preference. All
reached revision 100 with seven loan columns; settings snapshots before/after
were identical. The registration-only fixture set its own synthetic version
marker; no real installation was stamped. The fresh database served
`/api/health` and the database-backed `/api/setup/status` successfully.

A second `alembic upgrade head` on the migrated database verifies that no
migration repeats. The full backend suite, Ruff and ty must pass before merge.
These trials do not certify unknown manual production schema changes. They did
not access the user's Fedora installation, banking credentials or production
services.

Validation results for this change: **5,872 passed, 2 skipped, 1 expected
failure** (`pytest -n 4 --dist loadfile -ra -W error`, 226.59 s). The two skipped
contract cases are the existing PostgreSQL-only `to_char` exclusions; the
expected failure is the existing knowledge-ingest `MissingGreenlet` case. Ruff,
ty, and the migration-chain check passed. The unchanged baseline had 5,862
passing tests with the same two skips and one expected failure.
