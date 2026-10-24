"""REQ-002 market data directory.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('market_sources',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('provider', sa.String(255), nullable=False),
        sa.Column('product', sa.String(255), nullable=False),
        sa.UniqueConstraint('provider', 'product'))
    op.create_table('market_datasets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('market_sources.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('market', sa.String(16), nullable=False),
        sa.Column('period', sa.String(16), nullable=False),
        sa.Column('price_mode', sa.String(64), nullable=False),
        sa.Column('adjustment', sa.String(255), nullable=False),
        sa.Column('reference_date', sa.String(10), nullable=False),
        sa.Column('session', sa.String(16), nullable=False),
        sa.UniqueConstraint('source_id', 'market', 'period', 'price_mode', 'adjustment', 'reference_date', 'session'))
    op.create_table('market_drafts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('raw_path', sa.String(255), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('period', sa.String(16), nullable=False),
        sa.Column('market', sa.String(16), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('result', sa.JSON(none_as_null=True), nullable=True))
    op.create_table('market_imports',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('market_datasets.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('draft_id', sa.String(36), sa.ForeignKey('market_drafts.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('raw_path', sa.String(255), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False))
    op.create_table('market_versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('market_datasets.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('import_id', sa.String(36), sa.ForeignKey('market_imports.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('previous_id', sa.String(36), nullable=True),
        sa.Column('parquet_path', sa.String(255), nullable=False),
        sa.Column('parquet_sha256', sa.String(64), nullable=False),
        sa.Column('files', sa.JSON(), nullable=False),
        sa.Column('coverage', sa.JSON(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('warning_rules', sa.JSON(), nullable=False),
        sa.Column('warnings', sa.JSON(), nullable=False),
        sa.UniqueConstraint('dataset_id', 'number'))

def downgrade():
    for table in ('market_versions', 'market_imports', 'market_drafts', 'market_datasets', 'market_sources'):
        op.drop_table(table)
