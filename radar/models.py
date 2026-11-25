from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from radar.db import UtcDateTime, utc_now


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        CheckConstraint("length(code) BETWEEN 1 AND 64", name="ck_data_sources_code"),
        CheckConstraint("length(trim(name)) > 0", name="ck_data_sources_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))


class RawPost(Base):
    __tablename__ = "raw_posts"
    __table_args__ = (
        CheckConstraint("is_simulated IN (0, 1)", name="ck_raw_posts_is_simulated"),
        UniqueConstraint("data_source_id", "is_simulated", "external_id", name="uq_raw_posts_external"),
        UniqueConstraint("data_source_id", "is_simulated", "original_url", name="uq_raw_posts_url"),
        UniqueConstraint("data_source_id", "is_simulated", "content_hash", name="uq_raw_posts_hash"),
        UniqueConstraint("id", "data_source_id", "is_simulated", name="uq_raw_posts_evidence_parent"),
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 300", name="ck_raw_posts_title"),
        CheckConstraint("length(trim(content)) BETWEEN 1 AND 50000", name="ck_raw_posts_content"),
        CheckConstraint("length(content_hash) = 64", name="ck_raw_posts_hash"),
        CheckConstraint(
            "data_type IN ('post','comment','review','feature_request','service_request','other')",
            name="ck_raw_posts_data_type",
        ),
        CheckConstraint(
            "collection_method IN ('manual_single','manual_json','manual_csv')",
            name="ck_raw_posts_collection_method",
        ),
        CheckConstraint(
            "verification_status IN ('unverified','verified','rejected')",
            name="ck_raw_posts_verification_status",
        ),
        Index("ix_raw_posts_imported_at_id", "imported_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    original_url: Mapped[str] = mapped_column(String(2083))
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    imported_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    collection_method: Mapped[str] = mapped_column(String(20))
    content_hash: Mapped[str] = mapped_column(String(64))
    data_type: Mapped[str] = mapped_column(String(32), index=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, index=True)
    verification_status: Mapped[str] = mapped_column(
        String(16), index=True, server_default="unverified"
    )


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    __table_args__ = (
        CheckConstraint("is_simulated IN (0, 1)", name="ck_evidence_records_is_simulated"),
        ForeignKeyConstraint(
            ["raw_post_id", "data_source_id", "is_simulated"],
            ["raw_posts.id", "raw_posts.data_source_id", "raw_posts.is_simulated"],
            name="fk_evidence_records_raw_post",
        ),
        UniqueConstraint("id", "is_simulated", name="uq_evidence_records_simulation_parent"),
        UniqueConstraint("raw_post_id", "evidence_type", name="uq_evidence_records_post_type"),
        CheckConstraint("length(trim(summary)) > 0", name="ck_evidence_records_summary"),
        CheckConstraint(
            "credibility_status IN ('unverified','verified','rejected')",
            name="ck_evidence_records_credibility_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_post_id: Mapped[int] = mapped_column()
    evidence_type: Mapped[str] = mapped_column(String(32))
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    original_url: Mapped[str] = mapped_column(String(2083))
    summary: Mapped[str] = mapped_column(Text)
    acquired_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    credibility_status: Mapped[str] = mapped_column(String(16), server_default="unverified")
    is_simulated: Mapped[bool] = mapped_column(Boolean, index=True)


class DemandSignal(Base):
    __tablename__ = "demand_signals"
    __table_args__ = (
        CheckConstraint("evidence_grade IN ('S','A','B','C','D')", name="ck_demand_signals_grade"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_post_id: Mapped[int] = mapped_column(ForeignKey("raw_posts.id"), index=True)
    scenario: Mapped[str | None] = mapped_column(Text)
    pain_point: Mapped[str | None] = mapped_column(Text)
    evidence_grade: Mapped[str | None] = mapped_column(String(1))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)


class BusinessOpportunity(Base):
    __tablename__ = "business_opportunities"
    __table_args__ = (
        CheckConstraint("is_simulated IN (0, 1)", name="ck_business_opportunities_is_simulated"),
        UniqueConstraint("id", "is_simulated", name="uq_business_opportunities_simulation_parent"),
        CheckConstraint("length(trim(product_name)) > 0", name="ck_business_opportunities_name"),
        CheckConstraint(
            "validation_status IN ('pending','in_progress','validated','rejected')",
            name="ck_business_opportunities_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_name: Mapped[str] = mapped_column(String(200))
    positioning: Mapped[str] = mapped_column(Text)
    target_users: Mapped[str] = mapped_column(Text)
    pain_point: Mapped[str] = mapped_column(Text)
    use_case: Mapped[str] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(String(24), server_default="pending")
    is_simulated: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now, onupdate=utc_now)


class OpportunityEvidence(Base):
    __tablename__ = "opportunity_evidence"
    __table_args__ = (
        CheckConstraint("is_simulated IN (0, 1)", name="ck_opportunity_evidence_is_simulated"),
        ForeignKeyConstraint(
            ["opportunity_id", "is_simulated"],
            ["business_opportunities.id", "business_opportunities.is_simulated"],
            name="fk_opportunity_evidence_opportunity",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "is_simulated"], ["evidence_records.id", "evidence_records.is_simulated"],
            name="fk_opportunity_evidence_evidence",
        ),
    )

    opportunity_id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed')", name="ck_analysis_runs_status"
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="ck_analysis_runs_finished_at"
        ),
        Index("ix_analysis_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    input_ref: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(120))
    result_ref: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    error_summary: Mapped[str | None] = mapped_column(Text)
