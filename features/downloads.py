import os
from core.ctr import CTR, validate_ctr
from core.planner import plan
from core.policy import check_policy
from core.executor import execute
from core.steps import Step


def organize_downloads(source_dir: str, dry_run: bool = True) -> None:
    """Full downloads organizer workflow."""
    
    # Step 1: Build CTR
    ctr = CTR(
        task_type="ORGANIZE_DOWNLOADS",
        params={"source_dir": source_dir}
    )
    
    print(f"[WORKFLOW] CTR: {ctr}")
    
    # Step 2: Validate CTR
    validate_ctr(ctr)
    
    # Step 3: Plan
    steps = plan(ctr)
    
    # Step 4: Extract affected paths
    affected_paths = []
    for step in steps:
        if "path" in step.args:
            affected_paths.append(step.args["path"])
        elif "src" in step.args:
            affected_paths.append(step.args["src"])
        elif "dst" in step.args:
            affected_paths.append(step.args["dst"])
    
    # Step 5: Policy check
    check_policy(ctr, affected_paths)
    
    # Step 6: Execute
    execute(steps, dry_run=dry_run)
