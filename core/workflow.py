from typing import Any, List
from .ctr import CTR, validate_ctr
from .policy import check_policy
from .planner import plan
from .executor import execute
from .logger import log_ctr
from .steps import Step


def run_workflow(ctr: CTR, dry_run: bool = True) -> List[Step]:
    """Universal CTR → Policy → Plan → Execute pipeline."""
    
    # Log start
    log_ctr(ctr, "STARTED")
    
    # 1. Validate
    validate_ctr(ctr)
    
    # 2. Plan (if applicable)
    try:
        steps = plan(ctr)
        log_ctr(ctr, "PLANNED", {"step_count": len(steps)})
    except NotImplementedError:
        steps = []  # Pure code actions (password gen)
        log_ctr(ctr, "PLANNED", {"steps": "none (pure code action)"})
    
    # 3. Extract paths
    affected_paths = []
    for step in steps:
        if "path" in step.args:
            affected_paths.append(step.args["path"])
        elif "src" in step.args:
            affected_paths.append(step.args["src"])
        elif "dst" in step.args:
            affected_paths.append(step.args["dst"])
    
    # 4. Policy
    check_policy(ctr, affected_paths)
    log_ctr(ctr, "POLICY_APPROVED", {"affected_paths": len(affected_paths)})
    
    # 5. Execute
    execute(steps, dry_run)
    log_ctr(ctr, "COMPLETED", {"dry_run": dry_run, "steps_executed": len(steps)})
    
    return steps
