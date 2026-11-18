"""look-in portal sessions

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'lookin_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index(op.f('ix_lookin_sessions_id'), 'lookin_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_lookin_sessions_employee_id'), 'lookin_sessions', ['employee_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_lookin_sessions_employee_id'), table_name='lookin_sessions')
    op.drop_index(op.f('ix_lookin_sessions_id'), table_name='lookin_sessions')
    op.drop_table('lookin_sessions')
