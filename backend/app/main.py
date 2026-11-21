"""ReproLab AI API entry point."""

import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .db import init_db
from .routers import datasets, experiments, papers, protocols, workflows

API_VERSION = "0.5.0"
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


class HealthResponse(BaseModel):
    """Public service health payload."""

    status: Literal["ok"]
    service: str
    version: str
    timestamp: datetime


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepare SQLite storage on startup."""
    init_db()
    yield


app = FastAPI(
    title="ReproLab AI API",
    summary="研途复现官后端服务",
    version=API_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

demo_mode = os.getenv("REPROLAB_DEMO_MODE", "")
demo_access_code = os.getenv("REPROLAB_DEMO_ACCESS_CODE", "")
if demo_mode == "protected":
    if credentials_dir := os.getenv("CREDENTIALS_DIRECTORY"):
        demo_access_code = (Path(credentials_dir) / "demo_access_code").read_text().strip()
    if not demo_access_code:
        raise RuntimeError("Protected ReproLab needs a demo access code")


@app.middleware("http")
async def control_demo_access(request: Request, call_next):
    if demo_mode == "readonly" and request.method not in {"GET", "HEAD", "OPTIONS"}:
        return JSONResponse({"detail": "公开演示支持浏览。实时运行需要演示访问码。"}, 403)
    if demo_mode == "protected" and request.method != "OPTIONS":
        expected = f"Bearer {demo_access_code}".encode()
        provided = request.headers.get("Authorization", "").encode()
        if not secrets.compare_digest(provided, expected):
            return JSONResponse({"detail": "演示访问码无效。"}, 401)
    return await call_next(request)


origins = os.getenv("FRONTEND_ORIGINS", DEFAULT_ORIGINS).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(papers.router)
app.include_router(protocols.router)
app.include_router(datasets.router)
app.include_router(experiments.router)
app.include_router(workflows.router)


@app.get("/api/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    """Return current service status and API version."""
    return HealthResponse(
        status="ok",
        service="ReproLab AI API",
        version=API_VERSION,
        timestamp=datetime.now(timezone.utc),
    )


if demo_mode == "protected":
    @app.get("/api/demo/access", include_in_schema=False)
    def demo_access():
        return {"authenticated": True}
