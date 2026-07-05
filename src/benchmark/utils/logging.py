import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configures structured logging via structlog.

    Formats output logs as structured JSON to stdout for readability,
    tracing, and searchability under parallel workloads.

    Args:
        log_level: Case-insensitive logging level (DEBUG, INFO, WARNING, ERROR).
    """
    level_val = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level_val,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
