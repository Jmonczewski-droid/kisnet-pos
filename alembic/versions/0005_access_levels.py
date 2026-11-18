"""access levels, self-set PINs, lockout and owner two-step sign-in

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('access', sa.String(), nullable=False, server_default='team'))
        batch_op.add_column(sa.Column('must_change_pin', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('locked_until', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('totp_secret', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('totp_last_step', sa.Integer(), nullable=True))

    # Everyone who could work the admin position becomes a manager...
    op.execute("UPDATE employees SET access = 'manager' "
               "WHERE role = 'admin' OR (',' || positions || ',') LIKE '%,admin,%'")
    # ...and the longest-standing active one becomes the owner, so someone can always reach the database.
    op.execute("UPDATE employees SET access = 'owner' WHERE id = ("
               "SELECT id FROM employees WHERE access = 'manager' "
               "ORDER BY (archived_at IS NOT NULL), (active = 0), id LIMIT 1)")


def downgrade() -> None:
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_column('totp_last_step')
        batch_op.drop_column('totp_enabled')
        batch_op.drop_column('totp_secret')
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_attempts')
        batch_op.drop_column('must_change_pin')
        batch_op.drop_column('access')
