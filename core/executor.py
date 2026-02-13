import os
from typing import List
from .steps import Step


def execute(steps: List[Step], dry_run: bool = True) -> None:
    """Execute steps with optional dry-run."""
    print(f"[EXECUTOR] Starting {'DRY-RUN' if dry_run else 'REAL'} execution ({len(steps)} steps)")
    
    for i, step in enumerate(steps, 1):
        print(f"Step {i}/{len(steps)}: {step.step_type} {step.args}")
        
        if step.step_type == "CREATE_DIR":
            path = os.path.expanduser(step.args["path"])
            if dry_run:
                print(f"  [DRY-RUN] Would create: {path}")
            else:
                try:
                    os.makedirs(path, exist_ok=True)
                    print(f"  ✅ Created: {path}")
                except Exception as e:
                    print(f"  ❌ Failed to create {path}: {e}")
        
        elif step.step_type == "MOVE_FILE":
            src = os.path.expanduser(step.args["src"])
            dst = os.path.expanduser(step.args["dst"])
            if dry_run:
                print(f"  [DRY-RUN] Would move: {src} → {dst}")
            else:
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.rename(src, dst)
                    print(f"  ✅ Moved: {src} → {dst}")
                except Exception as e:
                    print(f"  ❌ Failed to move {src}: {e}")
        
        else:
            print(f"  [SKIP] Unknown step_type: {step.step_type}")
    
    print("[EXECUTOR] Done.")
