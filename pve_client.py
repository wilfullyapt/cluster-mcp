"""Shared PVE API client (session + helpers).

All routers/services should import get_pve_host / get_pve_timeout from here
(or config) so PVE_HOST never drifts across modules.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from config import DEFAULT_PVE_HOST, get_pve_host, get_pve_timeout

load_dotenv()

# Module-level aliases kept for back-compat imports; always re-read env via helpers.
PVE_HOST = os.getenv("PVE_HOST", DEFAULT_PVE_HOST)
PVE_TOKEN_ID = os.getenv("PVE_TOKEN_ID")
PVE_TOKEN_SECRET = os.getenv("PVE_TOKEN_SECRET")
VERIFY_SSL = os.getenv("VERIFY_SSL", "false").lower() == "true"


def token_configured() -> bool:
    tid = os.getenv("PVE_TOKEN_ID") or PVE_TOKEN_ID
    secret = os.getenv("PVE_TOKEN_SECRET") or PVE_TOKEN_SECRET
    return bool(tid and secret)


def get_session() -> requests.Session:
    """Return a requests session authenticated for Proxmox."""
    sess = requests.Session()
    tid = os.getenv("PVE_TOKEN_ID") or PVE_TOKEN_ID
    secret = os.getenv("PVE_TOKEN_SECRET") or PVE_TOKEN_SECRET
    if tid and secret:
        sess.headers.update({"Authorization": f"PVEAPIToken={tid}={secret}"})

    verify = os.getenv("VERIFY_SSL", "false").lower() == "true"
    if not verify:
        sess.verify = False
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    return sess


def pve_get(path: str, *, timeout: float | None = None) -> tuple[Any | None, str | None]:
    """Safe PVE GET. path is under /api2/json (with or without prefix).

    Returns (data, error_string). Never raises — callers soft-fail.
    """
    api_path = path if path.startswith("/api2/json") else f"/api2/json{path if path.startswith('/') else '/' + path}"
    url = f"{get_pve_host()}{api_path}"
    t = get_pve_timeout() if timeout is None else timeout
    try:
        sess = get_session()
        r = sess.get(url, timeout=t)
        r.raise_for_status()
        payload = r.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload.get("data"), None
        return payload, None
    except Exception as exc:  # noqa: BLE001 — probe boundary
        return None, f"{type(exc).__name__}: {exc}"


def classify_pve_error(err: str | None) -> str:
    """Map exception text to a coarse plane status for /capabilities honesty."""
    if not err:
        return "ok"
    low = err.lower()
    if not token_configured():
        return "token_missing"
    if any(x in low for x in ("name or service not known", "nodename nor servname", "failed to resolve", "getaddrinfo", "name resolution")):
        return "pve_unreachable"
    if any(
        x in low
        for x in (
            "connection refused",
            "connect timeout",
            "timed out",
            "timeout",
            "network is unreachable",
            "no route to host",
        )
    ):
        return "pve_unreachable"
    if any(x in low for x in ("401", "403", "unauthorized", "permission", "authentication", "invalid pve ticket")):
        return "token_broken"
    if "ssl" in low or "certificate" in low:
        return "pve_unreachable"
    return "pve_error"
