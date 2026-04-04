import os
import subprocess
import sys
import json
import re
from datetime import datetime
from core.policy import check_shell_plan
from db_manager import SQLiteManager
from core.llm_planner import generate_paraphrases
from checkpoint_manager import CheckpointManager

def execute_shell_plan(ctr, dry_run: bool = False) -> bool:
    """
    Takes a SHELL_PLAN CTR object. Runs the full flow:
    policy check → user approval → execution → save prompt.
    Returns True if execution completed, False if cancelled.
    """
    
    plan = ctr.params
    commands = plan["commands"]
    intent_description = plan.get("intent_description", "user-defined task")
    
    is_replay = ctr.params.get("_is_saved_replay", False)
    
    if not is_replay:
        print(f"\n{'─'*50}")
        print(f"  🤖  {intent_description}")
        print(f"{'─'*50}")
        for i, cmd in enumerate(commands, 1):
            print(f"\n  Step {i}: {cmd['explanation']}")
            print(f"  Command: {cmd['cmd']}")
        print()
        
        approved, needs_confirmation, blocked = check_shell_plan(plan)
        
        if blocked:
            print("\n[SHELL PLAN] Plan contains blocked commands.")
            print("The following commands cannot be executed:")
            for b in blocked:
                print(f"  ✗ {b['cmd']}: {b['risk_reason']}")
            print("\nRemaining safe commands can still run.")
            print("Proceed with only the approved/confirmed commands? (y/n):")
            
            from cli.main import pause_spinner, resume_spinner
            pause_spinner()
            sys.stdout.flush()
            choice = input().strip().lower()
            resume_spinner()
            
            if choice != "y": 
                print("[SHELL PLAN] Cancelled.")
                return False
            commands_to_run = approved.copy()
        else:
            commands_to_run = approved.copy()
            
        for cmd in needs_confirmation:
            print(f"\n[CONFIRM] {cmd['cmd']}")
            print(f"  What it does: {cmd['explanation']}")
            print(f"  Risk: {cmd['risk_reason']}")
            print("  Run this command? (y/n):")
            
            from cli.main import pause_spinner, resume_spinner
            pause_spinner()
            sys.stdout.flush()
            c = input().strip().lower()
            resume_spinner()
            
            if c == "y":
                commands_to_run.append(cmd)
            else:
                print(f"  Skipped: {cmd['cmd']}")
                
        if not commands_to_run:
            print("[SHELL PLAN] No commands to run. Cancelled.")
            return False
            
        print(f"\n[SHELL PLAN] Ready to run {len(commands_to_run)} command(s). Final approval (y/n):")
        
        from cli.main import pause_spinner, resume_spinner
        pause_spinner()
        sys.stdout.flush()
        final = input().strip().lower()
        resume_spinner()
        
        if final != "y":
            print("[SHELL PLAN] Cancelled.")
            return False
    else:
        # For replays, run all commands directly
        commands_to_run = commands
        print(f"\n▶  {intent_description}")
        
    cm = CheckpointManager()
    affected_paths = []
    for cmd in commands_to_run:
        paths = re.findall(r'[~\\/][\w\/\.\-]+', cmd["cmd"])
        affected_paths.extend(paths)
    cm.capture(affected_paths, command_text=f"SHELL_PLAN: {intent_description}")
    
    print(f"\n  Running your request...\n")
    all_succeeded = True
    for cmd in commands_to_run:
        if dry_run:
            print(f"  [DRY-RUN] {cmd['cmd']}")
            continue
        try:
            result = subprocess.run(
                cmd["cmd"], shell=True, capture_output=True,
                text=True, timeout=30,
                cwd=os.path.expanduser("~")
            )
            if result.stdout.strip():
                print(f"\n{'─'*50}")
                print(result.stdout.strip())
                print(f"{'─'*50}\n")
            if result.returncode != 0 and result.stderr.strip():
                print(f"  ⚠  Note: {result.stderr.strip()[:200]}")
                all_succeeded = False
        except subprocess.TimeoutExpired:
            print(f"  ✗  Timed out after 30 seconds")
            all_succeeded = False
        except Exception as e:
            print(f"  ✗  {e}")
            all_succeeded = False
            
    if not is_replay and all_succeeded and plan.get("saveable", True) and not dry_run:
        print(f"\n  💾  Want to save this as a quick command?")
        print(f"  Type a name (e.g. 'check disk space') "
              f"or press Enter to skip: ", end='', flush=True)
              
        from cli.main import pause_spinner, resume_spinner
        pause_spinner()
        sys.stdout.flush()
        trigger = input().strip()
        resume_spinner()
        
        if trigger:
            _save_user_command(trigger, ctr, intent_description)
            
    return all_succeeded

def _save_user_command(trigger_phrase: str, ctr, intent_description: str) -> None:
    """Saves a SHELL_PLAN CTR as a named user command and generates paraphrases for the sentence transformer."""
    db = SQLiteManager()
    
    try:
        db.insert("user_commands", {
            "command_name": trigger_phrase.lower().strip(),
            "ctr_json": ctr.to_json(),
            "created_at": datetime.utcnow().isoformat()
        })
    except Exception as e:
        print(f"[SAVE] Error saving command: {e}")
        return
        
    print(f"[SAVE] Generating recognition phrases for '{trigger_phrase}'...")
    
    paraphrases = generate_paraphrases(trigger_phrase)
    
    for phrase in paraphrases:
        try:
            db.insert("command_paraphrases", {
                "command_name": trigger_phrase.lower().strip(),
                "phrase": phrase,
                "created_at": datetime.utcnow().isoformat()
            })
        except Exception:
            pass
            
    print(f"[SAVE] ✓ Command '{trigger_phrase}' saved with {len(paraphrases)} recognition phrases.")
    print(f"  You can now say: {paraphrases[:3]}")
