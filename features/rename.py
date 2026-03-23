import re
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from core.ctr import CTR, validate_ctr
from core.policy import check_policy
from core.logger import log_ctr


class BulkRename:
    def __init__(self):
        pass
    
    def bulk_rename(self, source_dir: str, pattern: str, dry_run: bool = True) -> List[Dict]:
        """Bulk rename files using pattern."""
        from checkpoint_manager import CheckpointManager
        cm = CheckpointManager()
        affected = [str(p) for p in Path(source_dir).expanduser().resolve().glob("*")] + [source_dir]
        cm.capture(affected, command_text="Bulk rename files in a directory using a pattern")

        source_path = Path(source_dir).expanduser().resolve()
        if not source_path.exists():
            print(f"[RENAME] ❌ Directory not found: {source_dir}")
            return []
        
        files = list(source_path.glob("*"))
        renames = []
        
        for original_path in files:  # ← FIXED: rename original_path
            if original_path.is_file():
                new_name = self._generate_name(original_path, pattern)
                new_path = source_path / new_name  # ← FIXED: explicit source_path
                
                rename_info = {
                    "old": original_path.name,
                    "new": new_name,
                    "old_path": str(original_path),
                    "new_path": str(new_path)
                }
                renames.append(rename_info)
        
        if dry_run:
            print(f"[DRY-RUN] Would rename {len(renames)} files:")
            for r in renames[:5]:
                print(f"  {r['old']} → {r['new']}")
        else:
            print(f"[EXECUTOR] Renaming {len(renames)} files...")
            for r in renames:
                new_path = Path(r["new_path"])
                original_path = Path(r["old_path"])  # ← FIXED: explicit paths
                if new_path.exists():
                    print(f"  ⚠️  Skipping {r['old']} (target exists)")
                else:
                    original_path.rename(new_path)
                    print(f"  ✅ {r['old']} → {r['new']}")
        
        return renames

    
    def _generate_name(self, file_path: Path, pattern: str) -> str:
        """Generate new filename based on pattern."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        date_slug = datetime.now().strftime("%Y-%m-%d")
        counter = "001"
        
        base, ext = file_path.stem, file_path.suffix
        
        if pattern == "date_slug":
            return f"{date_slug}_{base}{ext}"
        elif pattern == "number":
            return f"{base}_{counter}{ext}"
        elif pattern == "timestamp":
            return f"{timestamp}_{base}{ext}"
        else:
            return f"{pattern}_{base}{ext}"


rename_engine = BulkRename()


def bulk_rename_action(source_dir: str, pattern: str = "date_slug", dry_run: bool = True):
    """CTR workflow for bulk rename."""
    ctr = CTR(
        task_type="BULK_RENAME",
        params={
            "source_dir": source_dir,
            "pattern": pattern
        }
    )
    
    print(f"[WORKFLOW] CTR: {ctr}")
    log_ctr(ctr, "STARTED")
    validate_ctr(ctr)
    log_ctr(ctr, "VALIDATED")
    
    affected_paths = [source_dir]
    check_policy(ctr, affected_paths)
    log_ctr(ctr, "POLICY_APPROVED")
    
    if dry_run:
        print("[EXECUTOR] DRY-RUN mode")
        log_ctr(ctr, "COMPLETED", {"dry_run": True})
        rename_engine.bulk_rename(source_dir, pattern, True)  # Show preview
    else:
        renames = rename_engine.bulk_rename(source_dir, pattern, False)
        log_ctr(ctr, "COMPLETED", {"renames": len(renames)})