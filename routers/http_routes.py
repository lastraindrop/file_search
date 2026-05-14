"""HTTP route aggregator for the FileCortex web application.

Individual route modules are organized by domain:
- ``project_routes`` — workspace/project CRUD, favorites, settings
- ``fs_routes`` — file system operations
- ``action_routes`` — staging, tools, context generation, global settings
"""

from __future__ import annotations

from fastapi import APIRouter

from routers.action_routes import action_router
from routers.fs_routes import fs_router
from routers.project_routes import project_router

router = APIRouter()

# Merge all sub-routers into the main router.
# Each sub-router defines its own path prefixes, so we include them
# by specifying no prefix and all tags for discoverability.
router.include_router(project_router, tags=["Project"])
router.include_router(fs_router, tags=["File System"])
router.include_router(action_router, tags=["Actions"])

# Re-export for backward compatibility
__all__ = ["router"]
