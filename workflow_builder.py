"""
workflow_builder.py

Orchestrates parsing, validation, and persistence of user-defined workflows.
Combines WorkflowParser, WorkflowValidator, SQLiteManager, and CTR into a
single registration pipeline.

Only stdlib dependencies (json, datetime, sqlite3) beyond project modules.
"""

import json
import sqlite3
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow_parser    import WorkflowParser
from workflow_validator import WorkflowValidator
from db_manager         import SQLiteManager
from core.ctr           import CTR


# ---------------------------------------------------------------------------
# register_workflow
# ---------------------------------------------------------------------------

def register_workflow(trigger_phrase: str, description: str) -> str:
    """Parse, validate, and persist a user-defined workflow.

    Args:
        trigger_phrase: The short spoken/typed phrase that will invoke the workflow.
        description:    Natural-language description of what the workflow does.

    Returns:
        "registered"             — success.
        "Registration cancelled." — user declined to overwrite.
        A reason string          — if feasibility or policy checks fail.
    """

    # ------------------------------------------------------------------
    # Step 1 — Parse
    # ------------------------------------------------------------------
    print("Parsing workflow description...")
    parser = WorkflowParser()
    steps  = parser.parse(description)

    # ------------------------------------------------------------------
    # Step 2 — Feasibility check
    # ------------------------------------------------------------------
    print("Running feasibility check...")
    validator = WorkflowValidator()
    ok, reason = validator.check_feasibility(steps)
    if not ok:
        print(f"Feasibility failed: {reason}")
        return reason

    # ------------------------------------------------------------------
    # Step 3 — Policy check
    # ------------------------------------------------------------------
    print("Running policy check...")
    ok, reason = validator.check_policy(steps)
    if not ok:
        print(f"Policy violation: {reason}")
        return reason

    # ------------------------------------------------------------------
    # Step 4 — Build CTR
    # ------------------------------------------------------------------
    # task_type is set to 'user_defined_workflow'; params carry the trigger
    # and the serialised step list so the whole workflow is self-contained.
    ctr = CTR(
        task_type="user_defined_workflow",
        params={
            "trigger":    trigger_phrase,
            "steps_json": json.dumps(steps),
        },
    )
    ctr_json = ctr.to_json()

    # ------------------------------------------------------------------
    # Step 5 — Persist to user_commands
    # ------------------------------------------------------------------
    db = SQLiteManager()
    command_name = trigger_phrase.lower().strip()

    try:
        db.insert("user_commands", {
            "command_name": command_name,
            "ctr_json":     ctr_json,
            "created_at":   datetime.utcnow().isoformat(),
        })

    except sqlite3.IntegrityError:
        # UNIQUE constraint — a workflow with this trigger already exists.
        print(
            f"A workflow named '{trigger_phrase}' already exists. "
            "Overwrite? (y/n)"
        )
        answer = input().strip().lower()

        if answer == "y":
            # Find and delete the existing row, then re-insert.
            existing = db.fetch_where("user_commands", "command_name", command_name)
            if existing:
                db.delete("user_commands", existing[0]["id"])
            db.insert("user_commands", {
                "command_name": command_name,
                "ctr_json":     ctr_json,
                "created_at":   datetime.utcnow().isoformat(),
            })
        else:
            db.close()
            return "Registration cancelled."

    db.close()

    # ------------------------------------------------------------------
    # Step 6 — Confirm
    # ------------------------------------------------------------------
    print(
        f"Workflow '{trigger_phrase}' registered successfully. "
        f"Say '{trigger_phrase}' to run it anytime."
    )
    return "registered"


# ---------------------------------------------------------------------------
# run_demo  (required by project rules)
# ---------------------------------------------------------------------------

def run_demo() -> None:
    """Demonstrate register_workflow with an in-memory SQLiteManager.

    Uses monkey-patching so no files are written to disk during the demo.
    Simulates 'y' for the overwrite prompt via sys.stdin replacement.
    """
    import io
    import workflow_builder as _wb

    _original_cls = _wb.SQLiteManager

    # Shared in-memory database for the entire demo
    _shared_db = SQLiteManager(db_path=":memory:")

    class _InMemoryProxy:
        def __init__(self, db_path=None):
            pass
        def __getattr__(self, name):
            return getattr(_shared_db, name)
        def close(self):
            pass  # keep shared DB alive

    _wb.SQLiteManager = _InMemoryProxy

    # Also stub out WorkflowParser to avoid loading sentence-transformers
    _original_parser = _wb.WorkflowParser

    class _StubParser:
        def parse(self, description):
            return [
                {
                    "executor_type": "FIND_RECEIPTS",
                    "parameters":    {"source_dir": "~/reports"},
                },
            ]

    _wb.WorkflowParser = _StubParser

    try:
        print("=" * 55)
        print("  WorkflowBuilder Demo — First Registration")
        print("=" * 55)
        result = register_workflow(
            trigger_phrase="friday report",
            description="take the newest file in ~/reports and copy it to ~/sent",
        )
        print(f"→ return value: {result!r}\n")

        print("=" * 55)
        print("  WorkflowBuilder Demo — Duplicate (overwrite with 'y')")
        print("=" * 55)
        # Simulate the user typing 'y' at the overwrite prompt
        _original_stdin = sys.stdin
        sys.stdin = io.StringIO("y\n")
        try:
            result2 = register_workflow(
                trigger_phrase="friday report",
                description="take the newest file in ~/reports and copy it to ~/sent",
            )
        finally:
            sys.stdin = _original_stdin
        print(f"→ return value: {result2!r}\n")

        print("=== Demo complete ===")

    finally:
        _wb.SQLiteManager  = _original_cls
        _wb.WorkflowParser = _original_parser
        _shared_db.close()


# ---------------------------------------------------------------------------
# Tests  (required by project rules: 3 test cases)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Three fast tests that stub parser and SQLiteManager."""
    import io
    import workflow_builder as _wb

    _original_cls    = _wb.SQLiteManager
    _original_parser = _wb.WorkflowParser

    # --- shared helpers ---

    def _make_proxy():
        db = SQLiteManager(db_path=":memory:")
        class Proxy:
            def __init__(self, db_path=None): pass
            def __getattr__(self, name): return getattr(db, name)
            def close(self): pass
        return db, Proxy

    class _StubParser:
        def parse(self, description):
            return [{"executor_type": "ORGANIZE_DOWNLOADS", "parameters": {}}]

    print("\n=== Running Tests ===\n")

    # Test 1: happy path returns "registered"
    print("Test 1: successful registration returns 'registered'")
    db1, Proxy1 = _make_proxy()
    _wb.SQLiteManager  = Proxy1
    _wb.WorkflowParser = _StubParser
    try:
        result = register_workflow("test trigger", "organize downloads")
        assert result == "registered", f"Expected 'registered', got {result!r}"
    finally:
        _wb.SQLiteManager  = _original_cls
        _wb.WorkflowParser = _original_parser
        db1.close()
    print("  PASSED\n")

    # Test 2: duplicate + 'n' returns "Registration cancelled."
    print("Test 2: duplicate + 'n' → 'Registration cancelled.'")
    db2, Proxy2 = _make_proxy()
    _wb.SQLiteManager  = Proxy2
    _wb.WorkflowParser = _StubParser
    original_stdin = sys.stdin
    try:
        # First insert
        register_workflow("dup trigger", "organize downloads")
        # Second insert — should hit UNIQUE and prompt
        sys.stdin = io.StringIO("n\n")
        result2 = register_workflow("dup trigger", "organize downloads")
        assert result2 == "Registration cancelled.", f"Unexpected: {result2!r}"
    finally:
        sys.stdin = original_stdin
        _wb.SQLiteManager  = _original_cls
        _wb.WorkflowParser = _original_parser
        db2.close()
    print("  PASSED\n")

    # Test 3: duplicate + 'y' overwrites and returns "registered"
    print("Test 3: duplicate + 'y' → overwrite → 'registered'")
    db3, Proxy3 = _make_proxy()
    _wb.SQLiteManager  = Proxy3
    _wb.WorkflowParser = _StubParser
    original_stdin = sys.stdin
    try:
        register_workflow("ow trigger", "organize downloads")
        sys.stdin = io.StringIO("y\n")
        result3 = register_workflow("ow trigger", "organize downloads")
        assert result3 == "registered", f"Unexpected: {result3!r}"
        # Confirm only one row exists after overwrite
        rows = db3.fetch_where("user_commands", "command_name", "ow trigger")
        assert len(rows) == 1, f"Expected 1 row, found {len(rows)}"
    finally:
        sys.stdin = original_stdin
        _wb.SQLiteManager  = _original_cls
        _wb.WorkflowParser = _original_parser
        db3.close()
    print("  PASSED\n")

    print("=== All Tests Passed ===")


if __name__ == "__main__":
    _run_tests()
    print()
    run_demo()
