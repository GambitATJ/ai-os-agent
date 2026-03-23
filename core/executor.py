import os
from typing import List
from .steps import Step


def execute(steps: List[Step], dry_run: bool = True) -> None:
    from checkpoint_manager import CheckpointManager
    cm = CheckpointManager()
    affected = []
    for step in steps:
        if "path" in step.args: affected.append(step.args["path"])
        if "src" in step.args: affected.append(step.args["src"])
        if "dst" in step.args: affected.append(step.args["dst"])
    cm.capture(affected, command_text="Execute file operations from plan")

    print(f"[EXECUTOR] Starting {'DRY-RUN' if dry_run else 'REAL'} execution ({len(steps)} steps)")
    
    for i, step in enumerate(steps, 1):
        print(f"Step {i}/{len(steps)}: {step.step_type} {step.args}")
        
        if step.step_type == "CREATE_DIR":
            path = os.path.expanduser(step.args["path"])
            if dry_run:
                print(f"  [DRY-RUN] Would create: {path}")
            else:
                os.makedirs(path, exist_ok=True)
                print(f"  ✅ Created: {path}")
        
        elif step.step_type == "MOVE_FILE":
            src = os.path.expanduser(step.args["src"])
            dst = os.path.expanduser(step.args["dst"])
            if dry_run:
                print(f"  [DRY-RUN] Would move: {src} → {dst}")
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
                print(f"  ✅ Moved: {src} → {dst}")
        
        else:
            print(f"  [SKIP] Unknown step_type: {step.step_type}")
    
    print("[EXECUTOR] Done.")
