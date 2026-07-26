from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorDetail, ErrorResponse, ValidationErrorItem


class APIException(Exception):
    """Base exception for API-layer errors."""

    def __init__(
        self,
        status_code: int = 500,
        code: str = "internal_error",
        message: str = "An internal error occurred",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class NotFoundError(APIException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(status_code=404, code="not_found", message=message)


class BadRequestError(APIException):
    def __init__(self, message: str = "Bad request") -> None:
        super().__init__(status_code=400, code="bad_request", message=message)


class ServiceUnavailableError(APIException):
    def __init__(self, message: str = "Service unavailable") -> None:
        super().__init__(
            status_code=503, code="service_unavailable", message=message,
        )


def _error_response(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error=ErrorDetail(code=code, message=message),
        ).model_dump(),
    )


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.code, message=exc.message, details=exc.details,
            ),
        ).model_dump(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError,
) -> JSONResponse:
    items: list[ValidationErrorItem] = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "Unknown validation error")
        items.append(ValidationErrorItem(field=field, message=msg))
    return JSONResponse(
        status_code=422,
        content={
            "error": ErrorDetail(
                code="validation_error",
                message="Request validation failed",
            ).model_dump(),
            "details": [item.model_dump() for item in items],
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(
                code="internal_error",
                message="An unexpected error occurred",
            ),
        ).model_dump(),
    )
