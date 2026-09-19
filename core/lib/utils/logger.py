# core/lib/utils/logger.py
import logging


class ErrorFormatter(logging.Formatter):
    """Форматтер ошибок как в MCUB: модуль + короткое сообщение."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        if record.exc_info:
            exc = record.exc_info[1]
            base = f"{type(exc).__name__}: {exc}"
        return base
