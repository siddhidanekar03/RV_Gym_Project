import logging
import sys
import re
from contextvars import ContextVar
from backend.app.core.config import settings

# Request Correlation ID Context Variable
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


class StructuredFormatter(logging.Formatter):
    """Clean structured log formatter with standardized layout, correlation IDs, and redaction."""

    REDACTION_PATTERNS = [
        (re.compile(r'(password["\':\s=]+)([^"\'\s,;{}]+)', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(secret_key["\':\s=]+)([^"\'\s,;{}]+)', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(session_token["\':\s=]+)([^"\'\s,;{}]+)', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(authorization:\s*bearer\s+)([^"\'\s,;{}]+)', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(rvf_session=)([^"\'\s;]+)', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(rvf_csrf_token=)([^"\'\s;]+)', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(weight_kg["\':\s=]+)([0-9.]+)', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(body_fat_percentage["\':\s=]+)([0-9.]+)', re.IGNORECASE), r'\1[REDACTED]'),
    ]

    def redact(self, message: str) -> str:
        if not message:
            return ""
        for pattern, replacement in self.REDACTION_PATTERNS:
            message = pattern.sub(replacement, message)
        return message

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        level = record.levelname.ljust(8)
        name = record.name
        message = self.redact(record.getMessage())
        corr_id = correlation_id_ctx.get()

        base = f"[{timestamp}] [{level}] [{name}] [corr_id:{corr_id}] {message}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging() -> None:
    """Initialize centralized logging handlers and level."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers on reload
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(handler)

    # Set external libraries to warning to keep logs readable
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.ENVIRONMENT == "development" else logging.WARNING
    )


logger = logging.getLogger("rvfitness")
