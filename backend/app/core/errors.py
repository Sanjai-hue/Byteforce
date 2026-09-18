"""Application error types and FastAPI exception handlers.

Rule: users see a short, actionable message. Stack traces, provider payloads and
credentials stay in the backend log.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("reqguard")


class ReqGuardError(Exception):
    """Base class for errors that are safe to show to a user."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class ValidationFailure(ReqGuardError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "validation_failed"


class UnsupportedFileType(ReqGuardError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_file_type"


class FileTooLarge(ReqGuardError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "file_too_large"


class DocumentParseError(ReqGuardError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "document_parse_failed"


class EmptyDocumentError(ReqGuardError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "empty_document"


class NotFoundError(ReqGuardError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(ReqGuardError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class DatabaseError(ReqGuardError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "database_error"


class StorageError(ReqGuardError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "storage_error"


class AIServiceError(ReqGuardError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "ai_service_error"


class AIResponseInvalid(AIServiceError):
    """The model returned something that could not be validated as the expected schema."""

    code = "ai_response_invalid"


class ConfigurationError(ReqGuardError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "not_configured"


class EmbeddingModelError(ReqGuardError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "embedding_model_unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ReqGuardError)
    async def _handle_reqguard_error(_: Request, exc: ReqGuardError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("%s: %s (detail=%s)", exc.code, exc.message, exc.detail)
        else:
            logger.info("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("request validation failed: %s", exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "request_invalid",
                    "message": "The request was not valid. Check the submitted fields and try again.",
                }
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong on our side. The failure has been logged.",
                }
            },
        )
