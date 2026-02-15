import argparse
import os
from features.downloads import organize_downloads
from features.projects import create_project


def main():
    parser = argparse.ArgumentParser(description="AI OS Agent CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # Downloads organizer
    org = subparsers.add_parser("organize-downloads")
    org.add_argument("--path", default="~/Downloads", help="Path to organize")
    org.add_argument("--apply", action="store_true", help="Apply (not dry-run)")
    
    # Project scaffold
    proj = subparsers.add_parser("create-project")
    proj.add_argument("name", help="Project name")
    proj.add_argument("--location", default="~/Projects", help="Base location")
    proj.add_argument("--type", default="python_project", help="Project type")
    proj.add_argument("--apply", action="store_true", help="Apply (not dry-run)")
    
    args = parser.parse_args()
    
    if args.command == "organize-downloads":
        organize_downloads(args.path, dry_run=not args.apply)
    elif args.command == "create-project":
        create_project(args.name, args.location, args.type, dry_run=not args.apply)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

