from datetime import datetime, timezone
import re
from typing import Generic, Literal, TypeVar
import unicodedata

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, StrictBool, field_validator

from radar.constants import CollectionMethod, DataType, VerificationStatus


class RawPostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    external_id: str | None = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=50000)
    original_url: HttpUrl
    published_at: AwareDatetime | None = None
    data_type: DataType
    is_simulated: StrictBool

    @field_validator("source_code", "external_id", "title", "content", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Text must be valid UTF-8") from exc
        if "\x00" in value:
            raise ValueError("Text cannot contain a NUL character")
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()

    @field_validator("external_id")
    @classmethod
    def blank_id_as_null(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("original_url", mode="before")
    @classmethod
    def validate_url_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Expected an HTTP(S) URL")
        value = value.strip()
        scheme = re.match(r"https?://", value, flags=re.IGNORECASE)
        if (
            scheme is None
            or not value[scheme.end():]
            or value[scheme.end()] in "/?#"
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
            or "\\" in value
        ):
            raise ValueError("Expected an absolute HTTP(S) URL with a host")
        return value

    @field_validator("original_url")
    @classmethod
    def reject_url_credentials(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("URL credentials are not allowed")
        return value

    @field_validator("published_at", mode="before")
    @classmethod
    def require_timestamp_format(cls, value: object) -> object:
        if value is not None and (
            not isinstance(value, str) or not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T", value)
        ):
            raise ValueError("Expected an ISO 8601 timestamp with a timezone")
        return value

    @field_validator("published_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        try:
            return value.astimezone(timezone.utc)
        except OverflowError as exc:
            raise ValueError("Timestamp is outside the supported UTC range") from exc


class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class RawPostSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    data_source_id: int
    source_code: str
    external_id: str | None
    title: str
    original_url: str
    published_at: datetime | None
    imported_at: datetime
    collection_method: CollectionMethod
    content_hash: str
    data_type: DataType
    is_simulated: bool
    verification_status: VerificationStatus


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_post_id: int
    data_source_id: int
    evidence_type: str
    original_url: str
    summary: str
    acquired_at: datetime
    credibility_status: VerificationStatus
    is_simulated: bool


class RawPostDetail(RawPostSummary):
    content: str
    evidence: list[EvidenceOut]


Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    page: int
    page_size: int
    total: int


class ValidationIssue(BaseModel):
    field: str
    message: str


class ImportIssue(BaseModel):
    row: int
    code: str
    message: str
    fields: list[ValidationIssue] = Field(default_factory=list)
    existing_id: int | None = None


class ImportResult(BaseModel):
    total: int
    imported: int = 0
    duplicates: int = 0
    failed: int = 0
    issues: list[ImportIssue] = Field(default_factory=list)


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[ValidationIssue] = Field(default_factory=list)
    existing_id: int | None = None


class ErrorResponse(BaseModel):
    error: ErrorInfo


class HealthOut(BaseModel):
    status: Literal["ok", "ready"]


class DataCounts(BaseModel):
    raw_posts: int
    evidence_records: int


class StatsOut(BaseModel):
    real: DataCounts
    simulated: DataCounts
