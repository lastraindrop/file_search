#!/usr/bin/env python3
"""File operations and action bridge for FileCortex.

Provides file manipulation utilities and external tool execution.
"""

import os
import pathlib
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import threading
import uuid
import zipfile
from collections.abc import Generator
from typing import Any

from .config import DataManager, logger
from .file_io import FileUtils
from .security import PathValidator


class ProgressTracker:
    """Thread-safe in-memory progress tracker for long-running tasks.

    Maintains a module-level registry mapping ``task_id`` to a progress dict
    with the keys ``task_id``, ``status`` (``"pending"`` / ``"running"`` /
    ``"done"`` / ``"failed"``), ``message``, ``done`` and ``total``. All access
    is serialized through a class-level :class:`threading.Lock`.

    Typical usage::

        task_id = ProgressTracker.new_task(total=len(items))
        for i, item in enumerate(items):
            ...
            ProgressTracker.update(task_id, done=i + 1, status="running")
        ProgressTracker.update(task_id, status="done")
        state = ProgressTracker.get(task_id)
    """

    _tasks: dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def new_task(cls, total: int) -> str:
        """Creates a new tracked task with a generated UUID id.

        Args:
            total: Total number of units in the task.

        Returns:
            The newly generated ``task_id``.
        """
        task_id = uuid.uuid4().hex
        cls.start_task(task_id, total)
        return task_id

    @classmethod
    def start_task(cls, task_id: str, total: int) -> None:
        """Creates a new progress entry for ``task_id``.

        Overwrites any pre-existing entry for the same id.

        Args:
            task_id: Unique identifier supplied by the caller.
            total: Total number of units in the task.
        """
        with cls._lock:
            cls._tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "message": None,
                "done": 0,
                "total": total,
            }

    @classmethod
    def update(
        cls,
        task_id: str,
        done: int | None = None,
        status: str | None = None,
        message: str | None = None,
    ) -> None:
        """Updates an existing progress entry.

        Silently no-ops if ``task_id`` was never started. Each of
        ``done`` / ``status`` / ``message`` is applied only when provided.

        Args:
            task_id: Unique identifier supplied to :meth:`start_task`.
            done: New completed-units count, or ``None`` to leave unchanged.
            status: New status string, or ``None`` to leave unchanged.
            message: New human-readable message, or ``None`` to leave unchanged.
        """
        with cls._lock:
            entry = cls._tasks.get(task_id)
            if entry is None:
                return
            if done is not None:
                entry["done"] = done
            if status is not None:
                entry["status"] = status
            if message is not None:
                entry["message"] = message

    @classmethod
    def get(cls, task_id: str) -> dict | None:
        """Returns a shallow copy of the progress entry, or ``None`` if unknown.

        Args:
            task_id: Unique identifier supplied to :meth:`start_task`.

        Returns:
            A copy of the progress dict, or ``None``.
        """
        with cls._lock:
            entry = cls._tasks.get(task_id)
            return dict(entry) if entry is not None else None


class FileOps:
    """File operation utilities."""

    @staticmethod
    def _validate_item_name(name: str) -> None:
        """Validates a single path segment used for create/rename operations."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Name must be a non-empty string.")
        if name in {".", ".."}:
            raise ValueError("Reserved relative names are not allowed.")
        if any(sep in name for sep in ("/", "\\")):
            raise ValueError("Path separators are not allowed in item names.")

    @staticmethod
    def batch_rename(
        project_path: str,
        paths: list[str],
        pattern: str,
        replacement: str,
        dry_run: bool = True,
        count: int = 1,
    ) -> list[dict[str, str]]:
        """Renames multiple files using regex.

        Args:
            project_path: Project root path.
            paths: List of file paths to rename.
            pattern: Regex pattern.
            replacement: Replacement string.
            dry_run: If True, only simulate changes.
            count: Maximum number of replacements per filename (0 = all).
                Defaults to 1 for backward compatibility.

        Returns:
            List of result dictionaries.
        """
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex: {e}") from e

        results = []
        new_names = {}
        for p_str in paths:
            p = pathlib.Path(p_str)
            new_name = regex.sub(replacement, p.name, count=count if count > 0 else 0)
            if new_name == p.name:
                continue

            new_path = p.parent / new_name
            new_names[p_str] = new_path

        final_targets: dict[str, tuple[pathlib.Path, str]] = {}
        target_norm_set = set()

        def norm_path_str(p: pathlib.Path) -> str:
            abs_p = str(p.absolute())
            return abs_p.lower() if os.name == "nt" else abs_p

        for old_p, new_p in new_names.items():
            status = "ok"
            norm_new = norm_path_str(new_p)

            if new_p.exists() or norm_new in target_norm_set:
                status = "conflict"

            if status == "conflict":
                base = new_p.stem
                ext = new_p.suffix
                counter = 1
                max_attempts = 1000
                while counter <= max_attempts:
                    candidate = new_p.parent / f"{base}_{counter}{ext}"
                    norm_candidate = norm_path_str(candidate)
                    if not candidate.exists() and norm_candidate not in target_norm_set:
                        new_p = candidate
                        status = "renamed_with_suffix"
                        break
                    counter += 1
                if counter > max_attempts:
                    status = "failed"

            final_targets[old_p] = (new_p, status)
            target_norm_set.add(norm_path_str(new_p))
            results.append({"old": old_p, "new": str(new_p), "status": status})

        if not dry_run:
            renamed_stack = []
            try:
                for old_p, (new_p, _) in final_targets.items():
                    p_old = pathlib.Path(old_p)
                    p_old.rename(new_p)
                    renamed_stack.append((old_p, new_p))
            except Exception as e:
                logger.error(
                    f"Batch rename failed: {e}. "
                    f"Attempting rollback of {len(renamed_stack)} items."
                )
                rollback_errors = []
                for old_p_str, new_p_obj in reversed(renamed_stack):
                    try:
                        new_p_obj.rename(old_p_str)
                    except Exception as rollback_e:
                        rollback_errors.append(
                            f"{new_p_obj} -> {old_p_str}: {rollback_e}"
                        )
                        logger.critical(
                            f"FATAL: Rollback failed for {new_p_obj}: {rollback_e}"
                        )

                if rollback_errors:
                    msg = (
                        f"Batch rename failed and rollback was incomplete: {e}. "
                        f"Manual fix required for: {', '.join(rollback_errors)}"
                    )
                    raise RuntimeError(msg) from e
                raise

        return results

    @staticmethod
    def rename_file(old_path_str: str, new_name: str) -> str:
        """Renames a single file.

        Args:
            old_path_str: Original file path.
            new_name: New file name.

        Returns:
            New file path.
        """
        FileOps._validate_item_name(new_name)
        old_path = pathlib.Path(old_path_str)
        if not old_path.exists():
            raise FileNotFoundError("Target path does not exist.")
        new_path = old_path.parent / new_name
        if new_path.exists():
            raise FileExistsError("A file with new name already exists.")
        old_path.rename(new_path)
        return str(new_path)

    @staticmethod
    def delete_file(path_str: str) -> bool:
        """Deletes a file or directory.

        Args:
            path_str: Path to delete.

        Returns:
            True on success.
        """
        path = pathlib.Path(path_str)
        if not path.exists():
            raise FileNotFoundError("Target path does not exist.")

        def _handle_readonly(
            func: Any,
            path: str,
            exc_info: tuple[type[BaseException], BaseException, ...],
        ) -> None:
            os.chmod(path, stat.S_IWRITE)
            func(path)

        if path.is_file():
            try:
                path.unlink()
            except PermissionError:
                os.chmod(path, stat.S_IWRITE)
                path.unlink()
        elif path.is_dir():
            shutil.rmtree(path, onerror=_handle_readonly)
        return True

    @staticmethod
    def move_file(src_path_str: str, dst_dir_str: str) -> str:
        """Moves a file to a destination directory.

        Args:
            src_path_str: Source file path.
            dst_dir_str: Destination directory path.

        Returns:
            New file path.
        """
        src_path = pathlib.Path(src_path_str)
        dst_dir = pathlib.Path(dst_dir_str)
        if not src_path.exists():
            raise FileNotFoundError("Source path does not exist.")
        if not dst_dir.exists() or not dst_dir.is_dir():
            raise FileNotFoundError("Destination directory does not exist.")

        dst_path = dst_dir / src_path.name
        if dst_path.exists():
            raise FileExistsError("A file with same name exists in destination.")

        shutil.move(str(src_path), str(dst_path))
        return str(dst_path)

    @staticmethod
    def save_content(path_str: str, content: str) -> bool:
        """Saves content to a file atomically.

        Args:
            path_str: File path.
            content: Content to write.

        Returns:
            True on success.
        """
        path = pathlib.Path(path_str)
        if not path.exists():
            raise FileNotFoundError("Target file does not exist.")
        if not path.is_file():
            raise IsADirectoryError("Target is a directory.")
        if FileUtils.is_binary(path):
            raise ValueError("Cannot save binary file as text.")

        temp_fd, temp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(temp_path, path)
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception:
                pass
            raise
        return True

    @staticmethod
    def create_item(parent_path_str: str, name: str, is_dir: bool = False) -> str:
        """Creates a new file or directory.

        Args:
            parent_path_str: Parent directory path.
            name: New item name.
            is_dir: Whether to create a directory.

        Returns:
            Created item path.
        """
        FileOps._validate_item_name(name)
        parent_path = pathlib.Path(parent_path_str)
        if not parent_path.exists() or not parent_path.is_dir():
            raise FileNotFoundError("Parent directory does not exist.")

        new_path = parent_path / name
        if new_path.exists():
            raise FileExistsError(
                f"{'Directory' if is_dir else 'File'} already exists."
            )

        if is_dir:
            new_path.mkdir()
        else:
            new_path.touch()
        return str(new_path)

    @staticmethod
    def archive_selection(
        paths: list[str],
        output_path_str: str,
        root_dir: str | None = None,
    ) -> str:
        """Creates a ZIP archive of selected files.

        Args:
            paths: Files to archive.
            output_path_str: Output archive path.
            root_dir: Root directory for relative paths.

        Returns:
            Output archive path.
        """
        output_path = pathlib.Path(output_path_str)
        root_dir_p = pathlib.Path(root_dir).resolve() if root_dir else None
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for p_str in paths:
                p = pathlib.Path(p_str).resolve()
                if not p.exists():
                    continue
                arcname = (
                    p.relative_to(root_dir_p)
                    if root_dir_p and (root_dir_p == p or root_dir_p in p.parents)
                    else p.name
                )
                if p.is_file():
                    zipf.write(p, arcname)
                elif p.is_dir():
                    for root, _, files in os.walk(p):
                        for file in files:
                            full_f = pathlib.Path(root) / file
                            # BUG-C2 fix: per-file arcname decision, same logic as file branch.
                            if root_dir_p and (
                                root_dir_p == full_f or root_dir_p in full_f.parents
                            ):
                                arc = full_f.relative_to(root_dir_p)
                            else:
                                arc = full_f.relative_to(p.parent)
                            zipf.write(full_f, arc)
        return str(output_path)

    @staticmethod
    def batch_categorize(
        project_path: str,
        paths: list[str],
        category_name: str,
        data_mgr: DataManager | None = None,
    ) -> list[str]:
        """Categorizes files into a project category directory.

        Args:
            project_path: Project root path.
            paths: Files to categorize.
            category_name: Category name.
            data_mgr: Optional DataManager instance for DI.

        Returns:
            List of new file paths.
        """
        dm = data_mgr or DataManager()
        proj = dm.get_project_data(project_path)
        cat_dir_rel = proj["quick_categories"].get(category_name)
        if not cat_dir_rel:
            raise ValueError(f"Category '{category_name}' not defined.")

        root = pathlib.Path(project_path)
        target_dir = (root / cat_dir_rel).resolve()

        if not PathValidator.is_safe(target_dir, root):
            raise PermissionError("Category target directory is outside the workspace.")

        if not target_dir.exists():
            target_dir.mkdir(parents=True)

        moved = []
        for p_str in paths:
            try:
                new_p = FileOps.move_file(p_str, str(target_dir))
                moved.append(new_p)
            except Exception:
                logger.exception(f"Failed to categorize {p_str}")
        return moved

    @staticmethod
    def copy_item(
        srcs: list[str],
        dst_dir_str: str,
        project_root: str,
        task_id: str | None = None,
    ) -> list[str]:
        """Copies a batch of files and/or directories into a destination directory.

        Iterates over ``srcs`` and applies the existing per-item copy logic:
        files are copied with :func:`shutil.copy2` and directories are copied
        recursively with :func:`shutil.copytree`. Each item still enforces
        no-overwrite: if ``dst_dir / src.name`` already exists a
        :class:`FileExistsError` is raised and the whole batch aborts.

        Both the destination directory and every source must reside within
        ``project_root`` (the security boundary). The destination directory
        must already exist.

        When ``task_id`` is provided the operation is tracked through
        :class:`ProgressTracker`: the task is started with
        ``total = len(srcs)``, updated to ``"running"`` after each successful
        item, set to ``"failed"`` on exception (re-raised), and set to
        ``"done"`` on full success. ``task_id=None`` (default) disables
        tracking entirely, preserving backward-compatible behaviour.

        Args:
            srcs: List of source file or directory paths to copy.
            dst_dir_str: Destination directory path.
            project_root: Project root acting as the security boundary.
            task_id: Optional progress-tracker task id.

        Returns:
            List of the newly created copy paths, one per input source.

        Raises:
            FileNotFoundError: If a source does not exist or the destination
                directory does not exist.
            FileExistsError: If a target name already exists in the destination.
            PermissionError: If a source or the destination escapes the project
                root.
            ValueError: If a source is neither a file nor a directory, or if a
                directory would be copied into itself or one of its descendants.
        """
        dst_dir = pathlib.Path(dst_dir_str).resolve()
        root = pathlib.Path(project_root).resolve()

        if not PathValidator.is_safe(dst_dir, root):
            raise PermissionError("Destination is outside the project workspace.")
        if not dst_dir.exists() or not dst_dir.is_dir():
            raise FileNotFoundError("Destination directory does not exist.")

        if task_id is not None:
            ProgressTracker.start_task(task_id, total=len(srcs))

        results: list[str] = []
        try:
            for idx, src_path_str in enumerate(srcs):
                src_path = pathlib.Path(src_path_str).resolve()

                if not src_path.exists():
                    raise FileNotFoundError("Source path does not exist.")
                if not PathValidator.is_safe(src_path, root):
                    raise PermissionError(
                        "Source is outside the project workspace."
                    )

                dst_path = dst_dir / src_path.name
                if dst_path.exists():
                    raise FileExistsError(
                        "A file with the same name exists in destination."
                    )

                if src_path.is_file():
                    shutil.copy2(src_path, dst_path)
                    logger.info(f"Copied file: {src_path} -> {dst_path}")
                elif src_path.is_dir():
                    # Guard against copying a directory into itself or a
                    # descendant, which would otherwise recurse infinitely.
                    if dst_dir == src_path or src_path in dst_dir.parents:
                        raise ValueError(
                            "Cannot copy a directory into itself or its "
                            "descendant."
                        )
                    shutil.copytree(src_path, dst_path)
                    logger.info(f"Copied directory: {src_path} -> {dst_path}")
                else:
                    raise ValueError("Source is neither a file nor a directory.")

                results.append(str(dst_path))

                if task_id is not None:
                    ProgressTracker.update(
                        task_id,
                        done=idx + 1,
                        status="running",
                        message=f"Copied {src_path.name}",
                    )
        except Exception:
            if task_id is not None:
                ProgressTracker.update(
                    task_id,
                    done=len(results),
                    status="failed",
                    message="Batch copy failed",
                )
            raise

        if task_id is not None:
            ProgressTracker.update(
                task_id,
                done=len(results),
                status="done",
                message=f"Copied {len(results)} item(s)",
            )
        return results

    @staticmethod
    def _validate_extract_member(
        member_name: str, dst_root: pathlib.Path
    ) -> pathlib.Path:
        """Validates a single ZIP member name and returns its safe target path.

        Rejects any member that could escape ``dst_root``: absolute paths,
        Windows drive letters, UNC paths, backslash traversal, ``..`` segments,
        and any resolved target that lands outside ``dst_root``.

        Args:
            member_name: Raw member filename from the archive.
            dst_root: Resolved destination root directory.

        Returns:
            The resolved, boundary-checked target path.

        Raises:
            ValueError: If the member name is unsafe or escapes the destination.
        """
        if not member_name:
            raise ValueError("Empty archive member name.")

        # Normalize backslashes to forward slashes so Windows-style traversal
        # (e.g. "..\\evil.txt") is treated uniformly. ZIP spec uses "/", but
        # hostile archives may use "\" to slip past naive checks.
        normalized = member_name.replace("\\", "/")

        if normalized.startswith("/"):
            raise ValueError(f"Absolute path in archive: {member_name!r}")
        if normalized.startswith("//"):
            raise ValueError(f"UNC-style path in archive: {member_name!r}")
        # Windows drive letter, e.g. "C:/evil" or "C:evil".
        if len(normalized) >= 2 and normalized[1] == ":":
            raise ValueError(f"Drive-letter path in archive: {member_name!r}")

        # Reject any ".." path segment regardless of separator.
        segments = normalized.split("/")
        if any(seg == ".." for seg in segments):
            raise ValueError(f"Path traversal in archive: {member_name!r}")

        target = (dst_root / normalized).resolve()
        try:
            target.relative_to(dst_root)
        except ValueError as e:
            raise ValueError(
                f"Archive member escapes destination: {member_name!r}"
            ) from e
        return target

    @staticmethod
    def extract_archive(
        zip_path_str: str,
        dst_dir_str: str,
        project_root: str,
        task_id: str | None = None,
    ) -> list[str]:
        """Extracts a ZIP archive into a destination directory transactionally.

        The archive and destination must both reside within ``project_root``
        (the security boundary). The destination directory is created if it
        does not exist (including parents).

        Every member is validated before any file is written: absolute paths,
        Windows drive letters, UNC paths, backslash traversal, ``..`` segments,
        and any resolved target outside the destination are rejected. If any
        member is unsafe the whole operation aborts without writing.

        Extraction is performed in three passes inside a temporary staging
        directory created with
        ``tempfile.mkdtemp(prefix=".fctx_extract_", dir=dst_dir.parent)``:

        * **Pass 1** validates every member, computes its final target path,
          re-applies the no-overwrite pre-check and the duplicate-target check.
        * **Pass 2** extracts files (and creates directory members) inside the
          staging directory.
        * **Pass 3** atomically renames/moves each staged file to its final
          destination via :func:`shutil.move`.

        The staging directory is always removed via
        ``shutil.rmtree(temp_dir, ignore_errors=True)`` in a ``finally`` block,
        whether the operation succeeds or fails.

        When ``task_id`` is provided the operation is tracked through
        :class:`ProgressTracker` (``total`` = number of archive members),
        updated to ``"running"`` as each member is committed in Pass 3, set to
        ``"failed"`` on exception (re-raised), and set to ``"done"`` on full
        success. ``task_id=None`` (default) disables tracking.

        Args:
            zip_path_str: Path to the ZIP archive.
            dst_dir_str: Destination directory path.
            project_root: Project root acting as the security boundary.
            task_id: Optional progress-tracker task id.

        Returns:
            List of extracted paths (directories and files).

        Raises:
            FileNotFoundError: If the archive does not exist.
            FileExistsError: If any extracted file would overwrite an existing
                path.
            ValueError: If the archive is not a ZIP file or a member is unsafe.
            PermissionError: If the destination escapes the project root.
        """
        # The archive may originate from anywhere (e.g. a freshly downloaded or
        # generated bundle). The security boundary for extraction is the
        # *destination*: only where members are written matters, enforced by
        # the per-member validation below plus the dst-within-root check.
        zip_path = pathlib.Path(zip_path_str).resolve()
        root = pathlib.Path(project_root).resolve()
        dst_dir = pathlib.Path(dst_dir_str).resolve()

        if not zip_path.exists():
            raise FileNotFoundError("Archive does not exist.")
        if not PathValidator.is_safe(dst_dir, root):
            raise PermissionError(
                "Destination is outside the project workspace."
            )
        if not zipfile.is_zipfile(zip_path):
            raise ValueError(f"Not a ZIP archive: {zip_path}")

        dst_dir.mkdir(parents=True, exist_ok=True)

        extracted: list[str] = []
        infolist: list[zipfile.ZipInfo] = []

        with zipfile.ZipFile(zip_path, "r") as zf:
            infolist = zf.infolist()

            if task_id is not None:
                ProgressTracker.start_task(task_id, total=len(infolist))

            # Staging directory lives next to the destination so the final
            # Pass 3 rename/move is on the same filesystem and therefore atomic.
            temp_dir = pathlib.Path(
                tempfile.mkdtemp(prefix=".fctx_extract_", dir=str(dst_dir.parent))
            )
            try:
                # Pass 1: validate every member and resolve final + staging
                # targets. Re-apply the no-overwrite + duplicate-target checks
                # against the final destination. A malicious or unsatisfiable
                # entry aborts before any bytes are written.
                plan: list[tuple[zipfile.ZipInfo, pathlib.Path, pathlib.Path]] = []
                planned_file_targets: set[str] = set()
                for member in infolist:
                    target = FileOps._validate_extract_member(
                        member.filename, dst_dir
                    )
                    rel = target.relative_to(dst_dir)
                    temp_target = temp_dir / rel
                    target_key = (
                        str(target).lower() if os.name == "nt" else str(target)
                    )
                    if member.is_dir():
                        if target.exists() and not target.is_dir():
                            raise FileExistsError(
                                "Archive directory conflicts with existing "
                                f"file: {target}"
                            )
                    else:
                        if target.exists():
                            raise FileExistsError(
                                f"Extract target already exists: {target}"
                            )
                        if target_key in planned_file_targets:
                            raise FileExistsError(
                                "Archive contains duplicate target: "
                                f"{member.filename}"
                            )
                        planned_file_targets.add(target_key)
                    plan.append((member, target, temp_target))

                # Pass 2: write every member into the staging directory only.
                for member, _target, temp_target in plan:
                    if member.is_dir():
                        temp_target.mkdir(parents=True, exist_ok=True)
                    else:
                        temp_target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(temp_target, "wb") as out:
                            shutil.copyfileobj(src, out)

                # Pass 3: atomically promote each staged member to its final
                # destination. Per-file atomicity comes from shutil.move using
                # os.rename on the same filesystem.
                for idx, (member, target, temp_target) in enumerate(plan):
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(temp_target), str(target))
                    extracted.append(str(target))

                    if task_id is not None:
                        ProgressTracker.update(
                            task_id,
                            done=idx + 1,
                            status="running",
                            message=f"Extracted {member.filename}",
                        )
            except Exception:
                if task_id is not None:
                    ProgressTracker.update(
                        task_id,
                        done=len(extracted),
                        status="failed",
                        message="Extraction failed",
                    )
                raise
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        logger.info(
            f"Extracted {len(infolist)} members from {zip_path} -> {dst_dir}"
        )

        if task_id is not None:
            ProgressTracker.update(
                task_id,
                done=len(extracted),
                status="done",
                message=f"Extracted {len(extracted)} member(s)",
            )
        return extracted


class ActionBridge:
    """Bridge for executing external tools and commands."""

    @staticmethod
    def _prepare_execution(
        template: str,
        path_str: str,
        project_root: str,
        force_shell: bool | None = None,
    ) -> tuple[str | list[str], bool, dict[str, str]]:
        """Prepares command execution arguments.

        Args:
            template: Command template string.
            path_str: File path.
            project_root: Project root path.
            force_shell: Force shell mode.

        Returns:
            Tuple of (command, is_shell, context).
        """
        p = pathlib.Path(path_str)
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {path_str}")

        context = {
            "path": str(p),
            "name": p.name,
            "ext": p.suffix,
            "root": str(project_root),
            "parent": str(p.parent),
            "parent_name": p.parent.name,
        }

        if os.name == "nt":
            shell_metas = set("&|<>^%")
            is_shell = any(c in template for c in shell_metas) or (force_shell is True)

            def win_quote(s: str) -> str:
                return f'"{s.replace(chr(34), chr(92) + chr(34)).replace("%", "%%")}"'

            if not is_shell and force_shell is not False:
                first_word = template.split(None, 1)[0].strip('"')
                if not shutil.which(first_word):
                    is_shell = True

            if is_shell:
                safe_context = {k: win_quote(v) for k, v in context.items()}
                return template.format(**safe_context), True, context
            cmd_str = template.format(**context)
            try:
                raw_args = shlex.split(cmd_str, posix=False)
                args = [t.strip('"') for t in raw_args]
                return args, False, context
            except Exception:
                safe_context = {k: win_quote(v) for k, v in context.items()}
                return template.format(**safe_context), True, context
        else:
            tokens = shlex.split(template, posix=True)
            final_cmd = [t.format(**context) for t in tokens]
            return final_cmd, False, context

    @staticmethod
    def execute_tool(template: str, path_str: str, project_root: str) -> dict[str, Any]:
        """Executes a tool on a file.

        Args:
            template: Command template.
            path_str: File path.
            project_root: Project root.

        Returns:
            Result dictionary with stdout, stderr, exit_code.
        """
        try:
            cmd, is_shell, _ = ActionBridge._prepare_execution(
                template, path_str, project_root
            )

            timeout = int(os.environ.get("FCTX_EXEC_TIMEOUT", "300"))

            logger.info(
                f"AUDIT - Executing external tool (Shell={is_shell}): "
                f"{cmd if isinstance(cmd, list) else cmd.split()[0] + '...'}"
            )

            with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=is_shell,
                cwd=(
                    project_root
                    if os.path.exists(project_root) and os.path.isdir(project_root)
                    else None
                ),
            ) as proc:
                try:
                    stdout, stderr = proc.communicate(timeout=timeout)
                    return {
                        "stdout": stdout,
                        "stderr": stderr,
                        "exit_code": proc.returncode,
                        "pid": proc.pid,
                        "status": "success",
                    }
                except subprocess.TimeoutExpired:
                    from .process_utils import terminate_process

                    terminate_process(proc.pid)
                    stdout, stderr = proc.communicate()
                    return {
                        "stdout": stdout,
                        "stderr": stderr,
                        "exit_code": -1,
                        "error": "command timed out",
                        "status": "timeout",
                    }
        except Exception as e:
            logger.exception("Tool execution failed")
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "error": str(e),
                "status": "error",
            }

    @staticmethod
    def create_process(
        template: str, path_str: str, project_root: str
    ) -> subprocess.Popen:
        """Creates a subprocess for streaming output.

        Args:
            template: Command template.
            path_str: File path.
            project_root: Project root.

        Returns:
            Popen process object.
        """
        cmd, is_shell, _ = ActionBridge._prepare_execution(
            template, path_str, project_root
        )

        logger.info(
            f"AUDIT - Creating process (Shell={is_shell}): "
            f"{cmd if isinstance(cmd, list) else cmd.split()[0] + '...'}"
        )

        popen_kwargs = {
            "shell": is_shell,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
            "encoding": "utf-8",
            "errors": "replace",
        }

        if os.name != "nt":
            popen_kwargs["start_new_session"] = True

        return subprocess.Popen(cmd, **popen_kwargs)

    @staticmethod
    def stream_tool(
        template: str, path_str: str, project_root: str
    ) -> Generator[dict[str, Any], None, None]:
        """Streams tool output line by line.

        Args:
            template: Command template.
            path_str: File path.
            project_root: Project root.

        Yields:
            Result dictionaries with output lines.
        """
        p = pathlib.Path(path_str)
        if not p.exists():
            yield {"error": "Path does not exist"}
            return

        process = None
        try:
            process = ActionBridge.create_process(template, path_str, project_root)
            if process.stdout:
                for line in process.stdout:
                    yield {"out": line}

            exit_code = process.wait()
            yield {"exit_code": exit_code}

        except Exception as e:
            logger.exception("Tool streaming failed")
            yield {"error": str(e)}
        finally:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except Exception:
                    pass
