"""Structured logging for ClusterMCP (production ready)."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from uuid import uuid4

import structlog

LOG_DIR = os.getenv("MCP_LOG_DIR", "./logs")
LOG_FILE = os.path.join(LOG_DIR, "mcp.log")
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5


def configure_logging():
    # Ensure log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler],
        format="%(message)s"
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.JSONRenderer() if not sys.stderr.isatty() else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "clustermcp"):
    return structlog.get_logger(name)


def request_id_middleware():
    """FastAPI middleware factory for correlation IDs."""
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware

    class RequestIDMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            request_id = request.headers.get("X-Request-ID", str(uuid4()))
            structlog.contextvars.bind_contextvars(request_id=request_id)
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

    return RequestIDMiddleware
