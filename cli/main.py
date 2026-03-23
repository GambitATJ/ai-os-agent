import argparse
import os
import sys
import threading
import time
import warnings
import logging

# ── Silence all ML/tokenizer noise before importing anything heavy ──────────
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from features.downloads import organize_downloads
from features.projects import create_project
from features.vault import generate_password_action
from features.vault import scan_password_fields
from features.vault import vault
from features.rename import bulk_rename_action
from features.receipts import find_receipts_action
from core.nlu_router import route, get_model
from core.workflow import run_workflow
from checkpoint_manager import CheckpointManager
from db_manager import SQLiteManager
import numpy as np

# ── Re-enable logging for our own output ─────────────────────────────────────
logging.disable(logging.NOTSET)


class Spinner:
    """Simple CLI spinner shown while a task is running."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Processing"):
        self.message = message
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        i = 0
        while not self._stop_event.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r{frame}  {self.message}...")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1

    def start(self):
        self._thread.start()

    def stop(self, final_msg: str = ""):
        self._stop_event.set()
        self._thread.join()
        sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")  # clear line
        sys.stdout.flush()
        if final_msg:
            print(final_msg)

def interactive_mode():
    print("🤖 AI-OS Interactive Mode (type 'exit' to quit)\n")

    from core.nlu_router import route
    from core.workflow import run_workflow

    while True:
        text = input("ai-os > ")

        if text.lower() in ["exit", "quit"]:
            break

        # --- Undo Logic ---
        if any(substring in text.lower() for substring in ['undo that', 'revert last', 'undo last', 'roll back']):
            cm = CheckpointManager()
            print(cm.restore())
            continue

        if text.lower().startswith('undo '):
            query_str = text[5:].strip()
            if query_str:
                model = get_model()
                query_embedding = model.encode([query_str])[0]
                db = SQLiteManager()
                rows = db.fetch_all("checkpoints")
                db.close()
                if rows:
                    best_id = None
                    best_score = -1
                    for row in rows:
                        cmd_emb = model.encode([row["command_text"]])[0]
                        score = float(np.dot(query_embedding, cmd_emb) / 
                                      max(np.linalg.norm(query_embedding) * np.linalg.norm(cmd_emb), 1e-9))
                        if score > best_score:
                            best_score = score
                            best_id = row["id"]
                    if best_id is not None:
                        cm = CheckpointManager()
                        print(cm.restore(checkpoint_id=best_id))
                        continue

        try:
            ctr = route(text)
            run_workflow(ctr, dry_run=False)
        except Exception as e:
            print(f"❌ {e}")

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
    
    #Rename
    bulk_rename = subparsers.add_parser("bulk-rename")
    bulk_rename.add_argument("source_dir", help="Directory to rename")
    bulk_rename.add_argument("--pattern", default="date_slug", 
                            choices=["date_slug", "number", "timestamp"], 
                            help="Rename pattern")
    bulk_rename.add_argument("--apply", dest="dry_run", action="store_false")

    #Find Receipts
    find_receipts_parser = subparsers.add_parser("find-receipts", help="AI-powered document search")
    find_receipts_parser.add_argument("source_dir")                          # REQUIRED
    find_receipts_parser.add_argument("--query", default="receipt", help="What to search for (e.g. 'Starbucks coffee')")
    find_receipts_parser.add_argument("--export", help="Export directory")
    find_receipts_parser.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        default=True,
        help="Execute (not dry-run)"
    )

    nl = subparsers.add_parser("nl")
    nl.add_argument("text", help="Natural language command")

    chat = subparsers.add_parser("chat")

    hotkey_p = subparsers.add_parser("hotkey", help="Start global hotkey daemon")
    hotkey_p.add_argument(
        "--key",
        default="<ctrl>+<alt>+v",
        help="Hotkey combination (default: <ctrl>+<alt>+v)"
    )

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
    elif args.command == "bulk-rename":
        bulk_rename_action(args.source_dir, args.pattern, args.dry_run)
    elif args.command == "find-receipts":
        find_receipts_action(args.source_dir, args.query, args.export, args.dry_run)
    elif args.command == "nl":
        spinner = Spinner("Running")
        spinner.start()
        
        # --- Undo Logic ---
        text_lower = args.text.lower()
        if any(substring in text_lower for substring in ['undo that', 'revert last', 'undo last', 'roll back']):
            spinner.stop()
            cm = CheckpointManager()
            print(cm.restore())
            return

        if text_lower.startswith('undo '):
            query_str = args.text[5:].strip()
            if query_str:
                model = get_model()
                query_embedding = model.encode([query_str])[0]
                db = SQLiteManager()
                rows = db.fetch_all("checkpoints")
                db.close()
                if rows:
                    best_id = None
                    best_score = -1
                    for row in rows:
                        cmd_emb = model.encode([row["command_text"]])[0]
                        score = float(np.dot(query_embedding, cmd_emb) / 
                                      max(np.linalg.norm(query_embedding) * np.linalg.norm(cmd_emb), 1e-9))
                        if score > best_score:
                            best_score = score
                            best_id = row["id"]
                    if best_id is not None:
                        spinner.stop()
                        cm = CheckpointManager()
                        print(cm.restore(checkpoint_id=best_id))
                        return
        try:
            ctr = route(args.text)
            run_workflow(ctr, dry_run=False)
        except Exception as e:
            spinner.stop()
            print(f"❌ {e}")
        else:
            spinner.stop()
    elif args.command == "chat":
        interactive_mode()
    elif args.command == "hotkey":
        from hotkey_daemon import run_daemon
        run_daemon(args.key)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

