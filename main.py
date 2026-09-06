"""
Proxmox MCP Server — Repeatable, priv-aware tools for Proxmox clusters.
Self-contained, deployable as LXC or Docker.
Focus: status, reports, queries, routine maintenance (Ceph, cluster, network, tasks).
Finite/one-off work stays on SSH path.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from logging_config import configure_logging, get_logger, request_id_middleware
from models import ActionResponse
from routers import admin, capabilities, ceph, cluster, logs, lxc, report
from routers.logs import setup_self_logging
from security import add_rate_limiting, get_api_key

load_dotenv()
configure_logging()
setup_self_logging()
logger = get_logger()


app = FastAPI(
    title="Proxmox MCP Server",
    version="0.5.0",
    description="Priv-aware, repeatable tools: cluster status, Ceph, LXC/VM management, health snapshots.",
)

# CORS (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID + structured logging
app.add_middleware(request_id_middleware())

# Rate limiting + optional API key
app = add_rate_limiting(app)

# Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Include routers
app.include_router(capabilities.router)
app.include_router(lxc.router)
app.include_router(cluster.router)
app.include_router(ceph.router)
app.include_router(logs.router)
app.include_router(admin.router)
app.include_router(report.router)

# Optional API key protection on all routes (if MCP_API_KEY is set)
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if os.getenv("MCP_API_KEY"):
        get_api_key(request.headers.get("X-API-Key"))
    return await call_next(request)


# Better error handling for PVE responses
@app.exception_handler(HTTPException)
async def pve_error_handler(request: Request, exc: HTTPException):
    if exc.status_code == 403:
        return {"success": False, "error": "Permission denied (check token ACLs)", "detail": exc.detail}
    if exc.status_code >= 500:
        return {"success": False, "error": "Proxmox API error", "detail": exc.detail}
    return {"success": False, "error": str(exc.detail)}


# Legacy /health
@app.get("/health", response_model=ActionResponse)
def health():
    return ActionResponse(success=True, data={
        "status": "ok",
        "version": "0.5.0",
        "pve_host": os.getenv("PVE_HOST", "https://pve-01:8006")
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
