"""persona_add_mcp_server_ids

Revision ID: 95f0b4960b50
Revises: 621a250ffa68
Create Date: 2026-07-05 17:08:01.950828

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '95f0b4960b50'
down_revision: Union[str, None] = '621a250ffa68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_personas', sa.Column('mcp_server_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade() -> None:
    op.drop_column('agent_personas', 'mcp_server_ids')
