"""FastAPI application entry point.

    uvicorn app.main:app --reload --port 8000     (from story-pipeline/backend)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.api import jobs, projects, stories, system
from app.config import ROOT_DIR, get_settings
from app.persistence.db import init_engine
from app.services.rights.service import RightsError
from app.workflow.context import StageFailed
from app.workflow.runner import JobRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_engine(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    runner = JobRunner(settings)
    app.state.runner = runner
    runner.start()
    yield
    runner.stop()


app = FastAPI(title="Story-to-YouTube Pipeline", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4200"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(StageFailed)
@app.exception_handler(RightsError)
async def _domain_error(_: Request, exc: Exception):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


for r in (stories.router, projects.router, jobs.router, system.router):
    app.include_router(r)

# Serve the built Angular app (npm run build) from the same process, if present.
_dist = ROOT_DIR / "frontend" / "dist" / "story-studio" / "browser"
if _dist.exists():
    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        f = _dist / path
        if path and f.is_file() and _dist in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
