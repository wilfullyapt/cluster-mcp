"""MCP-side interval collector for enrolled Wardens."""

from __future__ import annotations

import os
import threading
from typing import Any

from logging_config import get_logger

logger = get_logger()
_stop = threading.Event()
_thread: threading.Thread | None = None


def _interval_sec() -> int:
    raw = os.getenv("WARDENS_COLLECT_INTERVAL_SEC", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _loop() -> None:
    from services.warden_fleet import FleetSyncError, fleet_sync

    interval = _interval_sec()
    logger.info("Wardens collect scheduler started", interval_sec=interval)
    # initial delay so startup is not blocked
    if _stop.wait(min(15, interval)):
        return
    while not _stop.is_set():
        try:
            result = fleet_sync(do_build=False, do_update=False, do_collect=True)
            logger.info(
                "Scheduled collect-all finished",
                success=result.success,
                message=result.message,
            )
        except FleetSyncError as exc:
            logger.warning("Scheduled collect-all skipped", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scheduled collect-all error", error=str(exc))
        # re-read interval each cycle
        interval = _interval_sec()
        if interval <= 0:
            break
        if _stop.wait(interval):
            break
    logger.info("Wardens collect scheduler stopped")


def start_wardens_collect_scheduler() -> dict[str, Any]:
    """Start background collect-all if WARDENS_COLLECT_INTERVAL_SEC > 0."""
    global _thread
    interval = _interval_sec()
    if interval <= 0:
        return {"started": False, "reason": "WARDENS_COLLECT_INTERVAL_SEC unset or 0"}
    if _thread and _thread.is_alive():
        return {"started": False, "reason": "already running", "interval_sec": interval}
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="wardens-collect", daemon=True)
    _thread.start()
    return {"started": True, "interval_sec": interval}


def stop_wardens_collect_scheduler() -> None:
    _stop.set()
