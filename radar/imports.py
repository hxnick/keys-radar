from collections.abc import Sequence
import csv
from hashlib import sha256
from io import StringIO
import json
import logging
from typing import NamedTuple

from pydantic import ValidationError
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from radar.constants import CollectionMethod
from radar.db import utc_now
from radar.errors import APIError, validation_fields
from radar.models import DataSource, EvidenceRecord, RawPost
from radar.schemas import ImportIssue, ImportResult, RawPostDetail, RawPostIn, RawPostSummary

logger = logging.getLogger("radar")

MAX_IMPORT_ROWS = 1000
MAX_IMPORT_BYTES = 5 * 1024 * 1024
REQUIRED_COLUMNS = {name for name, field in RawPostIn.model_fields.items() if field.is_required()}


class InputRow(NamedTuple):
    number: int
    payload: object


def parse_json(body: bytes | bytearray) -> list[InputRow]:
    try:
        items = json.loads(body.decode("utf-8-sig"))
    except (ValueError, RecursionError) as exc:
        raise APIError(422, "invalid_json", "Expected a UTF-8 JSON array") from exc
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_IMPORT_ROWS:
        raise APIError(422, "invalid_batch_size", f"Expected an array of 1 to {MAX_IMPORT_ROWS} rows")
    return [InputRow(index, item) for index, item in enumerate(items, start=1)]


def parse_csv(body: bytes | bytearray) -> list[InputRow]:
    rows = []
    try:
        reader = csv.reader(StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader, [])
        if (
            len(set(header)) != len(header)
            or not REQUIRED_COLUMNS.issubset(header)
            or any(name not in RawPostIn.model_fields for name in header)
        ):
            raise APIError(422, "invalid_csv_header", "CSV requires valid, unique column names")
        for values in reader:
            if not values:
                continue
            if len(rows) == MAX_IMPORT_ROWS:
                raise APIError(422, "invalid_batch_size", f"Expected at most {MAX_IMPORT_ROWS} rows")
            row_number = reader.line_num
            if len(values) != len(header):
                rows.append(InputRow(row_number, None))
                continue
            payload = dict(zip(header, values, strict=True))
            payload["is_simulated"] = {"true": True, "false": False}.get(
                payload["is_simulated"].strip().lower()
            )
            for field in ("external_id", "published_at"):
                if field in payload and not payload[field].strip():
                    payload[field] = None
            rows.append(InputRow(row_number, payload))
    except (csv.Error, UnicodeDecodeError) as exc:
        raise APIError(422, "invalid_csv", "Expected well-formed UTF-8 CSV") from exc
    if not rows:
        raise APIError(422, "invalid_batch_size", f"Expected 1 to {MAX_IMPORT_ROWS} rows")
    return rows


def get_source_ids(session: Session) -> dict[str, int]:
    return dict(session.execute(select(DataSource.code, DataSource.id)).tuples().all())


def insert_post(
    session: Session, data: RawPostIn, source_id: int, method: CollectionMethod
) -> tuple[RawPost, EvidenceRecord] | int:
    content_hash = sha256(" ".join(data.content.split()).encode("utf-8")).hexdigest()
    url = str(data.original_url)
    matches = [RawPost.original_url == url, RawPost.content_hash == content_hash]
    if data.external_id is not None:
        matches.append(RawPost.external_id == data.external_id)
    existing_id = session.scalar(
        select(RawPost.id)
        .where(
            RawPost.data_source_id == source_id,
            RawPost.is_simulated == data.is_simulated,
            or_(*matches),
        )
        .order_by(RawPost.id)
        .limit(1)
    )
    if existing_id is not None:
        return existing_id

    imported_at = utc_now()
    post = RawPost(
        data_source_id=source_id,
        external_id=data.external_id,
        title=data.title,
        content=data.content,
        original_url=url,
        published_at=data.published_at,
        imported_at=imported_at,
        collection_method=method,
        content_hash=content_hash,
        data_type=data.data_type,
        is_simulated=data.is_simulated,
    )
    session.add(post)
    session.flush()
    evidence = EvidenceRecord(
        raw_post_id=post.id,
        data_source_id=source_id,
        evidence_type="original_demand",
        original_url=url,
        summary=data.content[:280],
        acquired_at=imported_at,
        is_simulated=data.is_simulated,
    )
    session.add(evidence)
    session.flush()
    return post, evidence


def post_detail(
    post: RawPost, source_code: str, evidence: Sequence[EvidenceRecord]
) -> RawPostDetail:
    fields = RawPostSummary.model_fields.keys() - {"source_code"}
    metadata = {field: getattr(post, field) for field in fields}
    return RawPostDetail.model_validate(
        {**metadata, "source_code": source_code, "content": post.content, "evidence": evidence}
    )


def import_single(session: Session, data: RawPostIn) -> RawPostDetail:
    with session.begin():
        # Reserve the SQLite writer before looking up duplicates. Concurrent imports
        # wait for this transaction and then see its committed keys.
        session.execute(text("BEGIN IMMEDIATE"))
        source_id = get_source_ids(session).get(data.source_code)
        if source_id is None:
            raise APIError(422, "unknown_source", "source_code is absent from the source catalog")
        result = insert_post(session, data, source_id, CollectionMethod.SINGLE)
        if isinstance(result, int):
            raise APIError(409, "duplicate_post", "A matching post already exists", existing_id=result)
        post, evidence = result
        return post_detail(post, data.source_code, [evidence])


def import_batch(
    session: Session, rows: list[InputRow], method: CollectionMethod
) -> ImportResult:
    result = ImportResult(total=len(rows))
    valid_rows = []
    for row in rows:
        if row.payload is None and method == CollectionMethod.CSV:
            result.failed += 1
            result.issues.append(ImportIssue(
                row=row.number, code="invalid_columns", message="Row width differs from the header"
            ))
            continue
        try:
            data = RawPostIn.model_validate(row.payload)
        except ValidationError as exc:
            result.failed += 1
            result.issues.append(ImportIssue(
                row=row.number,
                code="validation_error",
                message="Row validation failed",
                fields=validation_fields(exc.errors()),
            ))
            continue
        valid_rows.append((row.number, data))

    if valid_rows:
        with session.begin():
            session.execute(text("BEGIN IMMEDIATE"))
            source_ids = get_source_ids(session)
            for row_number, data in valid_rows:
                source_id = source_ids.get(data.source_code)
                if source_id is None:
                    result.failed += 1
                    result.issues.append(ImportIssue(
                        row=row_number, code="unknown_source", message="Unknown source_code"
                    ))
                    continue
                outcome = insert_post(session, data, source_id, method)
                if isinstance(outcome, int):
                    result.duplicates += 1
                    result.issues.append(ImportIssue(
                        row=row_number,
                        code="duplicate_post",
                        message="A matching post already exists",
                        existing_id=outcome,
                    ))
                else:
                    result.imported += 1

    result.issues.sort(key=lambda issue: issue.row)
    logger.info(
        "Manual import method=%s total=%d imported=%d duplicates=%d failed=%d",
        method, result.total, result.imported, result.duplicates, result.failed,
    )
    return result
