#!/usr/bin/env python3
"""FileCortex CLI - Workspace Orchestrator.

A command-line interface for managing project workspaces, staging files,
executing custom tools, searching files, and exporting AI context.
"""

import argparse
import contextlib
import pathlib
import sys

from file_cortex_core import (
    ActionBridge,
    ContextFormatter,
    DataManager,
    FileOps,
    FormatUtils,
    PathValidator,
    logger,
    search_generator,
)


def _resolve_project(data_mgr: DataManager, project: str) -> str | None:
    """Resolves and validates a project root path.

    Args:
        data_mgr: DataManager instance.
        project: Project path string.

    Returns:
        Normalized project root or None if invalid.
    """
    proj_root = data_mgr.resolve_project_root(project)
    if not proj_root:
        print(f"ERROR: Project '{project}' is not registered or is unsafe.")
    return proj_root


def cmd_open(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'open' subcommand.

    Returns:
        True on success, False on failure (main() exits with code 1).
    """
    try:
        validated = PathValidator.validate_project(args.path)
        abs_path = str(validated)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return False
    except NotADirectoryError as e:
        print(f"ERROR: {e}")
        return False
    except PermissionError as e:
        print(f"ERROR: {e}")
        return False

    data_mgr.add_to_recent(abs_path)
    data_mgr.get_project_data_obj(abs_path)
    data_mgr.save()
    print(f"PROJECT REGISTERED: {abs_path}")
    return True


def cmd_projects(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'projects' subcommand.

    Returns:
        True (informational command; empty list is not an error).
    """
    projects = data_mgr.config.projects
    if not projects:
        print("No registered projects.")
        return True
    for p in projects:
        name = pathlib.Path(p).name
        print(f"  {name}  →  {p}")
    return True


def cmd_stage(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'stage' subcommand.

    Returns:
        True on success, False on failure (main() exits with code 1).
    """
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return False

    file_path_str = PathValidator.norm_path(args.path)
    if not PathValidator.is_safe(file_path_str, proj_root):
        logger.error(f"Security: CLI block unsafe path: {args.path}")
        print(f"ERROR: Path '{args.path}' is outside project root or unsafe.")
        return False

    # CRITICAL: use get_project_data_obj() (live ProjectConfig), NOT
    # get_project_data() which returns a disconnected model_dump() snapshot.
    # Mutating the snapshot was silently lost on save().
    proj = data_mgr.get_project_data_obj(proj_root)
    if file_path_str not in proj.staging_list:
        proj.staging_list.append(file_path_str)
        data_mgr.save()
        print(f"Staged: {file_path_str}")
    else:
        print(f"Already staged: {file_path_str}")
    return True


def cmd_search(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'search' subcommand.

    Returns:
        True on success (including no matches), False on failure.
    """
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return False

    # Align with the project's configured content-search size limit instead
    # of the module default (5MB), matching the Web/WS behavior.
    proj_data = data_mgr.get_project_data(proj_root)
    max_size = proj_data.get("max_search_size_mb", 10)

    results = list(search_generator(
        pathlib.Path(proj_root),
        args.query,
        args.mode,
        args.excludes or "",
        max_size_mb=max_size,
    ))
    if not results:
        print("No matches found.")
        return True

    for r in results[:args.limit]:
        rel = pathlib.Path(r["path"])
        with contextlib.suppress(ValueError):
            rel = rel.relative_to(proj_root)
        match_type = r.get("match_type", "Match")
        size_fmt = FormatUtils.format_size(r.get("size", 0))
        print(f"  [{match_type}] {rel}  ({size_fmt})")

    total = len(results)
    if total > args.limit:
        print(f"\n  ... and {total - args.limit} more (use --limit to show more)")
    print(f"\n  Total: {total} matches")
    return True


def cmd_export(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'export' subcommand.

    Returns:
        True on success, False on failure (main() exits with code 1).
    """
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return False

    proj_data = data_mgr.get_project_data(proj_root)
    paths = proj_data.get("staging_list", [])

    if not paths:
        print("Staging list is empty. Use 'fctx stage' to add files first.")
        return False

    fmt = args.format
    use_noise = args.noise_reducer

    if fmt == "xml":
        content = ContextFormatter.to_xml(
            paths,
            root_dir=proj_root,
            apply_noise_reducer=use_noise,
        )
    else:
        content = ContextFormatter.to_markdown(
            paths,
            root_dir=proj_root,
            apply_noise_reducer=use_noise,
        )

    if args.output:
        out_path = pathlib.Path(args.output)
        if not out_path.is_absolute():
            out_path = pathlib.Path(proj_root) / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        tokens = FormatUtils.estimate_tokens(content)
        print(f"Exported to: {out_path}")
        print(f"  Format: {fmt}, ~{FormatUtils.format_number(tokens)} tokens")
    else:
        sys.stdout.write(content)
    return True


def cmd_categorize(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'categorize' subcommand.

    Returns:
        True on success, False on failure (main() exits with code 1).
    """
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return False

    # CRITICAL: use get_project_data_obj() (live ProjectConfig), NOT
    # get_project_data() which returns a disconnected model_dump() snapshot.
    # Reassigning the snapshot key was silently lost on save(), leaving the
    # real staging list populated after categorize.
    proj = data_mgr.get_project_data_obj(proj_root)
    paths = list(proj.staging_list)
    if not paths:
        print("Staging list is empty.")
        return False
    try:
        moved = FileOps.batch_categorize(proj_root, paths, args.category)
        print(f"Moved {len(moved)} files to {args.category}")
        proj.staging_list = [path for path in paths if pathlib.Path(path).exists()]
        data_mgr.save()
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def cmd_run(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'run' subcommand.

    Returns:
        True on success, False on failure (main() exits with code 1).
    """
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return False

    proj_data = data_mgr.get_project_data(proj_root)
    template = proj_data.get("custom_tools", {}).get(args.tool)
    if not template:
        print(f"Tool '{args.tool}' not found.")
        return False

    for p in proj_data["staging_list"]:
        if not PathValidator.is_safe(p, proj_root):
            print(f"SKIPPING unsafe path: {p}")
            continue

        print(f"Executing {args.tool} on {p}...")
        res = ActionBridge.execute_tool(template, p, proj_root)
        if "error" in res:
            print(f"ERROR: {res['error']}")
        else:
            print(f"EXIT CODE: {res['exit_code']}")
    return True


def cmd_copy(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'copy' subcommand (batch copy, one or more sources).

    Returns:
        True on success, False on failure (main() exits with code 1).
    """
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return False

    # Validate every source path before touching the filesystem so a
    # single unsafe entry aborts the whole batch (matches core semantics).
    normalized_srcs: list[str] = []
    for src in args.srcs:
        src_str = PathValidator.norm_path(src)
        if not PathValidator.is_safe(src_str, proj_root):
            logger.error(f"Security: CLI block unsafe src: {src}")
            print(f"ERROR: Source '{src}' is outside project root or unsafe.")
            return False
        normalized_srcs.append(src_str)

    dst_str = PathValidator.norm_path(args.dst_dir)
    if not PathValidator.is_safe(dst_str, proj_root):
        logger.error(f"Security: CLI block unsafe dst: {args.dst_dir}")
        print(
            f"ERROR: Destination '{args.dst_dir}' is outside project root "
            f"or unsafe."
        )
        return False

    try:
        result = FileOps.copy_item(
            srcs=normalized_srcs,
            dst_dir_str=dst_str,
            project_root=proj_root,
        )
    except (FileNotFoundError, FileExistsError, PermissionError, ValueError) as e:
        print(f"ERROR: {e}")
        return False
    for p in result:
        print(f"Copied: {p}")
    return True


def cmd_extract(args: argparse.Namespace, data_mgr: DataManager) -> bool:
    """Handles the 'extract' subcommand.

    Returns:
        True on success, False on failure (main() exits with code 1).
    """
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return False

    dst_str = PathValidator.norm_path(args.dst_dir)
    if not PathValidator.is_safe(dst_str, proj_root):
        logger.error(f"Security: CLI block unsafe dst: {args.dst_dir}")
        print(
            f"ERROR: Destination '{args.dst_dir}' is outside project root "
            f"or unsafe."
        )
        return False

    # The archive may live outside the project workspace; only the
    # extraction destination must be safe (validated above and again inside
    # FileOps.extract_archive on a per-member basis).
    try:
        extracted = FileOps.extract_archive(args.zip_path, dst_str, proj_root)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        print(f"ERROR: {e}")
        return False
    print(f"Extracted {len(extracted)} entries to: {dst_str}")
    return True


def main() -> None:
    """Entry point for the FileCortex CLI."""
    parser = argparse.ArgumentParser(
        description="FileCortex CLI: Workspace Orchestrator"
    )
    subparsers = parser.add_subparsers(dest="command")

    open_p = subparsers.add_parser(
        "open", help="Open and register a new project workspace"
    )
    open_p.add_argument("path", help="Project root path to register")

    subparsers.add_parser("projects", help="List registered projects")

    stage_p = subparsers.add_parser("stage", help="Stage a file or directory")
    stage_p.add_argument("project", help="Project root path")
    stage_p.add_argument("path", help="Path to stage")

    search_p = subparsers.add_parser(
        "search", help="Search files within a project workspace"
    )
    search_p.add_argument("project", help="Project root path")
    search_p.add_argument("query", help="Search query string")
    search_p.add_argument(
        "--mode", default="smart",
        choices=["smart", "exact", "regex", "content"],
        help="Search mode (default: smart)",
    )
    search_p.add_argument(
        "--excludes", default="",
        help="Space-separated exclusion patterns",
    )
    search_p.add_argument(
        "--limit", type=int, default=50,
        help="Max results to display (default: 50)",
    )

    export_p = subparsers.add_parser(
        "export", help="Export staged files as AI context"
    )
    export_p.add_argument("project", help="Project root path")
    export_p.add_argument(
        "--format", default="markdown",
        choices=["markdown", "xml"],
        help="Export format (default: markdown)",
    )
    export_p.add_argument(
        "--output", "-o", default=None,
        help="Output file path (prints to stdout if omitted)",
    )
    export_p.add_argument(
        "--noise-reducer", action="store_true", default=False,
        help="Apply noise reduction to exported content",
    )

    cat_p = subparsers.add_parser("categorize", help="Categorize staged files")
    cat_p.add_argument("project", help="Project root path")
    cat_p.add_argument("category", help="Category name")

    run_p = subparsers.add_parser("run", help="Run a custom tool on staged files")
    run_p.add_argument("project", help="Project root path")
    run_p.add_argument("tool", help="Tool name")

    copy_p = subparsers.add_parser(
        "copy",
        help="Copy one or more files/directories within a project",
    )
    copy_p.add_argument("project", help="Project root path")
    copy_p.add_argument(
        "srcs",
        nargs="+",
        help="Source paths to copy (one or more)",
    )
    copy_p.add_argument(
        "dst_dir", help="Destination directory relative to project root"
    )

    extract_p = subparsers.add_parser("extract", help="Extract a ZIP archive into a project")
    extract_p.add_argument("project", help="Project root path")
    extract_p.add_argument("zip_path", help="Path to ZIP archive")
    extract_p.add_argument("dst_dir", help="Destination directory relative to project root")

    args = parser.parse_args()
    data_mgr = DataManager()

    handlers = {
        "open": cmd_open,
        "projects": cmd_projects,
        "stage": cmd_stage,
        "search": cmd_search,
        "export": cmd_export,
        "categorize": cmd_categorize,
        "run": cmd_run,
        "copy": cmd_copy,
        "extract": cmd_extract,
    }

    handler = handlers.get(args.command)
    if handler:
        ok = handler(args, data_mgr)
        if ok is False:
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
