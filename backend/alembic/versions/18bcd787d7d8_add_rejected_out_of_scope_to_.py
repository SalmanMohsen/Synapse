"""add rejected_out_of_scope to agentrunstatus

Revision ID: 18bcd787d7d8
Revises: 3e69395d7760
Create Date: 2026-08-02 23:04:35.330309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18bcd787d7d8'
down_revision: Union[str, None] = '3e69395d7760'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guardrail 2 (build plan): the pre-flight scope/actionability gate
    # needs its own terminal AgentRun.status, distinct from the existing
    # human "rejected" plan-review outcome. IF NOT EXISTS makes this safe
    # to re-run. Postgres 12+ allows ADD VALUE inside a transaction block
    # as long as the new value isn't used in that same transaction — this
    # migration only adds it, so the default Alembic per-migration
    # transaction is fine.
    op.execute("ALTER TYPE agentrunstatus ADD VALUE IF NOT EXISTS 'rejected_out_of_scope'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums — removing one means rebuilding
    # the type (create a new type, cast the column over, drop the old type,
    # rename) and first migrating any existing 'rejected_out_of_scope' rows
    # to some other status. Not implemented: that's a destructive,
    # hand-written operation in its own right, not something to do silently
    # as part of an automatic downgrade.
    raise NotImplementedError(
        "Cannot downgrade: Postgres does not support removing a value from "
        "an enum type without rebuilding it. See migration docstring."
    )