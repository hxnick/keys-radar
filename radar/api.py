from collections.abc import Generator
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from radar.constants import CollectionMethod, DataType, VerificationStatus
from radar.errors import APIError
from radar.imports import (
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    import_batch,
    import_single,
    parse_csv,
    parse_json,
    post_detail,
)
from radar.models import Base, DataSource, EvidenceRecord, RawPost
from radar.schemas import (
    DataCounts,
    DataSourceOut,
    ErrorResponse,
    HealthOut,
    ImportResult,
    Page,
    RawPostDetail,
    RawPostIn,
    RawPostSummary,
    StatsOut,
)

router = APIRouter(responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
logger = logging.getLogger("radar")


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.sessions() as session:
        yield session


Database = Annotated[Session, Depends(get_session)]
PageNumber = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/health")
def health() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/ready", responses={503: {"model": ErrorResponse}})
def ready(session: Database) -> HealthOut:
    try:
        for table in Base.metadata.sorted_tables:
            session.execute(select(table).limit(0))
    except SQLAlchemyError as exc:
        logger.warning("Readiness check failed (%s)", type(exc).__name__)
        raise APIError(503, "database_not_ready", "Database schema is unavailable. Run migrations.") from exc
    return HealthOut(status="ready")


@router.get("/api/v1/data-sources")
def list_sources(
    session: Database, page: PageNumber = 1, page_size: PageSize = 50
) -> Page[DataSourceOut]:
    session.execute(text("BEGIN"))
    total = session.scalar(select(func.count()).select_from(DataSource))
    sources = session.scalars(
        select(DataSource).order_by(DataSource.code).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[DataSourceOut](
        items=[DataSourceOut.model_validate(source) for source in sources],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/api/v1/raw-posts",
    status_code=201,
    responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def create_post(data: RawPostIn, session: Database) -> RawPostDetail:
    return import_single(session, data)


@router.post(
    "/api/v1/raw-posts/import",
    responses={413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": {
                    "type": "array", "minItems": 1, "maxItems": MAX_IMPORT_ROWS,
                    "items": {"$ref": "#/components/schemas/RawPostIn"},
                }},
                "text/csv": {"schema": {"type": "string"}},
            },
        }
    },
)
async def create_posts(request: Request, session: Database) -> ImportResult:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in ("application/json", "text/csv"):
        raise APIError(415, "unsupported_media_type", "Use application/json or text/csv")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_IMPORT_BYTES:
            raise APIError(413, "batch_too_large", "Batch body exceeds 5 MiB")
        body.extend(chunk)

    def process_batch() -> ImportResult:
        if content_type == "application/json":
            return import_batch(session, parse_json(body), CollectionMethod.JSON)
        return import_batch(session, parse_csv(body), CollectionMethod.CSV)

    return await run_in_threadpool(process_batch)


@router.get("/api/v1/raw-posts")
def list_posts(
    session: Database,
    page: PageNumber = 1,
    page_size: PageSize = 50,
    source_code: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_]{0,63}$")] = None,
    data_type: DataType | None = None,
    verification_status: VerificationStatus | None = None,
    is_simulated: bool | None = None,
) -> Page[RawPostSummary]:
    filters = [
        column == value
        for column, value in (
            (DataSource.code, source_code),
            (RawPost.data_type, data_type),
            (RawPost.verification_status, verification_status),
            (RawPost.is_simulated, is_simulated),
        )
        if value is not None
    ]
    session.execute(text("BEGIN"))
    total = session.scalar(
        select(func.count()).select_from(RawPost).join(DataSource).where(*filters)
    )
    columns = [RawPost.__table__.c[name] for name in RawPostSummary.model_fields if name != "source_code"]
    rows = session.execute(
        select(*columns, DataSource.code.label("source_code"))
        .join(DataSource)
        .where(*filters)
        .order_by(RawPost.imported_at.desc(), RawPost.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).mappings()
    return Page[RawPostSummary](
        items=[RawPostSummary.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/api/v1/raw-posts/{id}", responses={404: {"model": ErrorResponse}})
def get_post(
    id: Annotated[int, Path(ge=1, le=2**63 - 1)], session: Database
) -> RawPostDetail:
    session.execute(text("BEGIN"))
    row = session.execute(
        select(RawPost, DataSource.code).join(DataSource).where(RawPost.id == id)
    ).one_or_none()
    if row is None:
        raise APIError(404, "post_not_found", "Post was not found")
    post, source_code = row
    evidence = session.scalars(
        select(EvidenceRecord).where(EvidenceRecord.raw_post_id == id).order_by(EvidenceRecord.id)
    ).all()
    return post_detail(post, source_code, evidence)


@router.get("/api/v1/stats")
def stats(session: Database) -> StatsOut:
    def counts_by_kind(model):
        return (
            select(model.is_simulated, func.count().label("count"))
            .select_from(model)
            .group_by(model.is_simulated)
        )

    session.execute(text("BEGIN"))
    posts = dict(session.execute(counts_by_kind(RawPost)).tuples().all())
    evidence = dict(session.execute(counts_by_kind(EvidenceRecord)).tuples().all())
    return StatsOut(
        real=DataCounts(raw_posts=posts.get(False, 0), evidence_records=evidence.get(False, 0)),
        simulated=DataCounts(raw_posts=posts.get(True, 0), evidence_records=evidence.get(True, 0)),
    )
