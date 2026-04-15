import sys
import argparse
import pathlib
from file_cortex_core import DataManager, FileOps, ActionBridge, PathValidator, logger

def main():
    parser = argparse.ArgumentParser(description="FileCortex CLI: Workspace Orchestrator")
    subparsers = parser.add_subparsers(dest="command")

    # Open
    open_p = subparsers.add_parser("open", help="Open and register a new project workspace")
    open_p.add_argument("path", help="Project root path to register")

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

    if args.command == "open":
        abs_path = PathValidator.norm_path(args.path)
        if not os.path.exists(abs_path):
            print(f"ERROR: Path '{abs_path}' does not exist.")
            return
        if not os.path.isdir(abs_path):
            print(f"ERROR: Path '{abs_path}' is not a directory.")
            return
        # Security: Blocking system root or forbidden paths
        # Actually is_safe needs project root, but for REGISTRATION, we check against sys root
        if not PathValidator.is_safe(abs_path, os.path.abspath(os.sep)):
             print(f"ERROR: Cannot register unsafe system directory: {abs_path}")
             return
             
        data_mgr.add_to_recent(abs_path)
        print(f"PROJECT REGISTERED: {abs_path}")
        return

    elif args.command == "projects":
        for p in data_mgr.data["projects"]:
            print(f"- {p}")

    elif args.command == "stage":
        proj_root = data_mgr.resolve_project_root(args.project)
        if not proj_root:
            print(f"ERROR: Project '{args.project}' is not registered or is unsafe.")
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

    elif args.command == "categorize":
        proj_root = data_mgr.resolve_project_root(args.project)
        if not proj_root:
            print(f"ERROR: Project '{args.project}' is not registered.")
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

    elif args.command == "run":
        proj_root = data_mgr.resolve_project_root(args.project)
        if not proj_root:
            print(f"ERROR: Project '{args.project}' is not registered.")
            return
            
        proj_data = data_mgr.get_project_data(proj_root)
        template = proj_data["custom_tools"].get(args.tool)
        if not template:
            print(f"Tool '{args.tool}' not found.")
            return
        
        for p in proj_data["staging_list"]:
            # Safety double check for tools
            if not PathValidator.is_safe(p, proj_root):
                print(f"SKIPPING unsafe path: {p}")
                continue
                
            print(f"Executing {args.tool} on {p}...")
            res = ActionBridge.execute_tool(template, p, proj_root)
            if "error" in res:
                print(f"ERROR: {res['error']}")
            else:
                print(f"EXIT CODE: {res['exit_code']}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
