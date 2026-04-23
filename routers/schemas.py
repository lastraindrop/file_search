"""Shared Pydantic request models for FileCortex routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProjectOpenRequest(BaseModel):
    """Request model for opening a project."""

    path: str


class StageAllRequest(BaseModel):
    """Request model for staging all files in a project."""

    project_path: str
    mode: str = "files"
    apply_excludes: bool = True


class GenerateRequest(BaseModel):
    """Request model for generating file context."""

    files: list[str]
    project_path: str | None = None
    template_name: str | None = None
    export_format: str = "markdown"
    include_blueprint: bool = True


class FileRenameRequest(BaseModel):
    """Request model for renaming a file."""

    project_path: str
    path: str
    new_name: str


class FileDeleteRequest(BaseModel):
    """Request model for deleting files."""

    project_path: str
    paths: list[str]


class FileMoveRequest(BaseModel):
    """Request model for moving files."""

    src_paths: list[str]
    dst_dir: str


class FileSaveRequest(BaseModel):
    """Request model for saving file content."""

    path: str
    content: str = Field(..., max_length=10_000_000)


class FileCreateRequest(BaseModel):
    """Request model for creating a new file or directory."""

    parent_path: str
    name: str
    is_dir: bool = False


class FileArchiveRequest(BaseModel):
    """Request model for archiving files."""

    paths: list[str]
    output_name: str
    project_root: str


class OpenPathRequest(BaseModel):
    """Request model for opening a file or directory in the OS shell."""

    project_path: str
    path: str


class ChildrenRequest(BaseModel):
    """Request model for getting directory children."""

    path: str


class NoteRequest(BaseModel):
    """Request model for adding notes to files."""

    project_path: str
    file_path: str
    note: str


class TagRequest(BaseModel):
    """Request model for managing file tags."""

    project_path: str
    file_path: str
    tag: str
    action: Literal["add", "remove"]


class GlobalSettingsRequest(BaseModel):
    """Request model for updating global settings."""

    preview_limit_mb: float | None = None
    allowed_extensions: str | None = None
    token_threshold: int | None = None
    enable_noise_reducer: bool | None = None
    theme: str | None = None
    token_ratio: float | None = None
    settings: dict | None = None


class FavoriteRequest(BaseModel):
    """Request model for managing favorites."""

    project_path: str
    group_name: str
    file_paths: list[str]
    action: Literal["add", "remove"]


class SessionRequest(BaseModel):
    """Request model for saving sessions."""

    project_path: str
    data: dict


class ProjectSettingsRequest(BaseModel):
    """Request model for updating project settings."""

    project_path: str
    settings: dict


class ToolsUpdateRequest(BaseModel):
    """Request model for updating custom tools."""

    project_path: str
    tools: dict


class CategoriesUpdateRequest(BaseModel):
    """Request model for updating categories."""

    project_path: str
    categories: dict


class PathCollectionRequest(BaseModel):
    """Request model for collecting and formatting paths."""

    paths: list[str]
    project_root: str | None = None
    mode: str = "relative"
    separator: str = "\n"
    file_prefix: str = ""
    dir_suffix: str = ""


class WorkspacePinRequest(BaseModel):
    """Request model for pinning workspaces."""

    path: str


class CategorizeRequest(BaseModel):
    """Request model for categorizing files."""

    project_path: str
    paths: list[str]
    category_name: str


class StatsRequest(BaseModel):
    """Request model for getting file statistics."""

    paths: list[str]
    project_path: str | None = None


class ToolExecuteRequest(BaseModel):
    """Request model for executing tools."""

    project_path: str
    paths: list[str]
    tool_name: str


class BatchRenameRequest(BaseModel):
    """Request model for batch renaming files."""

    project_path: str
    paths: list[str]
    pattern: str
    replacement: str
    dry_run: bool = True


class ProcessTerminateRequest(BaseModel):
    """Request model for terminating processes."""

    pid: int
