"""skill_add_is_public_call_count_storage_path

Revision ID: 167fe74c435c
Revises: e4ea03bcb371
Create Date: 2026-07-04 15:19:43.166535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '167fe74c435c'
down_revision: Union[str, None] = 'e4ea03bcb371'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('skills', sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('skills', sa.Column('call_count', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('skills', sa.Column('storage_path', sa.String(length=512), nullable=True))
    op.create_index(op.f('ix_skills_is_public'), 'skills', ['is_public'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_skills_is_public'), table_name='skills')
    op.drop_column('skills', 'storage_path')
    op.drop_column('skills', 'call_count')
    op.drop_column('skills', 'is_public')
