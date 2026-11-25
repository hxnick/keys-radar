from alembic import command
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from radar.db import make_engine
from radar.models import Base, BusinessOpportunity, DataSource, EvidenceRecord, OpportunityEvidence, RawPost

EXPECTED_TABLES = {
    "analysis_runs",
    "business_opportunities",
    "data_sources",
    "demand_signals",
    "evidence_records",
    "opportunity_evidence",
    "raw_posts",
}


def test_sqlite_initializes_from_empty_directory(migration):
    config, path = migration
    assert not path.exists()
    command.upgrade(config, "head")
    engine = make_engine(path)
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert set(inspect(connection).get_table_names()) == EXPECTED_TABLES | {"alembic_version"}
        assert connection.scalars(select(DataSource.code)).all().count("manual_other") == 1
        for table in EXPECTED_TABLES - {"data_sources"}:
            assert connection.scalar(select(text("count(*)")).select_from(Base.metadata.tables[table])) == 0
    engine.dispose()


def test_migration_reapply_and_metadata_agreement(migration):
    config, path = migration
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    engine = make_engine(path)
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0001"
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    command.check(config)
    engine.dispose()


@pytest.mark.parametrize("constraint", ["external_id", "original_url", "content_hash", "data_type"])
def test_raw_post_constraints(app, client, sample, constraint):
    response = client.post("/api/v1/raw-posts", json=sample())
    assert response.status_code == 201
    with app.state.sessions() as session:
        saved = session.get(RawPost, response.json()["id"])
        fields = {
            "data_source_id": saved.data_source_id,
            "external_id": "sim-row-2",
            "title": "模拟约束测试",
            "content": "模拟约束内容",
            "original_url": "https://radar.invalid/constraint",
            "collection_method": "manual_single",
            "content_hash": "a" * 64,
            "data_type": "review",
            "is_simulated": True,
        }
        fields[constraint] = "unknown" if constraint == "data_type" else getattr(saved, constraint)
        session.add(RawPost(**fields))
        with pytest.raises(IntegrityError):
            session.flush()


@pytest.mark.parametrize("mismatch", ["dangling", "source", "simulation"])
def test_evidence_requires_matching_post_source_and_simulation(app, client, sample, mismatch):
    post = client.post("/api/v1/raw-posts", json=sample()).json()
    with app.state.sessions() as session:
        source_id = session.scalar(select(DataSource.id).where(DataSource.code == "v2ex"))
        session.add(EvidenceRecord(
            evidence_type="manual_validation",
            data_source_id=source_id if mismatch == "source" else post["data_source_id"],
            raw_post_id=999 if mismatch == "dangling" else post["id"],
            original_url=post["original_url"],
            summary="模拟证据关联约束",
            is_simulated=mismatch != "simulation",
        ))
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            session.flush()


def test_opportunity_evidence_integrity(app, client, sample):
    post = client.post("/api/v1/raw-posts", json=sample()).json()
    with app.state.sessions() as session:
        opportunity = BusinessOpportunity(
            product_name="模拟机会",
            positioning="模拟定位",
            target_users="模拟用户",
            pain_point="模拟痛点",
            use_case="模拟场景",
            is_simulated=True,
        )
        session.add(opportunity)
        session.flush()
        opportunity_id = opportunity.id
        evidence_id = post["evidence"][0]["id"]
        session.add(OpportunityEvidence(
            opportunity_id=opportunity_id, evidence_id=evidence_id, is_simulated=True
        ))
        session.commit()
        assert session.get(OpportunityEvidence, (opportunity_id, evidence_id)).is_simulated
        # Mislabel a simulated link in an invalid write, then roll it back.
        saved = session.get(OpportunityEvidence, (opportunity_id, evidence_id))
        saved.is_simulated = False
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            session.flush()
