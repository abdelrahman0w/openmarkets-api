from fastapi import FastAPI
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse

from src.exceptions.custom_exceptions import AppError
from src.exceptions.custom_exceptions import ExchangeError
from src.exceptions.custom_exceptions import ExchangeTimeoutError
from src.exceptions.custom_exceptions import ExchangeUnavailableError
from src.exceptions.custom_exceptions import NotFoundError
from src.exceptions.custom_exceptions import UnsupportedError
from src.providers import logger
from src.structs.enums import ErrorTypes
from src.structs.models import ErrorDetail
from src.structs.models import ErrorResponse


STATUS_CODES: dict[type[AppError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    UnsupportedError: status.HTTP_400_BAD_REQUEST,
    ExchangeTimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    ExchangeUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    ExchangeError: status.HTTP_502_BAD_GATEWAY,
}


def status_code_for(exc: AppError) -> int:
    for cls in type(exc).__mro__:
        if cls in STATUS_CODES:
            return STATUS_CODES[cls]

    return status.HTTP_500_INTERNAL_SERVER_ERROR


def error_response(
    status_code: int,
    error_type: ErrorTypes,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                type=error_type,
                message=message,
            ),
        ).model_dump(mode="json"),
    )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    status_code = status_code_for(exc)
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.exception(
            "[Error] Request Failure",
            exc_info=exc,
            error_type=exc.error_type,
        )

    return error_response(
        status_code,
        exc.error_type,
        exc.message,
    )


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "[Error] Unhandled Error",
        exc_info=exc,
    )

    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorTypes.INTERNAL,
        "Something went wrong on our side",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
