from enum import StrEnum


class DataType(StrEnum):
    POST = "post"
    COMMENT = "comment"
    REVIEW = "review"
    FEATURE_REQUEST = "feature_request"
    SERVICE_REQUEST = "service_request"
    OTHER = "other"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"


class CollectionMethod(StrEnum):
    SINGLE = "manual_single"
    JSON = "manual_json"
    CSV = "manual_csv"
