from typing import ClassVar

from src.structs.enums import ErrorTypes


class AppError(Exception):
    error_type: ClassVar[ErrorTypes] = ErrorTypes.INTERNAL

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    error_type = ErrorTypes.NOT_FOUND


class UnsupportedError(AppError):
    error_type = ErrorTypes.UNSUPPORTED


class UnauthorizedError(AppError):
    error_type = ErrorTypes.UNAUTHORIZED


class ForbiddenError(AppError):
    error_type = ErrorTypes.FORBIDDEN


class InvalidCodeError(AppError):
    error_type = ErrorTypes.INVALID_CODE


class InvalidEmailError(AppError):
    error_type = ErrorTypes.INVALID_EMAIL


class EmailUnavailableError(AppError):
    error_type = ErrorTypes.EMAIL_UNAVAILABLE


class TooManyRequestsError(AppError):
    error_type = ErrorTypes.RATE_LIMITED

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SummarizerError(AppError):
    error_type = ErrorTypes.INTERNAL


class SummarizerBusyError(SummarizerError):
    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        daily: bool = False,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.daily = daily


class ExchangeError(AppError):
    error_type = ErrorTypes.EXCHANGE_ERROR


class ExchangeUnavailableError(ExchangeError):
    error_type = ErrorTypes.EXCHANGE_UNAVAILABLE


class ExchangeTimeoutError(ExchangeError):
    error_type = ErrorTypes.EXCHANGE_TIMEOUT


class ExchangeBlockedError(ExchangeUnavailableError):
    error_type = ErrorTypes.EXCHANGE_BLOCKED
