import logging
import sys
from backend.app.core.config import settings


class StructuredFormatter(logging.Formatter):
    """Clean structured log formatter with standardized layout."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        level = record.levelname.ljust(8)
        name = record.name
        message = record.getMessage()

        base = f"[{timestamp}] [{level}] [{name}] {message}"
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
