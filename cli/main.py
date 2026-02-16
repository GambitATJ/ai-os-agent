import argparse
import os
from features.downloads import organize_downloads
from features.projects import create_project
from features.vault import generate_password_action
from features.vault import scan_password_fields
from features.vault import vault

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
    
    # Password vault
    vault_gen = subparsers.add_parser("generate-password")
    vault_gen.add_argument("label", help="Password label (e.g., 'BankXYZ')")
    vault_gen.add_argument("--length", type=int, default=20, help="Password length")
    vault_gen.add_argument("--no-symbols", action="store_true", help="No symbols")
    vault_gen.add_argument("--apply", action="store_true", help="Apply (not dry-run)")
    
    vault_scan = subparsers.add_parser("scan-passwords")
    vault_scan.add_argument("scope", default=".", nargs="?", help="Folder to scan")
    vault_scan.add_argument("--apply", action="store_true", help="Apply (not dry-run)")

    # App autofill
    autofill_app = subparsers.add_parser("autofill-app")
    autofill_app.add_argument("app", help="App name (spotify, discord)")
    autofill_app.add_argument("--apply", action="store_true")
    
    # Config autofill
    autofill_config = subparsers.add_parser("autofill-config")
    autofill_config.add_argument("file", help="Config file path")
    autofill_config.add_argument("--apply", action="store_true")

    args = parser.parse_args()
    
    if args.command == "organize-downloads":
        organize_downloads(args.path, dry_run=not args.apply)
    elif args.command == "create-project":
        create_project(args.name, args.location, args.type, dry_run=not args.apply)
    elif args.command == "generate-password":
        symbols = not args.no_symbols
        generate_password_action(args.label, args.length, 
                               uppercase=True, lowercase=True, 
                               digits=True, symbols=symbols,
                               dry_run=not args.apply)
    elif args.command == "scan-passwords":
        scan_password_fields(args.scope, dry_run=not args.apply)
    elif args.command == "autofill-app":
        vault.autofill_app(args.app, dry_run=not args.apply)
    elif args.command == "autofill-config":
        vault.autofill_config(args.file, dry_run=not args.apply)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

