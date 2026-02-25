from typing import List
from .ctr import CTR, validate_ctr
from .policy import check_policy
from .planner import plan
from .executor import execute
from .logger import log_ctr
from .steps import Step


def run_workflow(ctr: CTR, dry_run: bool = True) -> List[Step]:

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

        execute(steps, dry_run)

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

    else:
        raise ValueError(f"No execution handler for task: {t}")
