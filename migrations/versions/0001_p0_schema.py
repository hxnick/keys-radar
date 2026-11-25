"""Create the seven P0 tables and the manual source catalog.

Revision ID: 0001
Create Date: 2026-11-25 11:45:54.466844
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('analysis_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_type', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('input_ref', sa.Text(), nullable=True),
        sa.Column('model_version', sa.String(length=120), nullable=True),
        sa.Column('result_ref', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('pending','running','succeeded','failed')", name='ck_analysis_runs_status'),
        sa.CheckConstraint('finished_at IS NULL OR finished_at >= started_at', name='ck_analysis_runs_finished_at'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_runs'))
    )
    op.create_index('ix_analysis_runs_status_started_at', 'analysis_runs', ['status', 'started_at'], unique=False)
    op.create_table('business_opportunities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_name', sa.String(length=200), nullable=False),
        sa.Column('positioning', sa.Text(), nullable=False),
        sa.Column('target_users', sa.Text(), nullable=False),
        sa.Column('pain_point', sa.Text(), nullable=False),
        sa.Column('use_case', sa.Text(), nullable=False),
        sa.Column('validation_status', sa.String(length=24), server_default='pending', nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.CheckConstraint('is_simulated IN (0, 1)', name='ck_business_opportunities_is_simulated'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("validation_status IN ('pending','in_progress','validated','rejected')", name='ck_business_opportunities_status'),
        sa.CheckConstraint('length(trim(product_name)) > 0', name='ck_business_opportunities_name'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_business_opportunities')),
        sa.UniqueConstraint('id', 'is_simulated', name='uq_business_opportunities_simulation_parent')
    )
    op.create_table('data_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.CheckConstraint('length(code) BETWEEN 1 AND 64', name='ck_data_sources_code'),
        sa.CheckConstraint('length(trim(name)) > 0', name='ck_data_sources_name'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_data_sources')),
        sa.UniqueConstraint('code', name=op.f('uq_data_sources_code'))
    )
    op.create_table('raw_posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('data_source_id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=True),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('original_url', sa.String(length=2083), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=False),
        sa.Column('collection_method', sa.String(length=20), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('data_type', sa.String(length=32), nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.CheckConstraint('is_simulated IN (0, 1)', name='ck_raw_posts_is_simulated'),
        sa.Column('verification_status', sa.String(length=16), server_default='unverified', nullable=False),
        sa.CheckConstraint("collection_method IN ('manual_single','manual_json','manual_csv')", name='ck_raw_posts_collection_method'),
        sa.CheckConstraint("data_type IN ('post','comment','review','feature_request','service_request','other')", name='ck_raw_posts_data_type'),
        sa.CheckConstraint("verification_status IN ('unverified','verified','rejected')", name='ck_raw_posts_verification_status'),
        sa.CheckConstraint('length(content_hash) = 64', name='ck_raw_posts_hash'),
        sa.CheckConstraint('length(trim(content)) BETWEEN 1 AND 50000', name='ck_raw_posts_content'),
        sa.CheckConstraint('length(trim(title)) BETWEEN 1 AND 300', name='ck_raw_posts_title'),
        sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id'], name=op.f('fk_raw_posts_data_source_id_data_sources')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_raw_posts')),
        sa.UniqueConstraint('data_source_id', 'is_simulated', 'content_hash', name='uq_raw_posts_hash'),
        sa.UniqueConstraint('data_source_id', 'is_simulated', 'external_id', name='uq_raw_posts_external'),
        sa.UniqueConstraint('data_source_id', 'is_simulated', 'original_url', name='uq_raw_posts_url'),
        sa.UniqueConstraint('id', 'data_source_id', 'is_simulated', name='uq_raw_posts_evidence_parent')
    )
    op.create_index(op.f('ix_raw_posts_data_source_id'), 'raw_posts', ['data_source_id'], unique=False)
    op.create_index(op.f('ix_raw_posts_data_type'), 'raw_posts', ['data_type'], unique=False)
    op.create_index('ix_raw_posts_imported_at_id', 'raw_posts', ['imported_at', 'id'], unique=False)
    op.create_index(op.f('ix_raw_posts_is_simulated'), 'raw_posts', ['is_simulated'], unique=False)
    op.create_index(op.f('ix_raw_posts_verification_status'), 'raw_posts', ['verification_status'], unique=False)
    op.create_table('demand_signals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('raw_post_id', sa.Integer(), nullable=False),
        sa.Column('scenario', sa.Text(), nullable=True),
        sa.Column('pain_point', sa.Text(), nullable=True),
        sa.Column('evidence_grade', sa.String(length=1), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("evidence_grade IN ('S','A','B','C','D')", name='ck_demand_signals_grade'),
        sa.ForeignKeyConstraint(['raw_post_id'], ['raw_posts.id'], name=op.f('fk_demand_signals_raw_post_id_raw_posts')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_demand_signals'))
    )
    op.create_index(op.f('ix_demand_signals_raw_post_id'), 'demand_signals', ['raw_post_id'], unique=False)
    op.create_table('evidence_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('raw_post_id', sa.Integer(), nullable=False),
        sa.Column('evidence_type', sa.String(length=32), nullable=False),
        sa.Column('data_source_id', sa.Integer(), nullable=False),
        sa.Column('original_url', sa.String(length=2083), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('acquired_at', sa.DateTime(), nullable=False),
        sa.Column('credibility_status', sa.String(length=16), server_default='unverified', nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.CheckConstraint('is_simulated IN (0, 1)', name='ck_evidence_records_is_simulated'),
        sa.CheckConstraint("credibility_status IN ('unverified','verified','rejected')", name='ck_evidence_records_credibility_status'),
        sa.CheckConstraint('length(trim(summary)) > 0', name='ck_evidence_records_summary'),
        sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id'], name=op.f('fk_evidence_records_data_source_id_data_sources')),
        sa.ForeignKeyConstraint(['raw_post_id', 'data_source_id', 'is_simulated'], ['raw_posts.id', 'raw_posts.data_source_id', 'raw_posts.is_simulated'], name='fk_evidence_records_raw_post'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_records')),
        sa.UniqueConstraint('id', 'is_simulated', name='uq_evidence_records_simulation_parent'),
        sa.UniqueConstraint('raw_post_id', 'evidence_type', name='uq_evidence_records_post_type')
    )
    op.create_index(op.f('ix_evidence_records_is_simulated'), 'evidence_records', ['is_simulated'], unique=False)
    op.create_table('opportunity_evidence',
        sa.Column('opportunity_id', sa.Integer(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.CheckConstraint('is_simulated IN (0, 1)', name='ck_opportunity_evidence_is_simulated'),
        sa.ForeignKeyConstraint(['evidence_id', 'is_simulated'], ['evidence_records.id', 'evidence_records.is_simulated'], name='fk_opportunity_evidence_evidence'),
        sa.ForeignKeyConstraint(['opportunity_id', 'is_simulated'], ['business_opportunities.id', 'business_opportunities.is_simulated'], name='fk_opportunity_evidence_opportunity'),
        sa.PrimaryKeyConstraint('opportunity_id', 'evidence_id', name=op.f('pk_opportunity_evidence'))
    )
    op.create_index(op.f('ix_opportunity_evidence_evidence_id'), 'opportunity_evidence', ['evidence_id'], unique=False)


    source_catalog = sa.table(
        "data_sources", sa.column("code", sa.String()), sa.column("name", sa.String())
    )
    op.bulk_insert(
        source_catalog,
        [
            {"code": "manual_other", "name": "其他人工来源"},
            {"code": "xiaohongshu", "name": "小红书"},
            {"code": "zhihu", "name": "知乎"},
            {"code": "v2ex", "name": "V2EX"},
            {"code": "coolapk", "name": "酷安"},
            {"code": "smzdm", "name": "什么值得买"},
            {"code": "xianyu", "name": "闲鱼"},
            {"code": "douyin", "name": "抖音"},
            {"code": "china_app_store", "name": "国内软件应用商店"},
            {"code": "reddit", "name": "Reddit"},
            {"code": "product_hunt", "name": "Product Hunt"},
            {"code": "hacker_news", "name": "Hacker News"},
            {"code": "indie_hackers", "name": "Indie Hackers"},
            {"code": "github", "name": "GitHub Issues / Discussions"},
            {"code": "apple_app_store", "name": "Apple App Store"},
            {"code": "google_play", "name": "Google Play"},
            {"code": "chrome_web_store", "name": "Chrome Web Store"},
        ],
    )


def downgrade() -> None:
    op.drop_table('opportunity_evidence')
    op.drop_table('evidence_records')
    op.drop_table('demand_signals')
    op.drop_table('raw_posts')
    op.drop_table('data_sources')
    op.drop_table('business_opportunities')
    op.drop_table('analysis_runs')
