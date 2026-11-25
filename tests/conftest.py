from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest

from radar.config import Settings
from radar.main import create_app


@pytest.fixture
def migration(tmp_path):
    path = tmp_path / "radar_test.sqlite3"
    config = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
    config.attributes["database_path"] = path
    return config, path


@pytest.fixture
def app(migration):
    config, path = migration
    command.upgrade(config, "head")
    return create_app(Settings(database_path=path))


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample():
    def make(number=1, **overrides):
        return {
            "source_code": "manual_other",
            "external_id": f"sim-{number}",
            "title": f"模拟需求 {number}",
            "content": f"模拟内容 {number}",
            "original_url": f"https://radar.invalid/test/{number}",
            "published_at": "2026-11-25T09:00:00+08:00",
            "data_type": "post",
            "is_simulated": True,
        } | overrides

    return make
