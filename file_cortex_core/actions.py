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
            renamed_stack = []
            try:
                for old_p, (new_p, _) in final_targets.items():
                    pathlib.Path(old_p).rename(new_p)
                    renamed_stack.append((old_p, new_p))
            except Exception as e:
                logger.error(f"Batch rename failed: {e}. Attempting rollback of {len(renamed_stack)} items.")
                for old_p, new_p in reversed(renamed_stack):
                    try:
                        new_p.rename(old_p)
                    except Exception as rollback_e:
                        logger.error(f"Critical: Rollback failed for {new_p}: {rollback_e}")
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
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
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
        temp_path = path.with_suffix(path.suffix + '.tmp')
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(temp_path, path)
        except Exception as e:
            try:
                if temp_path.exists():
                    temp_path.unlink()
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
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for p_str in paths:
                p = pathlib.Path(p_str)
                if not p.exists(): continue
                arcname = p.relative_to(root_dir) if root_dir and root_dir in p.parents else p.name
                if p.is_file():
                    zipf.write(p, arcname)
                elif p.is_dir():
                    for root, _, files in os.walk(p):
                        for file in files:
                            full_f = pathlib.Path(root) / file
                            rel_base = root_dir if root_dir else p.parent
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
    def execute_tool(template, path_str, project_root):
        p = pathlib.Path(path_str)
        if not p.exists(): return {"error": "Path does not exist"}
        
        context = {
            "path": str(p),
            "name": p.name,
            "ext": p.suffix,
            "root": str(project_root),
            "parent": str(p.parent),
            "parent_name": p.parent.name
        }
        
        try:
            if os.name == 'nt':
                # Security Hardening for Windows
                # If there are no shell metacharacters, we use shell=False for maximum safety
                shell_metas = set("&|<>^%")
                has_meta = any(c in template for c in shell_metas)
                
                def win_quote(s):
                    # Windows CMD shell metacharacters that require escaping or quoting
                    # " is handled by replacing with \" and wrapping in " "
                    # Other characters like ^, &, |, <, >, %, ( ) are handled by wrapping in " "
                    # Our current strategy: wrap the whole string in double quotes and escape internal double quotes.
                    # This is generally safe for Windows paths in CMD.
                    return f'"{s.replace(chr(34), chr(92)+chr(34))}"'
                
                if not has_meta:
                    cmd_str = template.format(**context)
                    try:
                        args = shlex.split(cmd_str, posix=False)
                        logger.info(f"AUDIT - Executing external tool (Win/No-Shell): {args}")
                        res = subprocess.run(args, shell=False, capture_output=True, text=True, check=False)
                    except Exception:
                        logger.warning("shlex failed on Windows, falling back to shell=True")
                        safe_context = {k: win_quote(v) for k, v in context.items()}
                        # Re-format with quoted values
                        cmd_str = template.format(**safe_context)
                        res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, check=False)
                else:
                    # Template has metacharacters, we MUST use shell=True and be safe
                    safe_context = {k: win_quote(v) for k, v in context.items()}
                    cmd_str = template.format(**safe_context)
                    logger.info(f"AUDIT - Executing external tool (Win/Shell-Required): {cmd_str}")
                    res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, check=False)
            else:
                tokens = shlex.split(template, posix=True)
                final_cmd = [t.format(**context) for t in tokens]
                logger.info(f"AUDIT - Executing external tool (Unix/List): {' '.join(final_cmd)}")
                res = subprocess.run(final_cmd, shell=False, capture_output=True, text=True, check=False)
                
            return {"stdout": res.stdout, "stderr": res.stderr, "exit_code": res.returncode}
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {"error": str(e)}

    @staticmethod
    def create_process(template, path_str, project_root):
        """Creates a subprocess Popen object based on template and context."""
        p = pathlib.Path(path_str)
        if not p.exists(): raise FileNotFoundError("Path does not exist")
        
        context = {
            "path": str(p),
            "name": p.name,
            "ext": p.suffix,
            "root": str(project_root),
            "parent": str(p.parent),
            "parent_name": p.parent.name
        }
        
        if os.name == 'nt':
            shell_metas = set("&|<>^%")
            has_meta = any(c in template for c in shell_metas)
            
            def win_quote(s):
                return f'"{s.replace(chr(34), chr(92)+chr(34))}"'
            
            if not has_meta:
                cmd_str = template.format(**context)
                try:
                    args = shlex.split(cmd_str, posix=False)
                    logger.info(f"AUDIT - Creating process (Win/No-Shell): {args}")
                    return subprocess.Popen(
                        args, shell=False,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1, encoding='utf-8', errors='replace'
                    )
                except Exception:
                    safe_context = {k: win_quote(v) for k, v in context.items()}
                    cmd_str = template.format(**safe_context)
                    return subprocess.Popen(
                        cmd_str, shell=True,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1, encoding='utf-8', errors='replace'
                    )
            else:
                safe_context = {k: win_quote(v) for k, v in context.items()}
                cmd_str = template.format(**safe_context)
                logger.info(f"AUDIT - Creating process (Win/Shell-Required): {cmd_str}")
                return subprocess.Popen(
                    cmd_str, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, encoding='utf-8', errors='replace'
                )
        else:
            tokens = shlex.split(template, posix=True)
            final_cmd = [t.format(**context) for t in tokens]
            logger.info(f"AUDIT - Creating process (Unix/List): {' '.join(final_cmd)}")
            return subprocess.Popen(
                final_cmd, shell=False,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding='utf-8', errors='replace',
                start_new_session=True
            )

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
        
        try:
            process = ActionBridge.create_process(template, path_str, project_root)
            
            for line in process.stdout:
                yield {"out": line}
            
            process.wait()
            yield {"exit_code": process.returncode}
            
        except Exception as e:
            logger.error(f"Tool streaming failed: {e}")
            yield {"error": str(e)}
