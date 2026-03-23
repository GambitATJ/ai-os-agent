"""
workflow_validator.py

Pre-execution validation for multi-step workflows in the AI Cognitive OS project.
Two checks are provided:
  - check_feasibility: paths exist + executor type is registered
  - check_policy:      no forbidden terms or restricted paths

Only uses Python stdlib (os, typing).  The executor registry is derived from
the TaskType Literal defined in core/ctr.py — the single source of truth for
supported executor types in this codebase.
"""

import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Build the executor registry from the project's single source of truth.
# core/ctr.py defines TaskType as a Literal of all known executor types.
# We extract those values here without importing pydantic (which is optional).
# ---------------------------------------------------------------------------

def _build_registry() -> set[str]:
    """Return the set of known executor types from core/ctr.py's TaskType Literal."""
    # Attempt rich import first (works when pydantic is installed)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import typing, types

        # Read the source and exec only the TaskType definition to avoid pydantic
        src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "ctr.py")
        with open(src_path) as f:
            source = f.read()

        # Execute only lines up to (but not including) the @dataclass block
        pre_dataclass = source.split("@dataclass")[0]
        ns: dict[str, Any] = {}
        exec(pre_dataclass, ns)

        task_type = ns.get("TaskType")
        if task_type is not None:
            # typing.get_args works on Literal types in Python 3.8+
            args = typing.get_args(task_type)
            if args:
                return set(args)
    except Exception:
        pass

    # Hard-coded fallback (mirrors core/ctr.py TaskType Literal)
    return {
        "ORGANIZE_DOWNLOADS",
        "CREATE_PROJECT_SCAFFOLD",
        "BULK_RENAME",
        "SEARCH_DOCUMENTS",
        "GENERATE_PASSWORD",
        "SCAN_PASSWORD_FIELDS",
        "AUTOFILL_APP",
        "FIND_RECEIPTS",
    }


EXECUTOR_REGISTRY: set[str] = _build_registry()

FORBIDDEN_PATHS = ["/etc", "/sys", "/boot", "/root"]
FORBIDDEN_TERMS = ["sudo", "rm -rf", "chmod 777", "mkfs"]


# ---------------------------------------------------------------------------
# WorkflowValidator
# ---------------------------------------------------------------------------

class WorkflowValidator:
    """Validates a list of workflow steps before execution.

    Each step is a dict with at minimum:
        'executor_type' (str)  – the name of the executor to invoke.
        'parameters'    (dict) – key/value pairs; path values start with '/' or '~'.
    """

    # ------------------------------------------------------------------
    # check_feasibility
    # ------------------------------------------------------------------

    def check_feasibility(self, steps: list[dict]) -> tuple[bool, str]:
        """Verify that all paths exist and all executor types are registered.

        Args:
            steps: List of step dicts, each with 'executor_type' and 'parameters'.

        Returns:
            (True, "Feasibility check passed") if all checks pass, otherwise
            (False, "<reason>") for the first failing check.
        """
        for step in steps:
            executor_type = step.get("executor_type", "")
            parameters = step.get("parameters", {})

            # 1. Path existence check
            for value in parameters.values():
                if isinstance(value, str) and (value.startswith("/") or value.startswith("~")):
                    expanded = os.path.expanduser(value)
                    if not os.path.exists(expanded):
                        return False, f"Path not found: {expanded}"

            # 2. Executor registry check
            if executor_type not in EXECUTOR_REGISTRY:
                return False, f"Unknown executor: {executor_type}"

        return True, "Feasibility check passed"

    # ------------------------------------------------------------------
    # check_policy
    # ------------------------------------------------------------------

    def check_policy(self, steps: list[dict]) -> tuple[bool, str]:
        """Enforce forbidden-term and restricted-path policies.

        Args:
            steps: List of step dicts, each with 'executor_type' and 'parameters'.

        Returns:
            (True, "Policy check passed") if all checks pass, otherwise
            (False, "<reason>") for the first failing check.
        """
        for step in steps:
            parameters = step.get("parameters", {})
            step_str = str(step).lower()

            # 1. Forbidden term check (case-insensitive substring match)
            for term in FORBIDDEN_TERMS:
                if term.lower() in step_str:
                    return False, f"Policy violation: forbidden term '{term}' detected"

            # 2. Restricted path prefix check
            for value in parameters.values():
                if isinstance(value, str) and (value.startswith("/") or value.startswith("~")):
                    expanded = os.path.expanduser(value)
                    for forbidden in FORBIDDEN_PATHS:
                        if expanded == forbidden or expanded.startswith(forbidden + "/"):
                            return False, f"Policy violation: restricted path '{expanded}'"

        return True, "Policy check passed"


# ---------------------------------------------------------------------------
# run_demo  (required by project rules)
# ---------------------------------------------------------------------------

def run_demo() -> None:
    """Demonstrate WorkflowValidator with concrete examples."""
    validator = WorkflowValidator()

    print("=== WorkflowValidator Demo ===\n")
    print(f"Loaded executor registry ({len(EXECUTOR_REGISTRY)} types): {EXECUTOR_REGISTRY}\n")

    # --- Feasibility examples ---
    steps_ok = [
        {"executor_type": "ORGANIZE_DOWNLOADS", "parameters": {"source_dir": "~"}},
        {"executor_type": "BULK_RENAME",        "parameters": {"source_dir": "/tmp"}},
    ]
    ok, msg = validator.check_feasibility(steps_ok)
    print(f"[feasibility] valid steps    → ({ok}, '{msg}')")

    steps_bad_path = [
        {"executor_type": "ORGANIZE_DOWNLOADS", "parameters": {"source_dir": "/nonexistent/path/xyz"}},
    ]
    ok, msg = validator.check_feasibility(steps_bad_path)
    print(f"[feasibility] bad path       → ({ok}, '{msg}')")

    steps_bad_exec = [
        {"executor_type": "DELETE_EVERYTHING", "parameters": {}},
    ]
    ok, msg = validator.check_feasibility(steps_bad_exec)
    print(f"[feasibility] bad executor   → ({ok}, '{msg}')")

    # --- Policy examples ---
    print()
    steps_clean = [
        {"executor_type": "ORGANIZE_DOWNLOADS", "parameters": {"source_dir": "~/Downloads"}},
    ]
    ok, msg = validator.check_policy(steps_clean)
    print(f"[policy] clean step          → ({ok}, '{msg}')")

    steps_term = [
        {"executor_type": "ORGANIZE_DOWNLOADS", "parameters": {"cmd": "sudo rm -rf /"}},
    ]
    ok, msg = validator.check_policy(steps_term)
    print(f"[policy] forbidden term      → ({ok}, '{msg}')")

    steps_path = [
        {"executor_type": "ORGANIZE_DOWNLOADS", "parameters": {"source_dir": "/etc/passwd"}},
    ]
    ok, msg = validator.check_policy(steps_path)
    print(f"[policy] restricted path     → ({ok}, '{msg}')")

    print("\n=== Demo complete ===")


# ---------------------------------------------------------------------------
# Tests  (required by project rules: 3 test cases)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Three test cases covering the main validation branches."""
    validator = WorkflowValidator()

    print("\n=== Running Tests ===\n")

    # Test 1: feasibility passes for valid executor + existing path
    print("Test 1: feasibility — valid executor + existing path")
    ok, msg = validator.check_feasibility([
        {"executor_type": "ORGANIZE_DOWNLOADS", "parameters": {"source_dir": "/tmp"}},
    ])
    assert ok is True, f"Expected True, got {ok}: {msg}"
    assert msg == "Feasibility check passed"
    print("  PASSED\n")

    # Test 2: feasibility fails for unknown executor
    print("Test 2: feasibility — unknown executor")
    ok, msg = validator.check_feasibility([
        {"executor_type": "NUKE_SYSTEM", "parameters": {}},
    ])
    assert ok is False
    assert "Unknown executor" in msg and "NUKE_SYSTEM" in msg
    print("  PASSED\n")

    # Test 3: policy fails for forbidden term 'sudo'
    print("Test 3: policy — forbidden term 'sudo'")
    ok, msg = validator.check_policy([
        {"executor_type": "ORGANIZE_DOWNLOADS", "parameters": {"flag": "sudo do-something"}},
    ])
    assert ok is False
    assert "sudo" in msg.lower()
    print("  PASSED\n")

    print("=== All Tests Passed ===")


if __name__ == "__main__":
    run_demo()
    _run_tests()
