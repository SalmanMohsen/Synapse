"""add_check_tier_to_agent_run_steps

Revision ID: 81ac47dc589c
Revises: 88721a7f7de5
Create Date: 2026-07-17 21:50:42.424165

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '81ac47dc589c'
down_revision: Union[str, None] = '88721a7f7de5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

check_tier_enum = postgresql.ENUM(
    'repo_test_suite', 'generic_validator', 'sanity_only', name='checktier'
)


def upgrade() -> None:
    check_tier_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('agent_run_steps', sa.Column('check_tier', check_tier_enum, nullable=True))
    op.add_column('agent_run_steps', sa.Column('requires_human_review', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('agent_run_steps', sa.Column('job_try', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_run_steps', 'job_try')
    op.drop_column('agent_run_steps', 'requires_human_review')
    op.drop_column('agent_run_steps', 'check_tier')
    check_tier_enum.drop(op.get_bind(), checkfirst=True)