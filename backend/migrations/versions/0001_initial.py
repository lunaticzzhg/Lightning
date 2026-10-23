"""Initial REQ-001 identity and immutable versions.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('strategies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('canonical_name', sa.String(255), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(36), sa.ForeignKey('strategies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(64), nullable=False),
        sa.Column('zip_bytes', sa.LargeBinary(length=50_000_000), nullable=False),
        sa.UniqueConstraint('strategy_id', 'number'), sa.UniqueConstraint('strategy_id', 'sha256'))


def downgrade():
    op.drop_table('versions')
    op.drop_table('strategies')
