import pathlib
import os
import shutil
import zipfile
import sys
import subprocess
import shlex

from .config import DataManager, logger
from .security import PathValidator
from .utils import FileUtils

import re

class FileOps:
    @staticmethod
    def batch_rename(project_path, paths, pattern, replacement, dry_run=True):
        """
        Renames multiple files using regex.
        Returns a list of (old_path, new_path, status) where status is 'ok', 'conflict', or 'error'.
        """
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex: {e}")

        results = []
        # Phase 1: Calculate new names and check for internal conflicts in the selection
        new_names = {}
        for p_str in paths:
            p = pathlib.Path(p_str)
            new_name = regex.sub(replacement, p.name, count=1)
            if new_name == p.name:
                continue # No change
            
            new_path = p.parent / new_name
            new_names[p_str] = new_path

        # Check for destination existence and selection collisions
        final_targets = {}
        target_norm_set = set()
        
        def norm_path_str(p):
            abs_p = str(p.absolute())
            return abs_p.lower() if os.name == 'nt' else abs_p

        for old_p, new_p in new_names.items():
            status = 'ok'
            norm_new = norm_path_str(new_p)
            
            # Check filesystem AND the currently planned batch targets
            if new_p.exists() or norm_new in target_norm_set:
                status = 'conflict'
            
            # Simple conflict resolution: add suffix if it's a conflict
            if status == 'conflict':
                base = new_p.stem
                ext = new_p.suffix
                counter = 1
                while True:
                    candidate = new_p.parent / f"{base}_{counter}{ext}"
                    norm_candidate = norm_path_str(candidate)
                    if not candidate.exists() and norm_candidate not in target_norm_set:
                        new_p = candidate
                        status = 'renamed_with_suffix'
                        break
                    counter += 1

            final_targets[old_p] = (new_p, status)
            target_norm_set.add(norm_path_str(new_p))
            results.append({"old": old_p, "new": str(new_p), "status": status})

        if not dry_run:
            # Phase 2: Check for cross-device rename risks (C1 Critical)
            # Pre-check all sources are in the same relative system as targets
            # On some systems, os.rename fails across mount points or drives.
            # While they are likely in the same project root, symlinks could break this.
            
            renamed_stack = []
            try:
                for old_p, (new_p, _) in final_targets.items():
                    p_old = pathlib.Path(old_p)
                    # Performance: rename will throw if on different devices anyway.
                    p_old.rename(new_p)
                    renamed_stack.append((old_p, new_p))
            except Exception as e:
                logger.error(f"Batch rename failed: {e}. Attempting rollback of {len(renamed_stack)} items.")
                # C1 Fix: Improved rollback with reverse order and better logging
                rollback_errors = []
                for old_p_str, new_p_obj in reversed(renamed_stack):
                    try:
                        new_p_obj.rename(old_p_str)
                    except Exception as rollback_e:
                        rollback_errors.append(f"{new_p_obj} -> {old_p_str}: {rollback_e}")
                        logger.critical(f"FATAL: Rollback failed for {new_p_obj}: {rollback_e}")
                
                if rollback_errors:
                    raise RuntimeError(f"Batch rename failed and rollback was incomplete: {e}. Manual fix required for: {', '.join(rollback_errors)}")
                raise e
        
        return results

    @staticmethod
    def rename_file(old_path_str, new_name):
        old_path = pathlib.Path(old_path_str)
        if not old_path.exists():
            raise FileNotFoundError("Target path does not exist.")
        new_path = old_path.parent / new_name
        if new_path.exists():
            raise FileExistsError("A file with new name already exists.")
        old_path.rename(new_path)
        return str(new_path)

    @staticmethod
    def delete_file(path_str):
        path = pathlib.Path(path_str)
        if not path.exists():
            raise FileNotFoundError("Target path does not exist.")
            
        def _handle_readonly(func, path, exc_info):
            # Clear the read-only bit and retry
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)

        if path.is_file():
            try:
                path.unlink()
            except PermissionError:
                # CR-24 Fix: Try clearing read-only bit
                import stat
                os.chmod(path, stat.S_IWRITE)
                path.unlink()
        elif path.is_dir():
            shutil.rmtree(path, onerror=_handle_readonly)
        return True

    @staticmethod
    def move_file(src_path_str, dst_dir_str):
        src_path = pathlib.Path(src_path_str)
        dst_dir = pathlib.Path(dst_dir_str)
        if not src_path.exists(): raise FileNotFoundError("Source path does not exist.")
        if not dst_dir.exists() or not dst_dir.is_dir(): raise FileNotFoundError("Destination directory does not exist.")
        
        dst_path = dst_dir / src_path.name
        if dst_path.exists(): raise FileExistsError("A file with same name exists in destination.")
        
        shutil.move(str(src_path), str(dst_path))
        return str(dst_path)

    @staticmethod
    def save_content(path_str, content):
        path = pathlib.Path(path_str)
        if not path.exists(): raise FileNotFoundError("Target file does not exist.")
        if not path.is_file(): raise IsADirectoryError("Target is a directory.")
        if FileUtils.is_binary(path): raise ValueError("Cannot save binary file as text.")
        
        # Atomic Write: write to temporary file then swap
        # C3 Critical: Use tempfile.NamedTemporaryFile to avoid name collisions in concurrent saves
        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            # Use os.replace for atomic replacement
            os.replace(temp_path, path)
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception: # Block double failure
                pass
            raise e
        return True

    @staticmethod
    def create_item(parent_path_str, name, is_dir=False):
        parent_path = pathlib.Path(parent_path_str)
        if not parent_path.exists() or not parent_path.is_dir():
            raise FileNotFoundError("Parent directory does not exist.")
        
        new_path = parent_path / name
        if new_path.exists():
            raise FileExistsError(f"{'Directory' if is_dir else 'File'} already exists.")
        
        if is_dir:
            new_path.mkdir()
        else:
            new_path.touch()
        return str(new_path)

    @staticmethod
    def archive_selection(paths, output_path_str, root_dir=None):
        output_path = pathlib.Path(output_path_str)
        # CR-C06 Fix: Normalize root_dir to pathlib.Path for correct relative_to comparison
        root_dir_p = pathlib.Path(root_dir).resolve() if root_dir else None
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for p_str in paths:
                p = pathlib.Path(p_str).resolve()
                if not p.exists(): continue
                arcname = p.relative_to(root_dir_p) if root_dir_p and (root_dir_p == p or root_dir_p in p.parents) else p.name
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
    def batch_categorize(project_path, paths, category_name):
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
    @staticmethod
    def _prepare_execution(template, path_str, project_root, force_shell=None):
        """
        Internal helper to prepare command arguments and shell status.
        Returns: (exec_args, is_shell, context)
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
            "parent_name": p.parent.name
        }
        
        if os.name == 'nt':
            # Security Hardening for Windows
            shell_metas = set("&|<>^%")
            # If template has shell meta-characters or is forced, use shell
            is_shell = any(c in template for c in shell_metas) or (force_shell is True)
            
            def win_quote(s):
                # Security: Quote for Windows CMD, escaping " to prevent injection.
                # Escape % to %% to prevent environment variable expansion in shell=True
                return f'"{s.replace(chr(34), chr(92)+chr(34)).replace("%", "%%")}"'
            
            # Optimization: Try to detect if the first word is a valid executable
            if not is_shell and force_shell is not False:
                first_word = template.split(None, 1)[0].strip('"')
                if not shutil.which(first_word):
                    # Likely a shell builtin like 'dir', 'echo', or a batch file
                    is_shell = True

            if is_shell:
                # Use shell=True with quoted values
                safe_context = {k: win_quote(v) for k, v in context.items()}
                return template.format(**safe_context), True, context
            else:
                # Use list-mode (shell=False) for maximum safety
                cmd_str = template.format(**context)
                try:
                    raw_args = shlex.split(cmd_str, posix=False)
                    args = [t.strip('"') for t in raw_args]
                    return args, False, context
                except Exception:
                    # Fallback if shlex fails: use shell and hope for the best (but still quote)
                    safe_context = {k: win_quote(v) for k, v in context.items()}
                    return template.format(**safe_context), True, context
        else:
            # Unix-like: Always prefer list mode (shell=False) with shlex
            tokens = shlex.split(template, posix=True)
            final_cmd = [t.format(**context) for t in tokens]
            return final_cmd, False, context

    @staticmethod
    def execute_tool(template, path_str, project_root):
        """
        Execute a tool on a file path. Returns {stdout, stderr, exit_code, status}.
        """
        try:
            cmd, is_shell, _ = ActionBridge._prepare_execution(template, path_str, project_root)
            
            # Fetch timeout from env or config
            timeout = int(os.environ.get("FCTX_EXEC_TIMEOUT", 
                                         DataManager().data.get("execution_timeout", 300)))

            logger.info(f"AUDIT - Executing external tool (Shell={is_shell}): {cmd if isinstance(cmd, list) else cmd.split()[0] + '...'}")
            
            with subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                shell=is_shell,
                cwd=project_root if os.path.exists(project_root) and os.path.isdir(project_root) else None
            ) as proc:
                try:
                    stdout, stderr = proc.communicate(timeout=timeout)
                    return {
                        "stdout": stdout,
                        "stderr": stderr,
                        "exit_code": proc.returncode,
                        "pid": proc.pid,
                        "status": "success"
                    }
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        # Use taskkill to ensure child processes are also handled on Windows
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        # Kill entire process group on Unix
                        import signal
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        except Exception:
                            proc.kill()
                    stdout, stderr = proc.communicate() # Drain pipes
                    return {
                        "stdout": stdout, 
                        "stderr": stderr, 
                        "exit_code": -1, 
                        "error": "command timed out",
                        "status": "timeout"
                    }
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {"stdout": "", "stderr": str(e), "exit_code": -1, "error": str(e), "status": "error"}

    @staticmethod
    def create_process(template, path_str, project_root):
        """Creates a subprocess Popen object based on template and context."""
        cmd, is_shell, _ = ActionBridge._prepare_execution(template, path_str, project_root)
        
        logger.info(f"AUDIT - Creating process (Shell={is_shell}): {cmd if isinstance(cmd, list) else cmd.split()[0] + '...'}")
        
        popen_kwargs = {
            "shell": is_shell,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
            "encoding": 'utf-8',
            "errors": 'replace'
        }
        
        # Enable process group leadership on Unix for clean cleanup
        if os.name != 'nt':
            popen_kwargs["start_new_session"] = True
            
        return subprocess.Popen(cmd, **popen_kwargs)

    @staticmethod
    def stream_tool(template, path_str, project_root):
        p = pathlib.Path(path_str)
        if not p.exists():
            yield {"error": "Path does not exist"}
            return
        
        context = {
            "path": str(p),
            "name": p.name,
            "ext": p.suffix,
            "root": str(project_root),
            "parent": str(p.parent),
            "parent_name": p.parent.name
        }
        
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
                    try: process.kill()
                    except: pass
