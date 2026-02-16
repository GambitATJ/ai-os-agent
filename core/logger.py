import json
from datetime import datetime
from pathlib import Path
from core.ctr import CTR

LOG_PATH = Path.home() / ".aios" / "ctr.log"

def log_ctr(ctr: CTR, status: str, details: dict = None):
    """Log CTR lifecycle events to JSONL."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "task_type": ctr.task_type,
        "params": ctr.params,
        "status": status,
        "details": details or {}
    }
    
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    print(f"[AUDIT] {status} {ctr.task_type}")
