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
import zipfile
from collections.abc import Generator
from typing import Any

from .config import DataManager, logger
from .security import PathValidator
from .file_io import FileUtils


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
    ) -> list[dict[str, str]]:
        """Renames multiple files using regex.

        Args:
            project_path: Project root path.
            paths: List of file paths to rename.
            pattern: Regex pattern.
            replacement: Replacement string.
            dry_run: If True, only simulate changes.

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
            new_name = regex.sub(replacement, p.name, count=1)
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
                    raise RuntimeError(
                        f"Batch rename failed and rollback was incomplete: {e}. "
                        f"Manual fix required for: {', '.join(rollback_errors)}"
                    ) from e
                raise e

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

        def _handle_readonly(func: Any, path: str, exc_info: tuple) -> None:
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
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception:
                pass
            raise e
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
                            rel_base = root_dir_p if root_dir_p else p.parent
                            zipf.write(full_f, full_f.relative_to(rel_base))
        return str(output_path)

    @staticmethod
    def batch_categorize(
        project_path: str, paths: list[str], category_name: str
    ) -> list[str]:
        """Categorizes files into a project category directory.

        Args:
            project_path: Project root path.
            paths: Files to categorize.
            category_name: Category name.

        Returns:
            List of new file paths.
        """
        data_mgr = DataManager()
        proj = data_mgr.get_project_data(project_path)
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
            except Exception as e:
                logger.error(f"Failed to categorize {p_str}: {e}")
        return moved


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
            else:
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

            timeout = int(
                os.environ.get(
                    "FCTX_EXEC_TIMEOUT",
                    DataManager().data.get("execution_timeout", 300),
                )
            )

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
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True,
                        )
                    else:
                        import signal

                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        except Exception:
                            proc.kill()
                    stdout, stderr = proc.communicate()
                    return {
                        "stdout": stdout,
                        "stderr": stderr,
                        "exit_code": -1,
                        "error": "command timed out",
                        "status": "timeout",
                    }
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
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
            logger.error(f"Tool streaming failed: {e}")
            yield {"error": str(e)}
        finally:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
