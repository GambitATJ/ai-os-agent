import os
from typing import List
from .ctr import CTR


HOME_DIR = os.path.expanduser("~")


def _is_under_home(path: str) -> bool:
    """Check if path is safely under HOME directory."""
    abs_path = os.path.realpath(os.path.expanduser(path))
    return abs_path.startswith(HOME_DIR)


def check_policy(ctr: CTR, affected_paths: List[str]) -> None:
    """
    Policy checks:
    - All paths under HOME
    - Max 100 files affected
    - No system paths
    """
    
    # 1. Path constraints
    for path in affected_paths:
        if not _is_under_home(path):
            raise PermissionError(f"Path {path} is outside HOME ({HOME_DIR})")
    
    # 2. File count constraint
    if len(affected_paths) > 100:
        raise PermissionError("Too many files affected (>100)")
    
    # 3. Task-specific constraints (expand later)
    if ctr.task_type == "ORGANIZE_DOWNLOADS":
        # Downloads only for now
        pass
    # Add more task-specific rules here later
    
    print(f"[POLICY] ✅ Approved {ctr.task_type} (affected: {len(affected_paths)} paths)")
