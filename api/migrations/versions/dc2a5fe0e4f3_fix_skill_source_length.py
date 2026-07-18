"""fix_skill_source_length

Revision ID: dc2a5fe0e4f3
Revises: f735e480fec4
Create Date: 2026-07-18 17:41:22.696734

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc2a5fe0e4f3'
down_revision: Union[str, None] = 'f735e480fec4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'skills', 'source',
        existing_type=sa.String(10),
        type_=sa.String(16),
        existing_nullable=False,
        existing_server_default=sa.text("'custom'"),
    )


def downgrade() -> None:
    op.alter_column(
        'skills', 'source',
        existing_type=sa.String(16),
        type_=sa.String(10),
        existing_nullable=False,
        existing_server_default=sa.text("'custom'"),
    )
