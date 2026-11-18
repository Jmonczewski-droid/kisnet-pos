"""devices (printers and monitors)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('jobs', sa.String(), nullable=False),
        sa.Column('host', sa.String(), nullable=True),
        sa.Column('port', sa.Integer(), nullable=True),
        sa.Column('platform', sa.String(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('pairing_code', sa.String(), nullable=True),
        sa.Column('pairing_expires_at', sa.DateTime(), nullable=True),
        sa.Column('token_hash', sa.String(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('pairing_code'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index(op.f('ix_devices_id'), 'devices', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_devices_id'), table_name='devices')
    op.drop_table('devices')
