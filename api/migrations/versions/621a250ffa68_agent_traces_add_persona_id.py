"""agent_traces_add_persona_id

Revision ID: 621a250ffa68
Revises: 167fe74c435c
Create Date: 2026-07-04 15:53:28.726670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '621a250ffa68'
down_revision: Union[str, None] = '167fe74c435c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_traces', sa.Column('persona_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_agent_traces_persona_id'), 'agent_traces', ['persona_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_traces_persona_id'), table_name='agent_traces')
    op.drop_column('agent_traces', 'persona_id')
