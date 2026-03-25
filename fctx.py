import sys
import argparse
import pathlib
from core_logic import DataManager, FileOps, ActionBridge, logger

def main():
    parser = argparse.ArgumentParser(description="FileCortex CLI: Workspace Orchestrator")
    subparsers = parser.add_subparsers(dest="command")

    # Projects
    subparsers.add_parser("projects", help="List registered projects")

    # Staging
    stage_p = subparsers.add_parser("stage", help="Stage a file or directory")
    stage_p.add_argument("project", help="Project root path")
    stage_p.add_argument("path", help="Path to stage")

    # Categorize
    cat_p = subparsers.add_parser("categorize", help="Categorize staged files")
    cat_p.add_argument("project", help="Project root path")
    cat_p.add_argument("category", help="Category name")

    # Run Tool
    run_p = subparsers.add_parser("run", help="Run a custom tool on staged files")
    run_p.add_argument("project", help="Project root path")
    run_p.add_argument("tool", help="Tool name")

    args = parser.parse_args()
    data_mgr = DataManager()

    if args.command == "projects":
        for p in data_mgr.data["projects"]:
            print(f"- {p}")

    elif args.command == "stage":
        proj_path = str(pathlib.Path(args.project).resolve())
        file_path = str(pathlib.Path(args.path).resolve())
        proj = data_mgr.get_project_data(proj_path)
        if file_path not in proj["staging_list"]:
            proj["staging_list"].append(file_path)
            data_mgr.save()
            print(f"Staged: {file_path}")

    elif args.command == "categorize":
        proj_path = str(pathlib.Path(args.project).resolve())
        proj = data_mgr.get_project_data(proj_path)
        paths = proj["staging_list"]
        if not paths:
            print("Staging list is empty.")
            return
        moved = FileOps.batch_categorize(proj_path, paths, args.category)
        print(f"Moved {len(moved)} files to {args.category}")
        proj["staging_list"] = []
        data_mgr.save()

    elif args.command == "run":
        proj_path = str(pathlib.Path(args.project).resolve())
        proj = data_mgr.get_project_data(proj_path)
        template = proj["custom_tools"].get(args.tool)
        if not template:
            print(f"Tool '{args.tool}' not found.")
            return
        
        for p in proj["staging_list"]:
            print(f"Executing {args.tool} on {p}...")
            res = ActionBridge.execute_tool(template, p, proj_path)
            if "error" in res:
                print(f"ERROR: {res['error']}")
            else:
                print(f"EXIT CODE: {res['exit_code']}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
