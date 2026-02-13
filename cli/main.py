import argparse
from features.downloads import organize_downloads


def main():
    parser = argparse.ArgumentParser(description="AI OS Agent CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # Downloads organizer
    org = subparsers.add_parser("organize-downloads")
    org.add_argument("--path", default="~/Downloads", help="Path to organize")
    org.add_argument("--apply", action="store_true", help="Apply (not dry-run)")
    
    args = parser.parse_args()
    
    if args.command == "organize-downloads":
        organize_downloads(args.path, dry_run=not args.apply)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
