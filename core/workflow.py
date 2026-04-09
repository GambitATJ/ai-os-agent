from typing import List
import time
from .ctr import CTR, validate_ctr
from .policy import check_policy
from .planner import plan
from .executor import execute
from .logger import log_ctr
from .steps import Step
from cost_estimator import CostEstimator
from features.shell_executor import execute_shell_plan
from core.session_context import update_context

def run_workflow(ctr: CTR, dry_run: bool = True) -> List[Step]:

    # Handle multi-task sequences first
    if ctr.task_type == "MULTI_TASK":
        import time as _time
        tasks = ctr.params.get("tasks", [])
        print(f"\n  \u26a1  Executing {len(tasks)}-step sequence\n")
        sep = "\u2500" * 40
        for i, task_dict in enumerate(tasks, 1):
            print(f"  {sep}")
            print(f"  Step {i} of {len(tasks)}: "
                  f"{task_dict['task_type']}\n")
            sub_ctr = CTR(
                task_type=task_dict["task_type"],
                params=task_dict["params"],
                version=task_dict.get("version", "1.0")
            )
            run_workflow(sub_ctr, dry_run=dry_run)
            _time.sleep(0.5)
        print(f"\n  \u2713  Sequence complete.\n")
        return []

    if ctr.task_type == "SHELL_PLAN":
        log_ctr(ctr, "STARTED")
        success = execute_shell_plan(ctr, dry_run=dry_run)
        if success:
            log_ctr(ctr, "COMPLETED", {"shell_plan": True})
            update_context(
                task_type="SHELL_PLAN",
                description=ctr.params.get(
                    "intent_description", "shell plan")
            )
            # Also save to session_memory
            from session_manager import save_ctr
            save_ctr(ctr, "complete",
                     ctr.params.get("intent_description",
                     "shell plan execution"))
        else:
            log_ctr(ctr, "INTERRUPTED", {"shell_plan": True,
                                          "cancelled": True})
        return []

    if ctr.task_type == "SAVED_COMMAND":
        # Retrieve and re-run the stored CTR
        stored_json = ctr.params.get("original_ctr_json")
        if stored_json:
            from core.ctr import CTR as CTRClass
            original = CTRClass.from_json(stored_json)
            print(f"[WORKFLOW] Executing saved command: {original.task_type}")
            return run_workflow(original, dry_run=dry_run)
        else:
            print("[WORKFLOW] Error: saved command has no stored CTR.")
            return []

    log_ctr(ctr, "STARTED")

    validate_ctr(ctr)

    try:
        steps = plan(ctr)
        log_ctr(ctr, "PLANNED", {"step_count": len(steps)})
    except NotImplementedError:
        steps = []
        log_ctr(ctr, "PLANNED", {"steps": "none (pure action)"})

    if steps:
        affected_paths = []

        for step in steps:
            if "path" in step.args:
                affected_paths.append(step.args["path"])
            elif "src" in step.args:
                affected_paths.append(step.args["src"])
            elif "dst" in step.args:
                affected_paths.append(step.args["dst"])

        check_policy(ctr, affected_paths)
        log_ctr(ctr, "POLICY_APPROVED", {"affected_paths": len(affected_paths)})

        # --- Cost estimation intercept (only when not dry-run) ---
        target_directory = ctr.params.get("source_dir") or ctr.params.get("location") or ctr.params.get("export_dir")
        cost_info = None
        ce = None
        if target_directory and not dry_run:
            ce = CostEstimator()
            cost_info = ce.estimate(target_directory, len(steps))
            # Just print the estimate and proceed (no blocking prompt).
            # The UI layer handles visibility; the DB logs performance.
            print(ce.display_estimate(cost_info))

        start_time = time.time()
        execute(steps, dry_run)
        if ce and cost_info:
            ce.log_actual(feature_name=ctr.task_type, estimate=cost_info,
                          actual_seconds=time.time() - start_time)

    else:
        check_policy(ctr, [])
        log_ctr(ctr, "POLICY_APPROVED", {"affected_paths": 0})

        _execute_pure_action(ctr, dry_run)

    log_ctr(ctr, "COMPLETED", {"dry_run": dry_run})

    return steps


def _execute_pure_action(ctr: CTR, dry_run: bool):

    t = ctr.task_type
    p = ctr.params

    # Import INSIDE function to avoid circular imports
    if t == "FIND_RECEIPTS":
        from features.receipts import find_receipts_action
        find_receipts_action(
            p["source_dir"],
            p.get("query"),
            p.get("export_dir"),
            dry_run
        )

    elif t == "GENERATE_PASSWORD":
        from features.vault import generate_password_action
        generate_password_action(
            p["label"],
            p.get("length", 16),
            p.get("uppercase", True),
            p.get("lowercase", True),
            p.get("digits", True),
            p.get("symbols", True),
            dry_run
        )

    elif t == "SCAN_PASSWORD_FIELDS":
        from features.vault import scan_password_fields
        scan_password_fields(
            p.get("scope", "."),
            dry_run
        )

    elif t == "CREATE_PROJECT_SCAFFOLD":
        from features.projects import create_project
        create_project(
            p["name"],
            p.get("location", "~/Projects"),
            p.get("project_type", "python_project"),
            dry_run
        )

    elif t == "ORGANIZE_DOWNLOADS":
        from features.downloads import organize_downloads
        organize_downloads(
            p.get("source_dir", "~/Downloads"),
            dry_run
        )
        update_context(
            task_type="ORGANIZE_DOWNLOADS",
            description="Organised downloads folder"
        )

    elif t == "AUTOFILL_APP":
        from features.vault import vault
        vault.autofill_app(
            p["app_name"],
            dry_run
        )

    elif t == "BULK_RENAME":
        from features.rename import bulk_rename_action
        bulk_rename_action(
            p["source_dir"],
            p.get("pattern", "date_slug"),
            dry_run
        )

    elif t == "SEMANTIC_ORGANIZE":
        import os
        from semantic_organizer import run_organizer_flow

        source = p.get("source_dir", "~/Downloads")
        source = os.path.expanduser(source)

        if not os.path.isdir(source):
            print(f"  ✗  Directory not found: {source}")
            return

        print(f"\n  🧠  Analysing files in {source}...")
        print(f"  This may take a moment while embeddings")
        print(f"  are computed for each file.\n")
        run_organizer_flow(source)

    elif t == "CALENDAR_TASK":
        from features.calendar_manager import (
            create_event, list_upcoming_events, delete_event)
        from db_manager import SQLiteManager

        action = p.get("action", "list")

        if action == "create":
            attendee_email = None
            attendee_name = p.get("attendee_name")
            if attendee_name:
                db = SQLiteManager()
                attendee_email = db.get_contact(attendee_name)

            create_event(
                title=p.get("title", "Meeting"),
                date_str=p.get("date_str", "tomorrow"),
                time_str=p.get("time_str", "09:00"),
                attendee_email=attendee_email
            )

        elif action == "delete":
            delete_event(
                title_keyword=p.get("title"),
                date_str=p.get("date_str")
            )

        else:  # list
            list_upcoming_events(
                days_ahead=p.get("days_ahead", 1))

    elif t == "EMAIL_TASK":
        from features.email_sender import send_email
        
        attachment = p.get("attachment_path")
        
        # If no explicit attachment but search is needed,
        # find the file first
        if not attachment and p.get("needs_search"):
            search_query = p.get("search_query", "receipt")
            search_dir = p.get("search_dir", "~/Downloads")
            
            print(f"\n  🔍  Searching for '{search_query}' in {search_dir}...")
            
            try:
                from features.receipts import process_receipts
                results = process_receipts(
                    source_dir=search_dir,
                    query=search_query,
                    export_dir=None,
                    dry_run=dry_run
                )
                
                if results:
                    # Take the highest ranked result
                    attachment = results[0]["path"]
                    import os
                    filename = os.path.basename(attachment)
                    print(f"  📄  Found: {filename}")
                    print(f"  📎  Will attach this file.")
                else:
                    print(f"  ⚠  No matching files found for '{search_query}'.")
                    print(f"  Sending email without attachment.")
            except Exception as e:
                print(f"  ⚠  Search failed: {e}")
                print(f"  Sending email without attachment.")
                
        send_email(
            to_name=p.get("to_name", ""),
            subject=p.get("subject", "Document from AI-OS"),
            body=p.get("body", ""),
            attachment_path=attachment
        )

    else:
        raise ValueError(f"No execution handler for task: {t}")
