from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
from io import StringIO
from threading import Barrier

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from radar.config import Settings
from radar.imports import MAX_IMPORT_BYTES
from radar.main import create_app

POSTS = "/api/v1/raw-posts"
IMPORTS = f"{POSTS}/import"
STATS = "/api/v1/stats"


def test_health_independent_of_database(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "uninitialized.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_not_ready"


def test_ready_detects_missing_table(app, client):
    assert client.get("/ready").json() == {"status": "ready"}
    with app.state.sessions.begin() as session:
        session.execute(text("DROP TABLE analysis_runs"))
    assert client.get("/ready").status_code == 503


def test_data_sources_pagination(client):
    response = client.get("/api/v1/data-sources", params={"page": 2, "page_size": 3})
    data = response.json()
    assert response.status_code == 200
    assert data["total"] == 17
    assert data["page"] == 2
    assert len(data["items"]) == 3
    assert data["items"] != client.get("/api/v1/data-sources", params={"page_size": 3}).json()["items"]


def test_single_post_and_evidence_detail(client, sample):
    payload = sample(content=" 模拟第一行\r\n模拟第二行  ")
    response = client.post(POSTS, json=payload)
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["content"] == "模拟第一行\n模拟第二行"
    assert item["collection_method"] == "manual_single"
    assert len(item["content_hash"]) == 64
    assert item["is_simulated"] is True
    assert item["verification_status"] == "unverified"
    assert datetime.fromisoformat(item["published_at"]) == datetime(2026, 11, 25, 1, tzinfo=timezone.utc)
    assert datetime.fromisoformat(item["imported_at"]).utcoffset().total_seconds() == 0
    [evidence] = item["evidence"]
    assert evidence["raw_post_id"] == item["id"]
    assert evidence["is_simulated"] is True
    assert evidence["credibility_status"] == "unverified"
    assert evidence["original_url"] == item["original_url"]
    assert evidence["data_source_id"] == item["data_source_id"]
    assert evidence["acquired_at"] == item["imported_at"]
    assert client.get(f"{POSTS}/{item['id']}").json() == item
    assert client.get(f"{POSTS}/9999").status_code == 404


def test_json_import(client, sample):
    response = client.post(IMPORTS, json=[sample(), sample(2)])
    assert response.status_code == 200
    assert response.json() == {"total": 2, "imported": 2, "duplicates": 0, "failed": 0, "issues": []}
    assert all(row["collection_method"] == "manual_json" for row in client.get(POSTS).json()["items"])


def test_csv_import_supports_bom_quotes_newline_and_missing_optional_fields(client, sample):
    row = sample(title="模拟,标题", content="模拟第一行\n模拟第二行", published_at="", external_id="")
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    output.write("模拟错误,缺少列\n")
    response = client.post(
        IMPORTS, content=output.getvalue().encode("utf-8-sig"), headers={"Content-Type": "text/csv"}
    )
    assert response.status_code == 200
    result = response.json()
    assert (result["imported"], result["duplicates"], result["failed"]) == (1, 0, 1)
    assert result["issues"][0]["row"] == 4
    assert result["issues"][0]["code"] == "invalid_columns"
    [summary] = client.get(POSTS).json()["items"]
    saved = client.get(f"{POSTS}/{summary['id']}").json()
    assert saved["collection_method"] == "manual_csv"
    assert saved["title"] == row["title"]
    assert saved["content"] == row["content"]
    assert saved["published_at"] is saved["external_id"] is None


@pytest.mark.parametrize("key", ["external_id", "original_url", "content"])
def test_duplicate_does_not_overwrite(client, sample, key):
    first = client.post(POSTS, json=sample(content="模拟 第一条")).json()
    initial = {
        "external_id": "sim-1", "original_url": "HTTPS://RADAR.INVALID:443/test/1",
        "content": "模拟\n\t第一条",
    }
    duplicate = client.post(POSTS, json=sample(2, **{key: initial[key]}))
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["existing_id"] == first["id"]
    assert client.get(f"{POSTS}/{first['id']}").json() == first
    assert client.get(POSTS).json()["total"] == 1


def test_concurrent_duplicate_import(client, sample):
    barrier = Barrier(2)

    def submit():
        barrier.wait(timeout=5)
        return client.post(POSTS, json=sample()).status_code

    with ThreadPoolExecutor(max_workers=2) as threads:
        codes = list(threads.map(lambda _: submit(), range(2)))
    assert sorted(codes) == [201, 409]
    assert client.get(STATS).json()["simulated"] == {"raw_posts": 1, "evidence_records": 1}


@pytest.mark.parametrize(
    "updates, field",
    [
        ({"title": "  "}, "title"),
        ({"original_url": "file:///tmp/test.txt"}, "original_url"),
        ({"original_url": "https:////radar.invalid/test/1"}, "original_url"),
        ({"original_url": "https://account:pass@radar.invalid/test/1"}, "original_url"),
        ({"published_at": "2026-11-25T08:00:00"}, "published_at"),
        ({"published_at": "0001-01-01T00:00:00+08:00"}, "published_at"),
        ({"content": "模拟\x00文本"}, "content"),
        ({"is_simulated": "true"}, "is_simulated"),
    ],
)
def test_invalid_single_input(client, sample, updates, field):
    response = client.post(POSTS, json=sample(**updates))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == f"body.{field}"
    assert client.get(STATS).json()["simulated"]["evidence_records"] == 0


def test_unknown_source_and_missing_simulated_flag(client, sample):
    unknown = client.post(POSTS, json=sample(source_code="absent"))
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_source"
    payload = sample()
    del payload["is_simulated"]
    assert client.post(POSTS, json=payload).status_code == 422


def test_mixed_batch_reports_rows_and_can_be_retried(client, sample):
    payload = [
        sample(),
        sample(2, content=""),
        sample(3, external_id="sim-1"),
        sample(4, source_code="absent"),
        sample(5),
    ]
    response = client.post(IMPORTS, json=payload)
    assert response.status_code == 200
    summary = response.json()
    assert (summary["total"], summary["imported"], summary["duplicates"], summary["failed"]) == (5, 2, 1, 2)
    assert [(row["row"], row["code"]) for row in summary["issues"]] == [
        (2, "validation_error"), (3, "duplicate_post"), (4, "unknown_source")
    ]
    retried = client.post(IMPORTS, json=payload).json()
    assert (retried["imported"], retried["duplicates"], retried["failed"]) == (0, 3, 2)
    assert client.get(STATS).json()["simulated"] == {"raw_posts": 2, "evidence_records": 2}


def test_unexpected_database_failure_rolls_back_whole_batch(app, client, sample):
    with app.state.sessions.begin() as session:
        session.execute(text("""
            CREATE TRIGGER abort_second_evidence BEFORE INSERT ON evidence_records
            WHEN NEW.summary = '模拟内容 2'
            BEGIN SELECT RAISE(ABORT, 'simulated failure'); END
        """))
    response = client.post(IMPORTS, json=[sample(), sample(2)])
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "database_error"
    assert client.get(STATS).json()["simulated"] == {"raw_posts": 0, "evidence_records": 0}
    with app.state.sessions.begin() as session:
        session.execute(text("DROP TRIGGER abort_second_evidence"))
    assert client.post(IMPORTS, json=[sample(), sample(2)]).json()["imported"] == 2


@pytest.mark.parametrize(
    "content_type, body, status, code",
    [
        ("application/json", b"[", 422, "invalid_json"),
        ("application/json", b"[]", 422, "invalid_batch_size"),
        ("text/csv", b"title,title", 422, "invalid_csv_header"),
        ("text/csv", b"source_code,title,content,original_url,data_type,is_simulated\n\"", 422, "invalid_csv"),
        ("text/plain", b"[]", 415, "unsupported_media_type"),
        ("application/json", b" " * (MAX_IMPORT_BYTES + 1), 413, "batch_too_large"),
    ],
)
def test_invalid_bulk_document(client, content_type, body, status, code):
    response = client.post(IMPORTS, content=body, headers={"Content-Type": content_type})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert client.get(POSTS).json()["total"] == 0


def test_list_pagination_and_combined_filters(client, sample):
    payload = [
        sample(),
        sample(2, data_type="review"),
        sample(3, source_code="v2ex", data_type="review"),
    ]
    assert client.post(IMPORTS, json=payload).json()["imported"] == 3
    query = {"source_code": "manual_other", "data_type": "review", "verification_status": "unverified",
             "is_simulated": "true", "page": 1, "page_size": 1}
    filtered = client.get(POSTS, params=query).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["external_id"] == "sim-2"
    page_one = client.get(POSTS, params={"page": 1, "page_size": 1}).json()
    page_two = client.get(POSTS, params={"page": 2, "page_size": 1}).json()
    assert page_one["total"] == page_two["total"] == 3
    assert page_one["items"][0]["external_id"] == "sim-3"
    assert page_two["items"][0]["external_id"] == "sim-2"
    assert client.get(POSTS, params={"verification_status": "verified"}).json()["total"] == 0
    assert client.get(POSTS, params={"page_size": 101}).json()["error"]["code"] == "validation_error"


def test_simulated_records_excluded_from_real_statistics(client, sample):
    assert client.get(STATS).json() == {
        "real": {"raw_posts": 0, "evidence_records": 0},
        "simulated": {"raw_posts": 0, "evidence_records": 0},
    }
    assert client.post(POSTS, json=sample()).status_code == 201
    assert client.get(POSTS, params={"is_simulated": "false"}).json()["total"] == 0
    assert client.get(POSTS, params={"is_simulated": "true"}).json()["total"] == 1
    assert client.get(STATS).json() == {
        "real": {"raw_posts": 0, "evidence_records": 0},
        "simulated": {"raw_posts": 1, "evidence_records": 1},
    }


def test_openapi_describes_batch_content_and_error_shape(client):
    spec = client.get("/openapi.json").json()
    assert len(spec["paths"]) == 7
    schema = spec["paths"][IMPORTS]["post"]
    assert set(schema["requestBody"]["content"]) == {"application/json", "text/csv"}
    assert schema["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorResponse")
