"""
ui/chat.py
==========
Single, stable Rich-based chat REPL for the AI OS Agent.

Design goals
------------
- No threading during rendering — no Live layout, no raw-mode input.
  Uses plain input() for reading, rich.Console.print() for output.
- Zero glitch: each response is printed after the command finishes;
  the screen is never written to from two threads at once.
- Instant startup: heavy ML imports happen on first command, not at launch.

Launch
------
    python -m ui.chat
    python -m cli.main          # (default when no subcommand given)
"""

from __future__ import annotations

import os
import sys
import time
import warnings
import logging
import threading
from datetime import datetime
from typing import Optional

# ── Silence ML noise before any heavy import ──────────────────────────────────
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

try:
    from rich.console import Console
    from rich.text import Text
    from rich.rule import Rule
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.padding import Padding
    from rich.spinner import Spinner as RichSpinner
    from rich.live import Live
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

logging.disable(logging.NOTSET)

# ── Console (shared, single instance) ────────────────────────────────────────
con = Console(highlight=False) if _HAS_RICH else None

# ── Theme ────────────────────────────────────────────────────────────────────
_C = {
    "accent":  "#a78bfa",
    "green":   "#4ade80",
    "red":     "#f87171",
    "yellow":  "#fbbf24",
    "cyan":    "#67e8f9",
    "dim":     "#64748b",
    "bold":    "bold white",
}

# ── Shortcuts shown in sidebar ────────────────────────────────────────────────
_SHORTCUTS = [
    ("exit / quit",    "Leave the chat"),
    ("undo",           "Revert last action"),
    ("resume",         "Resume interrupted task"),
    ("history",        "Show recent commands"),
    ("clear",          "Clear the screen"),
]

# ── In-session history ────────────────────────────────────────────────────────
_session_history: list[dict] = []   # {text, intent, status, ts, elapsed}


# ═══════════════════════════════════════════════════════════════════════════════
# Output helpers (all go through the shared Console)
# ═══════════════════════════════════════════════════════════════════════════════

def _p(*args, **kwargs) -> None:
    if con:
        con.print(*args, **kwargs)
    else:
        print(*args)


def _rule(title: str = "") -> None:
    if con:
        con.print(Rule(title, style=_C["dim"]))
    else:
        print("─" * 60, title)


def _print_header() -> None:
    if not con:
        print("=== AI OS Agent ===")
        return
    con.print()
    con.print(Panel(
        Text.assemble(
            ("🤖  AI OS Agent", f"bold {_C['accent']}"),
            ("  ·  ", _C["dim"]),
            ("Natural language → action", _C["dim"]),
        ),
        border_style=_C["accent"],
        padding=(0, 2),
    ))
    _print_shortcuts()
    con.print()


def _print_shortcuts() -> None:
    if not con:
        return
    lines = [f"  [{_C['dim']}]{k}[/]  {v}" for k, v in _SHORTCUTS]
    con.print(
        Panel(
            "\n".join(lines),
            title=f"[{_C['dim']}]shortcuts[/]",
            border_style=_C["dim"],
            padding=(0, 1),
        )
    )


def _print_user_line(text: str) -> None:
    if con:
        con.print(
            Text.assemble(
                ("  >  ", f"bold {_C['accent']}"),
                (text, "bold white"),
            )
        )
    else:
        print(f"  >  {text}")


def _print_thinking() -> None:
    """Print a static 'thinking' line. No threads / Live."""
    if con:
        con.print(f"  [{_C['dim']}]⟳  thinking…[/]", end="\r")
    else:
        print("  thinking...", end="\r", flush=True)


def _clear_line() -> None:
    if con:
        con.print(" " * 40, end="\r")
    else:
        print(" " * 40, end="\r", flush=True)


def _print_result(entry: dict) -> None:
    """Pretty-print a completed command entry."""
    status  = entry.get("status", "DONE")
    intent  = entry.get("intent", "—").replace("_", " ").title()
    elapsed = entry.get("elapsed", 0.0)
    detail  = entry.get("detail", "")

    if status == "DONE":
        icon  = "✓"
        color = _C["green"]
    elif status == "ERROR":
        icon  = "✗"
        color = _C["red"]
    else:
        icon  = "⟳"
        color = _C["yellow"]

    if con:
        line = Text()
        line.append(f"  {icon}  ", f"bold {color}")
        line.append(intent, "bold white")
        line.append(f"  [{elapsed:.1f}s]", _C["dim"])
        con.print(line)
        if detail and status == "ERROR":
            con.print(f"     [{_C['red']}]{detail[:120]}[/]")
        elif detail and status == "DONE":
            con.print(f"     [{_C['dim']}]{detail[:120]}[/]")
    else:
        print(f"  {icon}  {intent}  [{elapsed:.1f}s]")
        if detail:
            print(f"     {detail[:120]}")


def _print_history_table() -> None:
    if not _session_history:
        _p(f"  [{_C['dim']}]No commands this session.[/]")
        return
    if con:
        for i, e in enumerate(_session_history, 1):
            status = e.get("status", "—")
            icon   = {"DONE": "✓", "ERROR": "✗"}.get(status, "⟳")
            color  = {"DONE": _C["green"], "ERROR": _C["red"]}.get(status, _C["yellow"])
            ts     = e.get("ts", "")
            text   = e.get("text", "")[:50]
            con.print(f"  [{_C['dim']}]{i:2d}[/]  [{color}]{icon}[/]  [{_C['dim']}]{ts}[/]  {text}")
    else:
        for i, e in enumerate(_session_history, 1):
            print(f"  {i:2d}  {e.get('status','?')}  {e.get('ts','')}  {e.get('text','')[:50]}")


# ═══════════════════════════════════════════════════════════════════════════════
# Command dispatch
# ═══════════════════════════════════════════════════════════════════════════════

def _dispatch(text: str) -> dict:
    """
    Route *text* through the existing NLU + workflow pipeline.
    Returns an entry dict with status / intent / detail / elapsed.
    """
    entry = {
        "text":    text,
        "ts":      datetime.now().strftime("%H:%M"),
        "status":  "ERROR",
        "intent":  "—",
        "detail":  "",
        "elapsed": 0.0,
    }
    t0 = time.time()
    try:
        # Lazy import — keeps startup fast
        from core.nlu_router import route
        from core.workflow import run_workflow

        ctr = route(text)
        entry["intent"] = ctr.task_type

        if con:
            print()
            
        run_workflow(ctr, dry_run=False)

        if con:
            print()
            
        entry["detail"] = "Executed successfully."
        entry["status"] = "DONE"

    except ValueError as exc:
        entry["detail"] = str(exc)
        entry["status"] = "ERROR"
    except NotImplementedError as exc:
        entry["detail"] = str(exc)
        entry["status"] = "ERROR"
    except Exception as exc:
        entry["detail"] = str(exc)
        entry["status"] = "ERROR"

    entry["elapsed"] = time.time() - t0
    return entry


def _handle_resume(text: str) -> None:
    from session_manager import handle_resume_command
    from core.workflow import run_workflow as rwf
    result = handle_resume_command(text)
    if isinstance(result, tuple):
        msg, ctr = result
        _p(f"  [{_C['cyan']}]{msg}[/]")
        rwf(ctr, dry_run=False)
        _p(f"  [{_C['green']}]✓  Resumed.[/]")
    else:
        _p(f"  [{_C['dim']}]{result}[/]")


def _handle_undo(text: str) -> None:
    from checkpoint_manager import CheckpointManager
    if text.strip().lower() in ("undo", "undo last", "revert last", "roll back"):
        msg = CheckpointManager().restore()
    else:
        # Semantic undo: find nearest checkpoint by query
        try:
            from core.nlu_router import get_model
            from db_manager import SQLiteManager
            import numpy as np
            query = text[5:].strip() if text.lower().startswith("undo ") else text
            model = get_model()
            q_emb = model.encode([query])[0]
            db    = SQLiteManager()
            rows  = db.fetch_all("checkpoints")
            db.close()
            best_id, best_score = None, -1.0
            for row in rows:
                c_emb = model.encode([row["command_text"]])[0]
                score = float(np.dot(q_emb, c_emb) /
                              max(np.linalg.norm(q_emb) * np.linalg.norm(c_emb), 1e-9))
                if score > best_score:
                    best_score, best_id = score, row["id"]
            if best_id is not None:
                cm  = CheckpointManager()
                msg = cm.restore(best_id)
            else:
                msg = "No checkpoints found."
        except Exception as exc:
            msg = str(exc)
    _p(f"  [{_C['cyan']}]↩  {msg}[/]")


def _handle_delete_feature(text: str) -> None:
    lo = text.lower()
    command = text
    for kw in _DELETE_FEATURE_KEYWORDS:
        if lo.startswith(kw):
            command = text[len(kw):].strip()
            break
            
    if not command:
        _p(f"  [{_C['red']}]✗ Please specify a feature name to delete.[/]")
        return
        
    feat = command.upper()
    _p(f"  [{_C['yellow']}]⚠ Are you sure you want to completely disable the feature '{feat}'? (y/n)[/]")
    if con:
        con.print(f"[{_C['accent']}]ai-os[/] [bold]›[/] ", end="")
    choice = input().strip().lower()
    if choice == "y":
        from db_manager import SQLiteManager
        db = SQLiteManager()
        db.set_preference(f"disabled_feature_{feat}", feat)
        
        import core.nlu_router
        if feat in core.nlu_router.INTENT_EXAMPLES:
            del core.nlu_router.INTENT_EXAMPLES[feat]
            core.nlu_router._INTENT_EMBEDDINGS = None
            
        _p(f"  [{_C['green']}]✓ Feature '{feat}' successfully disabled.[/]")
    else:
        _p(f"  [{_C['dim']}]Cancelled.[/]")


# ═══════════════════════════════════════════════════════════════════════════════
# Main REPL loop
# ═══════════════════════════════════════════════════════════════════════════════

_RESUME_KEYWORDS = ("resume", "continue", "what was i doing", "what did i do", "yesterday")
_UNDO_KEYWORDS   = ("undo", "revert last", "roll back", "undo last", "undo that")
_DELETE_FEATURE_KEYWORDS = ("delete feature", "remove feature", "disable feature")


def run(first_command: Optional[str] = None) -> None:
    """
    Start the interactive REPL. Blocks until the user types 'exit'.

    Parameters
    ----------
    first_command : str, optional
        If provided, execute this command immediately before the first prompt.
    """
    _print_header()

    if first_command:
        _resolve_and_print(first_command)

    while True:
        try:
            if con:
                # Rich prompt — plain input() to avoid threading issues
                con.print(f"\n[{_C['accent']}]ai-os[/] [bold]›[/] ", end="")
            text = input().strip()
        except (EOFError, KeyboardInterrupt):
            _p(f"\n  [{_C['dim']}]Bye.[/]")
            break

        if not text:
            continue

        if text.lower() in ("exit", "quit", "bye"):
            _p(f"\n  [{_C['dim']}]Bye.[/]")
            break

        if text.lower() in ("clear", "cls"):
            if con:
                con.clear()
                _print_header()
            else:
                os.system("clear")
            continue

        if text.lower() in ("history", "hist"):
            _rule("session history")
            _print_history_table()
            continue

        if text.lower().startswith("help"):
            _print_shortcuts()
            continue

        _resolve_and_print(text)


def _resolve_and_print(text: str) -> None:
    """Classify and execute a single command, then print the result."""
    _print_user_line(text)
    lo = text.lower()

    # ── Built-in handlers ──────────────────────────────────────────────────
    if any(kw in lo for kw in _RESUME_KEYWORDS):
        _print_thinking()
        _clear_line()
        try:
            _handle_resume(text)
        except Exception as exc:
            _p(f"  [{_C['red']}]✗  {exc}[/]")
        return

    if any(lo == kw or lo.startswith("undo ") for kw in _UNDO_KEYWORDS):
        _print_thinking()
        _clear_line()
        _handle_undo(text)
        return

    if any(lo.startswith(kw) for kw in _DELETE_FEATURE_KEYWORDS):
        _print_thinking()
        _clear_line()
        _handle_delete_feature(text)
        return

    # ── NLU dispatch ───────────────────────────────────────────────────────
    _print_thinking()
    entry = _dispatch(text)
    _clear_line()
    _print_result(entry)
    _session_history.append(entry)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry points
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    run()


if __name__ == "__main__":
    main()
