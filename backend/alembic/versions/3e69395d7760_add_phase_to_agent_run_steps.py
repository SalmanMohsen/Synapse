"""add_phase_to_agent_run_steps

Revision ID: 3e69395d7760
Revises: 81ac47dc589c
Create Date: 2026-07-18 05:54:14.380252

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql



# revision identifiers, used by Alembic.
revision: str = '3e69395d7760'
down_revision: Union[str, None] = '81ac47dc589c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

agent_run_step_phase_enum = postgresql.ENUM(
    'planning', 'execution', name='agentrunstepphase'
)

def upgrade() -> None:
    agent_run_step_phase_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'agent_run_steps',
        sa.Column(
            'phase',
            agent_run_step_phase_enum,
            nullable=False,
            server_default='execution',
        ),
    )


def downgrade() -> None:
    op.drop_column('agent_run_steps', 'phase')
    agent_run_step_phase_enum.drop(op.get_bind(), checkfirst=True)
