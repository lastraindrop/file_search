#!/usr/bin/env python3
"""FileCortex Web Application."""

from __future__ import annotations

import argparse
import os
import pathlib

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from file_cortex_core import logger
from routers import common as route_common
from routers.http_routes import router as http_router
from routers.ws_routes import router as ws_router

API_TOKEN = os.getenv("FCTX_API_TOKEN", "")

_BASE_DIR = pathlib.Path(__file__).parent.resolve()
_STATIC_DIR = _BASE_DIR / "static"
_TEMPLATES_DIR = _BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
ACTIVE_PROCESSES = route_common.ACTIVE_PROCESSES


def _parse_allowed_origins(raw_value: str | None) -> list[str]:
    """Parses allowed origins from environment configuration."""
    if not raw_value:
        return ["*"]

    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return origins or ["*"]


ALLOWED_ORIGINS = _parse_allowed_origins(os.getenv("FCTX_ALLOWED_ORIGINS", "*"))


async def verify_api_token(request: Request, call_next):
    """Verifies API token for protected endpoints."""
    if not API_TOKEN:
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        token = request.headers.get("X-API-Token", "")
        if token != API_TOKEN:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "detail": "Invalid or missing API token"},
            )

        origin = request.headers.get("origin", "*")
        if ALLOWED_ORIGINS != ["*"] and origin not in ALLOWED_ORIGINS:
            return JSONResponse(
                status_code=403,
                content={"status": "error", "detail": "Origin not allowed"},
            )

    return await call_next(request)


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application."""
    app = FastAPI(title="FileCortex v6.2.0 API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=ALLOWED_ORIGINS != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(verify_api_token)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.include_router(http_router)
    app.include_router(ws_router)
    return app


app = create_app()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled server-side exceptions."""
    logger.error(f"Global Unhandled Exception: {exc}", exc_info=True)

    detail = f"Internal Server Error: {str(exc)}"
    if os.getenv("FCTX_PROD") == "1":
        detail = "Internal Server Error. Please check server logs for details."

    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": detail},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serves the main index page."""
    return templates.TemplateResponse(request, "index.html", {})


def main() -> None:
    """Entry point for the web server."""
    parser = argparse.ArgumentParser(description="FileCortex Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "web_app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
