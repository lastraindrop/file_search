#!/usr/bin/env python3
"""FileCortex Web Application."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hmac
import ipaddress
import os
import pathlib
import sysconfig
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from file_cortex_core import __version__, logger
from routers import common as route_common
from routers.http_routes import router as http_router
from routers.ws_routes import router as ws_router

API_TOKEN = os.getenv("FCTX_API_TOKEN", "")

_BASE_DIR = pathlib.Path(__file__).parent.resolve()


def _resource_dir(name: str) -> pathlib.Path:
    """Finds source-tree resources or resources installed with the wheel."""
    source_dir = _BASE_DIR / name
    if source_dir.is_dir():
        return source_dir
    return pathlib.Path(sysconfig.get_path("data")) / name


_STATIC_DIR = _resource_dir("static")
_TEMPLATES_DIR = _resource_dir("templates")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
ACTIVE_PROCESSES = route_common.ACTIVE_PROCESSES


def _parse_allowed_origins(raw_value: str | None) -> list[str]:
    """Parses allowed origins from environment configuration."""
    if not raw_value:
        return ["http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"]

    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return origins or ["http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"]


def _is_wildcard_origin(origins: list[str]) -> bool:
    """Checks if the origins list represents a wildcard (allow all)."""
    return "*" in origins


ALLOWED_ORIGINS = _parse_allowed_origins(os.getenv("FCTX_ALLOWED_ORIGINS"))


def _origin_allowed(origin: str) -> bool:
    """Checks an Origin header against the loopback/allowlist policy.

    Do NOT derive the expected origin from the client-controlled Host header
    (``request.base_url``): a forged Origin+Host pair would pass as
    "same-origin". A request is treated as same-origin only when the Origin
    host is one of the loopback hosts (the default deployment; any loopback
    port, matching the documented dev workflow) or matches an explicitly
    configured origin.
    """
    if _is_wildcard_origin(ALLOWED_ORIGINS):
        return True
    try:
        origin_host = (urlparse(origin).hostname or "").lower()
    except ValueError:
        return False
    return (
        origin_host in ("127.0.0.1", "localhost", "::1")
        or origin in ALLOWED_ORIGINS
    )


def _is_local_request(request: Request) -> bool:
    """Checks if the request originates from localhost.

    Used to decide whether to inject the API token into the index page.
    TestClient requests (no client info) are treated as local for CI.
    """
    client = request.client
    if not client:
        return True
    return client.host in ("127.0.0.1", "::1", "localhost", "testclient")


async def verify_api_token(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Verifies API token for protected endpoints."""
    if request.url.path.startswith("/api/"):
        # CORS preflights (OPTIONS) carry no auth headers; they must pass
        # through so the CORSMiddleware (registered inside this middleware)
        # can answer them for allowed origins.
        if request.method == "OPTIONS":
            return await call_next(request)
        origin = request.headers.get("origin")
        if origin and not _origin_allowed(origin):
            return JSONResponse(
                status_code=403,
                content={"status": "error", "detail": "Origin not allowed"},
            )
        if API_TOKEN:
            token = request.headers.get("X-API-Token", "")
            # Encode before comparing: compare_digest(str, str) raises
            # TypeError on non-ASCII header values (HTTP headers are
            # latin-1 decoded), which would surface as a 500.
            if not hmac.compare_digest(
                token.encode("utf-8"), API_TOKEN.encode("utf-8")
            ):
                return JSONResponse(
                    status_code=401,
                    content={"status": "error", "detail": "Invalid or missing API token"},
                )

    return await call_next(request)


async def apply_csp_header(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Adds Content-Security-Policy header to HTML responses."""
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return response
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'none'; "
        "form-action 'self'"
    )
    return response


def _shutdown_tracked_processes() -> None:
    """Terminates any tool subprocesses still tracked by ProcessManager.

    Runs on application shutdown so a server exit (or --reload restart)
    does not orphan detached child processes on the machine.
    """
    from file_cortex_core.process_utils import terminate_process

    for pid in route_common.process_manager.pids:
        proc = route_common.process_manager.get(pid)
        if proc is not None and proc.poll() is not None:
            route_common.process_manager.unregister(pid)
            continue
        logger.info(f"Shutting down tracked process on exit: PID {pid}")
        with contextlib.suppress(Exception):
            terminate_process(pid)
        route_common.process_manager.unregister(pid)


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application."""
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Application lifespan: cleans up tracked subprocesses on exit."""
        yield
        await asyncio.to_thread(_shutdown_tracked_processes)

    app = FastAPI(
        title=f"FileCortex v{__version__} API", lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        # NOTE: Browsers forbid credentials with wildcard origins;
        # credentials must be False when origins=["*"] per CORS spec.
        allow_credentials=not _is_wildcard_origin(ALLOWED_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(verify_api_token)
    app.middleware("http")(apply_csp_header)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.include_router(http_router)
    app.include_router(ws_router)
    return app


app = create_app()


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled server-side exceptions."""
    # B9: use logger.exception for consistent stack-trace capture per the
    # project's logging convention (was logger.error(..., exc_info=True)).
    logger.exception(f"Global Unhandled Exception: {exc}")

    detail = f"Internal Server Error: {str(exc)}"
    if os.getenv("FCTX_PROD") == "1":
        detail = "Internal Server Error. Please check server logs for details."

    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": detail},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serves the main index page.

    BUG-W1 fix: only inject the API token into the page when the request is
    local. Network clients must authenticate via X-API-Token header.
    """
    inject_token = API_TOKEN if _is_local_request(request) else ""
    return templates.TemplateResponse(
        request, "index.html", {"api_token": inject_token, "version": __version__}
    )


@app.get("/api/whoami")
async def whoami() -> dict[str, str]:
    """Returns server version (auth already enforced by middleware for /api/)."""
    return {"version": __version__, "status": "ok"}


def main() -> None:
    """Entry point for the web server."""
    parser = argparse.ArgumentParser(description="FileCortex Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    try:
        is_loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        is_loopback = args.host == "localhost"
    if not is_loopback and not API_TOKEN:
        parser.error("FCTX_API_TOKEN is required when binding outside localhost")

    uvicorn.run(
        "web_app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
