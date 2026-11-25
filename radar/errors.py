import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException

from radar.schemas import ErrorInfo, ErrorResponse, ValidationIssue

logger = logging.getLogger("radar")


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, *, existing_id: int | None = None):
        super().__init__(message)
        self.status = status
        self.info = ErrorInfo(code=code, message=message, existing_id=existing_id)


def validation_fields(errors: list) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            field=".".join(map(str, error["loc"])).encode("utf-8", errors="replace").decode("utf-8"),
            message=error["msg"],
        )
        for error in errors
    ]


def error_response(status: int, info: ErrorInfo, headers=None) -> JSONResponse:
    body = ErrorResponse(error=info).model_dump(exclude_none=True)
    return JSONResponse(status_code=status, content=body, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error(_request: Request, exc: APIError) -> JSONResponse:
        return error_response(exc.status, exc.info)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422,
            ErrorInfo(
                code="validation_error",
                message="Request validation failed",
                details=validation_fields(exc.errors()),
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(
            exc.status_code,
            ErrorInfo(code="http_error", message=str(exc.detail)),
            headers=exc.headers,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database operation failed (%s)", type(exc).__name__)
        if isinstance(exc, OperationalError):
            sqlite_code = getattr(exc.orig, "sqlite_errorcode", 0)
            if (sqlite_code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                return error_response(
                    503, ErrorInfo(code="database_busy", message="Database is busy. Retry the request.")
                )
        return error_response(
            500, ErrorInfo(code="database_error", message="Database operation failed")
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unexpected request error (%s)", type(exc).__name__)
        return error_response(500, ErrorInfo(code="internal_error", message="Internal server error"))
