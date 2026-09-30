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
