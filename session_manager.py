"""
session_manager.py

High-level session persistence layer for the AI Cognitive OS project.
Uses SQLiteManager (db_manager.py) for storage and CTR (core/ctr.py)
for serialization.  Only stdlib dependencies (json, datetime) beyond
the project's own modules.
"""

import json
import sys
import os
from datetime import datetime
from typing import Optional, Tuple, Union

# Allow imports from project root and core/ sub-package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_manager import SQLiteManager
from core.ctr import CTR


# ---------------------------------------------------------------------------
# save_ctr
# ---------------------------------------------------------------------------

def save_ctr(ctr: CTR, status: str, summary: str) -> None:
    """Persist a CTR object to the session_memory table.

    Args:
        ctr:     The CTR dataclass instance to save.
        status:  Execution status — must be 'complete', 'interrupted', or 'failed'.
        summary: Human-readable natural language description of what was done.
    """
    db = SQLiteManager()
    db.insert("session_memory", {
        "ctr_json":                ctr.to_json(),
        "timestamp":               datetime.utcnow().isoformat(),
        "execution_status":        status,
        "natural_language_summary": summary,
    })
    db.close()


# ---------------------------------------------------------------------------
# get_last_incomplete
# ---------------------------------------------------------------------------

def get_last_incomplete() -> Optional[CTR]:
    """Return the most recently interrupted CTR, or None if none exist.

    Fetches all rows from session_memory with execution_status='interrupted',
    sorts them by timestamp descending, and returns the CTR reconstructed
    from the latest row's ctr_json field.
    """
    db = SQLiteManager()
    rows = db.fetch_where("session_memory", "execution_status", "interrupted")
    db.close()

    if not rows:
        return None

    # Sort by timestamp descending (ISO 8601 strings sort lexicographically)
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    latest = rows[0]
    return CTR.from_json(latest["ctr_json"])


# ---------------------------------------------------------------------------
# get_recent_summary
# ---------------------------------------------------------------------------

def get_recent_summary(hours: int = 24) -> str:
    """Return a formatted string summarising session activity in the last N hours.

    Groups rows by executor_type (mapped from ctr_json's task_type field) and
    lists the count per type followed by each row's natural_language_summary.

    Args:
        hours: Look-back window in hours (default 24).

    Returns:
        A human-readable multi-line summary string.
    """
    db = SQLiteManager()
    rows = db.fetch_recent("session_memory", hours=hours)
    db.close()

    if not rows:
        return f"No sessions found in the last {hours} hour(s)."

    # Count runs per executor type (task_type in CTR maps to executor_type)
    type_counts: dict[str, int] = {}
    summaries: list[str] = []

    for row in rows:
        try:
            data = json.loads(row["ctr_json"])
            executor_type = data.get("task_type", "UNKNOWN")
        except (json.JSONDecodeError, KeyError):
            executor_type = "UNKNOWN"

        type_counts[executor_type] = type_counts.get(executor_type, 0) + 1
        summaries.append(row["natural_language_summary"])

    lines = [f"=== Session summary — last {hours} hour(s) ==="]
    lines.append("\nExecutor activity:")
    for etype, count in sorted(type_counts.items()):
        lines.append(f"  {etype}: {count} run(s)")

    lines.append("\nActivity log:")
    for s in summaries:
        lines.append(f"  - {s}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# get_last_n_tasks
# ---------------------------------------------------------------------------

def get_last_n_tasks(n: int = 10) -> str:
    """Return a formatted numbered report of the last N tasks from session_memory.

    Each entry shows: index, task type, local timestamp, and the
    natural-language summary.

    Args:
        n: Maximum number of tasks to return (default 10).

    Returns:
        A human-readable multi-line string.
    """
    db = SQLiteManager()
    # fetch all and sort descending — fetch_recent requires hours, so use all rows
    try:
        rows = db.fetch_all("session_memory")
    except Exception:
        rows = []
    db.close()

    if not rows:
        return "  No tasks recorded yet."

    # Sort by timestamp descending, take top N
    rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    rows = rows[:n]

    lines = [f"\n  📋  Last {len(rows)} task(s):\n"]
    for i, row in enumerate(rows, 1):
        try:
            data = json.loads(row.get("ctr_json", "{}"))
            task_type = data.get("task_type", "UNKNOWN")
        except Exception:
            task_type = "UNKNOWN"

        ts_raw = row.get("timestamp", "")
        try:
            from datetime import timezone, timedelta
            dt_utc = datetime.fromisoformat(ts_raw)
            # Convert UTC → IST (UTC+5:30)
            ist = dt_utc + timedelta(hours=5, minutes=30)
            ts_label = ist.strftime("%a %d %b · %I:%M %p")
        except Exception:
            ts_label = ts_raw[:16]

        status = row.get("execution_status", "?")
        icon = {"complete": "✓", "interrupted": "⟳", "failed": "✗"}.get(status, "·")
        summary = row.get("natural_language_summary", "—")
        task_label = task_type.replace("_", " ").title()

        lines.append(f"  {i:2d}.  {icon}  {task_label}")
        lines.append(f"       {ts_label}")
        lines.append(f"       {summary}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# handle_resume_command
# ---------------------------------------------------------------------------

def handle_resume_command(
    user_input: str,
) -> Union[str, Tuple[str, CTR]]:
    """Route a natural-language command to the appropriate session function.

    Recognised patterns
    -------------------
    - 'continue' / 'resume' / 'what was i doing'
          → looks up the last interrupted CTR.
          → Returns tuple (message: str, ctr: CTR) if found, else plain str.
    - 'yesterday' / 'what did i do'
          → returns get_recent_summary(24).

    Args:
        user_input: Raw user text (case-insensitive matching).

    Returns:
        Either a plain str message or a (str, CTR) tuple.
    """
    lowered = user_input.lower()

    if any(kw in lowered for kw in ("continue", "resume", "what was i doing")):
        ctr = get_last_incomplete()
        if ctr is None:
            return "No interrupted tasks found."

        # Retrieve the natural_language_summary from the matching DB row
        db = SQLiteManager()
        rows = db.fetch_where("session_memory", "execution_status", "interrupted")
        db.close()

        rows.sort(key=lambda r: r["timestamp"], reverse=True)
        nl_summary = rows[0]["natural_language_summary"] if rows else str(ctr)

        message = f"Resuming: {nl_summary}"
        return (message, ctr)

    if any(kw in lowered for kw in ("yesterday", "what did i do")):
        return get_recent_summary(24)

    return "Command not recognised. Try 'resume', 'what was I doing', or 'what did I do'."


# ---------------------------------------------------------------------------
# run_demo  (required by project rules)
# ---------------------------------------------------------------------------

def run_demo() -> None:
    """Demonstrate session_manager with a dummy CTR.

    Uses a temporary in-memory SQLiteManager so nothing is written to disk.
    We monkey-patch SQLiteManager to inject the in-memory instance for the demo.
    """
    import session_manager as _sm

    _original_cls = _sm.SQLiteManager

    # Shared in-memory DB instance so all calls within the demo share state
    _shared_db = SQLiteManager(db_path=":memory:")

    class _InMemoryProxy:
        """Thin proxy that returns the shared in-memory SQLiteManager."""
        def __init__(self, db_path=None):
            pass

        def __getattr__(self, name):
            return getattr(_shared_db, name)

        def close(self):
            pass  # keep the shared DB alive for the whole demo

    # Patch
    _sm.SQLiteManager = _InMemoryProxy

    try:
        print("=== session_manager Demo ===\n")

        # 1. Create a dummy CTR and save it as 'interrupted'
        dummy_ctr = CTR(
            task_type="ORGANIZE_DOWNLOADS",
            params={"source_dir": "~/Downloads"},
        )
        save_ctr(
            dummy_ctr,
            status="interrupted",
            summary="Organized 5 files before power cut.",
        )
        print(f"Saved interrupted CTR: {dummy_ctr.task_type}")

        # 2. Add a completed one too, for the summary report
        save_ctr(
            CTR(task_type="BULK_RENAME", params={"source_dir": "~/Docs"}),
            status="complete",
            summary="Renamed 20 documents with date-slug pattern.",
        )
        print("Saved completed CTR: BULK_RENAME\n")

        # 3. Simulate a new session — resume check
        result = handle_resume_command("what was i doing")
        if isinstance(result, tuple):
            message, recovered_ctr = result
            print(f"handle_resume_command → message : {message}")
            print(f"handle_resume_command → CTR    : {recovered_ctr}\n")
        else:
            print(f"handle_resume_command → {result}\n")

        # 4. Session summary
        print("get_recent_summary(hours=24):")
        print(get_recent_summary(24))

    finally:
        # Restore
        _sm.SQLiteManager = _original_cls
        _shared_db.close()
        print("\n=== Demo complete ===")


# ---------------------------------------------------------------------------
# Tests  (required by project rules: 3 test cases)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Three tests for session_manager using an in-memory DB."""

    import session_manager as _sm

    _original_cls = _sm.SQLiteManager

    def _make_proxy():
        db = SQLiteManager(db_path=":memory:")

        class Proxy:
            def __init__(self, db_path=None):
                pass
            def __getattr__(self, name):
                return getattr(db, name)
            def close(self):
                pass

        return db, Proxy

    print("\n=== Running Tests ===\n")

    # Test 1: save_ctr writes to session_memory, get_last_incomplete recovers it
    print("Test 1: save_ctr + get_last_incomplete")
    _shared, _Proxy = _make_proxy()
    _sm.SQLiteManager = _Proxy
    try:
        ctr_in = CTR(task_type="ORGANIZE_DOWNLOADS", params={"source_dir": "/tmp"})
        save_ctr(ctr_in, "interrupted", "Halfway through organizing.")
        recovered = get_last_incomplete()
        assert recovered is not None, "Expected a CTR, got None"
        assert recovered.task_type == "ORGANIZE_DOWNLOADS"
        assert recovered.params == {"source_dir": "/tmp"}
    finally:
        _sm.SQLiteManager = _original_cls
        _shared.close()
    print("  PASSED\n")

    # Test 2: get_last_incomplete returns None when no interrupted sessions exist
    print("Test 2: get_last_incomplete with no interrupted rows → None")
    _shared, _Proxy = _make_proxy()
    _sm.SQLiteManager = _Proxy
    try:
        save_ctr(CTR(task_type="BULK_RENAME", params={}), "complete", "Done.")
        result = get_last_incomplete()
        assert result is None, f"Expected None, got {result}"
    finally:
        _sm.SQLiteManager = _original_cls
        _shared.close()
    print("  PASSED\n")

    # Test 3: handle_resume_command with no interrupted tasks returns expected string
    print("Test 3: handle_resume_command → 'No interrupted tasks found.'")
    _shared, _Proxy = _make_proxy()
    _sm.SQLiteManager = _Proxy
    try:
        msg = handle_resume_command("what was i doing")
        assert msg == "No interrupted tasks found.", f"Unexpected: {msg}"
    finally:
        _sm.SQLiteManager = _original_cls
        _shared.close()
    print("  PASSED\n")

    print("=== All Tests Passed ===")


if __name__ == "__main__":
    run_demo()
    _run_tests()
