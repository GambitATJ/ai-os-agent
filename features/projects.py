import os
from core.ctr import CTR, validate_ctr
from core.planner import plan
from core.policy import check_policy
from core.executor import execute
from core.steps import Step


def create_project(name: str, location: str = "~/Projects", project_type: str = "python_project", dry_run: bool = True) -> None:
    """Full project scaffold workflow."""
    
    # Step 1: Build CTR
    ctr = CTR(
        task_type="CREATE_PROJECT_SCAFFOLD",
        params={
            "name": name,
            "location": location,
            "project_type": project_type
        }
    )
    
    print(f"[WORKFLOW] CTR: {ctr}")
    
    # Step 2: Validate CTR
    validate_ctr(ctr)
    
    # Step 3: Plan
    steps = plan(ctr)
    
    # Step 4: Extract affected paths
    affected_paths = [step.args["path"] for step in steps]
    
    # Step 5: Policy check
    check_policy(ctr, affected_paths)
    
    # Step 6: Execute
    execute(steps, dry_run=dry_run)
