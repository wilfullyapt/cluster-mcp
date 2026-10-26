"""Self-logging / observability router for the MCP itself."""

import logging
import subprocess
from collections import deque

from fastapi import APIRouter, Query

from models import ActionResponse

router = APIRouter(prefix="/logs", tags=["Logs / Self-Monitoring"])

LOG_BUFFER = deque(maxlen=500)


class LogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            LOG_BUFFER.append(msg)
        except Exception:
            pass


def setup_self_logging():
    handler = LogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


@router.get("/recent", response_model=ActionResponse)
def get_recent_logs(lines: int = Query(50, ge=1, le=500), level: str = Query(None)):
    recent = list(LOG_BUFFER)[-lines:]
    if level:
        level = level.upper()
        recent = [line for line in recent if level in line.upper()]
    return ActionResponse(success=True, data={"count": len(recent), "logs": recent})


@router.get("/health-with-logs", response_model=ActionResponse)
def health_with_logs():
    recent = list(LOG_BUFFER)[-20:]
    return ActionResponse(success=True, data={
        "status": "ok",
        "version": "0.3.0",
        "recent_logs": recent
    })


@router.get("/journal", response_model=ActionResponse)
def journal_logs(lines: int = Query(50, ge=1, le=200)):
    try:
        result = subprocess.run(
            ["journalctl", "-u", "clustermcp", "-n", str(lines), "--no-pager"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return ActionResponse(success=False, data={"error": result.stderr.strip()})
        logs = result.stdout.strip().splitlines()[-lines:]
        return ActionResponse(success=True, data={"count": len(logs), "logs": logs})
    except Exception as e:
        return ActionResponse(success=False, data={"error": str(e)})


@router.get("/watchdog", response_model=ActionResponse)
def watchdog_check():
    errors = [l for l in LOG_BUFFER if "ERROR" in l.upper() or "CRITICAL" in l.upper()]
    warnings = [l for l in LOG_BUFFER if "WARNING" in l.upper()]
    return ActionResponse(success=True, data={
        "recent_errors": len(errors),
        "recent_warnings": len(warnings),
        "status": "healthy" if len(errors) == 0 else "degraded"
    })
