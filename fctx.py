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


def cmd_open(args: argparse.Namespace, data_mgr: DataManager) -> None:
    """Handles the 'open' subcommand."""
    try:
        validated = PathValidator.validate_project(args.path)
        abs_path = str(validated)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return
    except NotADirectoryError as e:
        print(f"ERROR: {e}")
        return
    except PermissionError as e:
        print(f"ERROR: {e}")
        return

    data_mgr.add_to_recent(abs_path)
    print(f"PROJECT REGISTERED: {abs_path}")


def cmd_projects(args: argparse.Namespace, data_mgr: DataManager) -> None:
    """Handles the 'projects' subcommand."""
    projects = data_mgr.data["projects"]
    if not projects:
        print("No registered projects.")
        return
    for p in projects:
        name = pathlib.Path(p).name
        print(f"  {name}  →  {p}")


def cmd_stage(args: argparse.Namespace, data_mgr: DataManager) -> None:
    """Handles the 'stage' subcommand."""
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return

    file_path_str = PathValidator.norm_path(args.path)
    if not PathValidator.is_safe(file_path_str, proj_root):
        logger.error(f"Security: CLI block unsafe path: {args.path}")
        print(f"ERROR: Path '{args.path}' is outside project root or unsafe.")
        return

    proj_data = data_mgr.get_project_data(proj_root)
    if file_path_str not in proj_data["staging_list"]:
        proj_data["staging_list"].append(file_path_str)
        data_mgr.save()
        print(f"Staged: {file_path_str}")
    else:
        print(f"Already staged: {file_path_str}")


def cmd_search(args: argparse.Namespace, data_mgr: DataManager) -> None:
    """Handles the 'search' subcommand."""
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return

    results = list(search_generator(
        pathlib.Path(proj_root),
        args.query,
        args.mode,
        args.excludes or "",
    ))
    if not results:
        print("No matches found.")
        return

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


def cmd_export(args: argparse.Namespace, data_mgr: DataManager) -> None:
    """Handles the 'export' subcommand."""
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return

    proj_data = data_mgr.get_project_data(proj_root)
    paths = proj_data.get("staging_list", [])

    if not paths:
        print("Staging list is empty. Use 'fctx stage' to add files first.")
        return

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


def cmd_categorize(args: argparse.Namespace, data_mgr: DataManager) -> None:
    """Handles the 'categorize' subcommand."""
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return

    proj_data = data_mgr.get_project_data(proj_root)
    paths = proj_data["staging_list"]
    if not paths:
        print("Staging list is empty.")
        return
    try:
        moved = FileOps.batch_categorize(proj_root, paths, args.category)
        print(f"Moved {len(moved)} files to {args.category}")
        proj_data["staging_list"] = []
        data_mgr.save()
    except Exception as e:
        print(f"ERROR: {e}")


def cmd_run(args: argparse.Namespace, data_mgr: DataManager) -> None:
    """Handles the 'run' subcommand."""
    proj_root = _resolve_project(data_mgr, args.project)
    if not proj_root:
        return

    proj_data = data_mgr.get_project_data(proj_root)
    template = proj_data["custom_tools"].get(args.tool)
    if not template:
        print(f"Tool '{args.tool}' not found.")
        return

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
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args, data_mgr)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
