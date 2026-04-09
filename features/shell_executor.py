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


def _pause():
    """Pause the spinner and clear the current line before prompting user."""
    try:
        from cli.main import pause_spinner
        pause_spinner()
    except ImportError:
        pass


def _resume():
    """Resume the spinner after user input is collected."""
    try:
        from cli.main import resume_spinner
        resume_spinner()
    except ImportError:
        pass


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
    is_from_llm = ctr.params.get("_from_llm", False)

    if not is_replay:
        print(f"\n{'─'*50}")
        print(f"  🤖  {intent_description}")
        print(f"{'─'*50}")
        for i, cmd in enumerate(commands, 1):
            print(f"\n  Step {i}: {cmd['explanation']}")
            print(f"  Command: {cmd['cmd']}")
        print()

        approved, needs_confirmation, blocked = check_shell_plan(plan)

        override_password = ""
        # Handle blocked commands with override option
        if blocked:
            from core.policy import attempt_override
            _pause()
            overridden, override_password = attempt_override(blocked)
            _resume()
            commands_to_run = approved.copy()
            commands_to_run.extend(overridden)
        else:
            commands_to_run = approved.copy()

        for cmd in needs_confirmation:
            print(f"\n[CONFIRM] {cmd['cmd']}")
            print(f"  What it does: {cmd['explanation']}")
            print(f"  Risk: {cmd['risk_reason']}")
            _pause()
            print("  Run this command? (y/n): ", end='', flush=True)
            c = input().strip().lower()
            _resume()

            if c == "y":
                commands_to_run.append(cmd)
            else:
                print(f"  Skipped: {cmd['cmd']}")

        if not commands_to_run:
            print("[SHELL PLAN] No commands to run. Cancelled.")
            return False

        _pause()
        print(f"\n[SHELL PLAN] Ready to run {len(commands_to_run)} command(s). Final approval (y/n): ", end='', flush=True)
        final = input().strip().lower()
        _resume()

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
            timeout_seconds = 180 if any(pkg_mgr in cmd["cmd"] for pkg_mgr in ["apt", "apt-get", "pip", "npm", "snap", "dpkg"]) else 60

            env = os.environ.copy()
            if "apt" in cmd["cmd"]:
                env["DEBIAN_FRONTEND"] = "noninteractive"

            # If the user overrode a blocked command, pass the password if it's sudo
            is_overridden_sudo = "sudo" in cmd["cmd"] and (not is_replay and override_password)

            if is_overridden_sudo:
                env["SUDO_ASKPASS"] = "/bin/false"
                result = subprocess.run(
                    cmd["cmd"], shell=True, capture_output=True,
                    text=True, timeout=timeout_seconds,
                    input=override_password + "\n",
                    cwd=os.path.expanduser("~"),
                    env=env
                )
            else:
                result = subprocess.run(
                    cmd["cmd"], shell=True, capture_output=True,
                    text=True, timeout=timeout_seconds,
                    cwd=os.path.expanduser("~"),
                    env=env
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

    # Only offer save-as-named-command for LLM-generated plans, not predefined tasks
    if not is_replay and is_from_llm and all_succeeded and plan.get("saveable", True) and not dry_run:
        _pause()
        print(f"\n  💾  Want to save this as a quick command?")
        print(f"  Type a name (e.g. 'check disk space') or press Enter to skip: ", end='', flush=True)
        trigger = input().strip()
        _resume()

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
