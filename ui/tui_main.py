"""
ui/tui_main.py
==============
Rich-based fullscreen Text User Interface for the AI OS Agent.

Layout
------
┌─────────────────────────────────┬──────────────────┐
│  Command History  (70%)         │  System Status   │
│  (scrollable, coloured badges)  │  (30%)           │
├─────────────────────────────────┴──────────────────┤
│  > input prompt                                    │
└────────────────────────────────────────────────────┘

Keyboard shortcuts
------------------
  Ctrl+C      Quit
  Ctrl+R      Resume last interrupted task
  Ctrl+U      Undo last action
  /mode <m>   Switch UI mode (delegated to ui.launcher)

Python 3.10 compatible — stdlib + rich only (no prompt_toolkit).
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional

# ── Silence ML noise before heavy imports ─────────────────────────────────────
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import warnings
import logging
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.align import Align
    from rich.spinner import Spinner as RichSpinner
    from rich.style import Style
    from rich.rule import Rule
    from rich import box
except ImportError as _e:
    sys.exit(f"[tui_main] rich is required: pip install rich\n{_e}")

logging.disable(logging.NOTSET)


# ═══════════════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════════════

class CmdStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    DONE    = auto()
    ERROR   = auto()


_STATUS_STYLE: dict[CmdStatus, tuple[str, str]] = {
    CmdStatus.PENDING: ("bold yellow",  "PENDING"),
    CmdStatus.RUNNING: ("bold cyan",    "RUNNING"),
    CmdStatus.DONE:    ("bold green",   " DONE  "),
    CmdStatus.ERROR:   ("bold red",     " ERROR "),
}


@dataclass
class HistoryEntry:
    text: str
    status: CmdStatus = CmdStatus.PENDING
    intent: str = ""
    confidence: float = 0.0
    result: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


# ═══════════════════════════════════════════════════════════════════════════════
# TUI State (shared between render thread and input thread)
# ═══════════════════════════════════════════════════════════════════════════════

class TUIState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.history: list[HistoryEntry] = []
        self.session_start: datetime = datetime.now()
        self.last_intent: str = "—"
        self.last_confidence: float = 0.0
        self.vault_status: str = "locked"
        self.running: bool = True
        self.spinner_active: bool = False
        self._scroll_offset: int = 0   # rows from bottom (0 = newest visible)
        self.status_message: str = ""   # ephemeral status bar override

    # -- thread-safe mutators --------------------------------------------------

    def add_entry(self, text: str) -> HistoryEntry:
        entry = HistoryEntry(text=text)
        with self._lock:
            self.history.append(entry)
        return entry

    def update_entry(
        self,
        entry: HistoryEntry,
        status: CmdStatus,
        intent: str = "",
        confidence: float = 0.0,
        result: str = "",
    ) -> None:
        with self._lock:
            entry.status    = status
            entry.intent    = intent
            entry.confidence = confidence
            entry.result    = result
            if status == CmdStatus.DONE:
                self.last_intent     = intent or self.last_intent
                self.last_confidence = confidence
            self.spinner_active = (status == CmdStatus.RUNNING)

    def session_duration(self) -> str:
        delta = datetime.now() - self.session_start
        secs  = int(delta.total_seconds())
        h, rem = divmod(secs, 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def scroll_up(self) -> None:
        with self._lock:
            self._scroll_offset += 1

    def scroll_down(self) -> None:
        with self._lock:
            self._scroll_offset = max(0, self._scroll_offset - 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Renderers
# ═══════════════════════════════════════════════════════════════════════════════

_LOGO = "[bold magenta]🤖 AI OS Agent[/bold magenta]  [dim]TUI v1.0[/dim]"


def _render_history(state: TUIState, panel_height: int) -> Panel:
    """Build the scrollable command history panel."""
    table = Table(
        box=box.SIMPLE_HEAD,
        expand=True,
        show_header=True,
        header_style="bold dim",
        padding=(0, 1),
    )
    table.add_column("Time",    style="dim", width=8,  no_wrap=True)
    table.add_column("Status",  width=9,     no_wrap=True)
    table.add_column("Command", ratio=3,     no_wrap=False)
    table.add_column("Intent",  ratio=2,     no_wrap=True, style="dim cyan")
    table.add_column("Conf.",   width=6,     no_wrap=True, justify="right")

    with state._lock:
        entries = list(state.history)

    # visible window (newest at bottom)
    visible_count = max(1, panel_height - 5)
    offset = state._scroll_offset
    end   = max(0, len(entries) - offset)
    start = max(0, end - visible_count)
    window = entries[start:end]

    if not window:
        table.add_row("", "", "[dim]No commands yet — type below[/dim]", "", "")
    else:
        for e in window:
            style_str, badge = _STATUS_STYLE[e.status]
            badge_text = Text(f"[{badge}]", style=style_str)
            conf_str   = f"{e.confidence:.0%}" if e.confidence else "—"
            intent_str = e.intent or "—"
            table.add_row(
                e.timestamp.strftime("%H:%M:%S"),
                badge_text,
                e.text[:80] + ("…" if len(e.text) > 80 else ""),
                intent_str,
                conf_str,
            )

    scroll_hint = ""
    if offset > 0:
        scroll_hint = f"  ↑ {offset} older command(s) hidden (↑↓ to scroll)"

    title = f"{_LOGO}  {scroll_hint}"
    return Panel(table, title=title, border_style="bright_blue", padding=(0, 1))


def _render_sidebar(state: TUIState) -> Panel:
    """Build the live system-status side panel."""
    table = Table(
        box=box.SIMPLE,
        expand=True,
        show_header=False,
        padding=(0, 1),
    )
    table.add_column("Key",   style="dim",  ratio=1)
    table.add_column("Value", style="bold", ratio=2)

    vault_style = "green" if state.vault_status == "unlocked" else "yellow"
    conf_pct    = f"{state.last_confidence:.0%}" if state.last_confidence else "—"

    rows = [
        ("⏱ Session",   state.session_duration()),
        ("🎯 Intent",   state.last_intent),
        ("📊 Conf.",    conf_pct),
        ("🔒 Vault",    Text(state.vault_status, style=vault_style)),
        ("📝 History",  str(len(state.history))),
    ]
    for k, v in rows:
        table.add_row(k, v if isinstance(v, Text) else str(v))

    shortcuts = Table(box=None, expand=True, show_header=False, padding=(0, 1))
    shortcuts.add_column("Key",  style="bold cyan",  width=8)
    shortcuts.add_column("Desc", style="dim",        ratio=1)
    for key, desc in [
        ("Ctrl+C", "Quit"),
        ("Ctrl+R", "Resume task"),
        ("Ctrl+U", "Undo last"),
        ("/mode",  "Switch UI"),
    ]:
        shortcuts.add_row(key, desc)

    from rich.console import Group
    content = Group(table, Rule(style="dim"), shortcuts)

    return Panel(
        content,
        title="[bold cyan]System Status[/bold cyan]",
        border_style="cyan",
        padding=(0, 1),
    )


def _render_input_bar(state: TUIState, current_input: str) -> Panel:
    """Build the bottom input bar."""
    if state.spinner_active:
        spinner = RichSpinner("dots", style="cyan")
        txt = Text.assemble((" Processing…", "bold cyan"))
    else:
        spinner = None
        prompt  = Text("> ", style="bold green")
        input_t = Text(current_input, style="white")
        cursor  = Text("█", style="blink bold white")
        txt     = Text.assemble(prompt, input_t, cursor)

    if state.status_message:
        status_t = Text(f"  {state.status_message}", style="italic dim")
        txt = Text.assemble(txt, status_t)

    content: object
    if spinner:
        from rich.console import Group
        content = Group(Align(spinner, align="left"), Align(txt, align="left"))
    else:
        content = Align(txt, align="left")

    return Panel(
        content,
        border_style="green",
        padding=(0, 1),
        height=3,
    )


def _build_layout() -> Layout:
    layout = Layout(name="root")
    layout.split_column(
        Layout(name="body",   ratio=1),
        Layout(name="bottom", size=5),
    )
    layout["body"].split_row(
        Layout(name="history", ratio=7),
        Layout(name="sidebar", ratio=3),
    )
    return layout


# ═══════════════════════════════════════════════════════════════════════════════
# Command processor (runs in a worker thread)
# ═══════════════════════════════════════════════════════════════════════════════

def _process_command(text: str, entry: HistoryEntry, state: TUIState) -> None:
    """Execute *text* through the NLU pipeline; update *entry* on completion."""
    state.update_entry(entry, CmdStatus.RUNNING)
    try:
        from core.nlu_router import route
        from core.workflow import run_workflow

        ctr = route(text)
        intent     = ctr.task_type
        confidence = 0.0

        # Re-classify to surface confidence score for the sidebar
        try:
            from core.nlu_router import classify_intent
            _, confidence = classify_intent(text)
        except Exception:
            pass

        run_workflow(ctr, dry_run=False)
        state.update_entry(entry, CmdStatus.DONE,
                           intent=intent, confidence=confidence,
                           result="OK")
    except Exception as exc:
        state.update_entry(entry, CmdStatus.ERROR,
                           result=str(exc))


def _handle_special(text: str, state: TUIState) -> bool:
    """
    Handle built-in keyboard shortcuts and /mode commands.
    Returns True if the command was consumed (skip NLU routing).
    """
    stripped = text.strip().lower()

    # --- Mode switch ---
    if stripped.startswith("/mode"):
        try:
            from ui.launcher import handle_mode_switch
            new_mode = handle_mode_switch(text.strip())
            if new_mode:
                state.status_message = f"Mode switch to '{new_mode}' requested — restart to apply."
        except ImportError:
            state.status_message = "ui.launcher not available."
        return True

    # --- Resume (Ctrl+R equivalent, also works typed) ---
    if any(kw in stripped for kw in ("resume", "what was i doing", "continue")):
        entry = state.add_entry(text)
        def _resume():
            state.update_entry(entry, CmdStatus.RUNNING)
            try:
                from session_manager import handle_resume_command
                from core.workflow import run_workflow
                result = handle_resume_command(text)
                if isinstance(result, tuple):
                    msg, ctr = result
                    run_workflow(ctr, dry_run=False)
                    state.update_entry(entry, CmdStatus.DONE, intent="RESUME", result=msg)
                else:
                    state.update_entry(entry, CmdStatus.DONE, intent="RESUME", result=result)
            except Exception as exc:
                state.update_entry(entry, CmdStatus.ERROR, result=str(exc))
        threading.Thread(target=_resume, daemon=True).start()
        return True

    # --- Undo ---
    if any(sub in stripped for sub in ("undo that", "revert last", "undo last", "roll back")):
        entry = state.add_entry(text)
        def _undo():
            state.update_entry(entry, CmdStatus.RUNNING)
            try:
                from checkpoint_manager import CheckpointManager
                msg = CheckpointManager().restore()
                state.update_entry(entry, CmdStatus.DONE, intent="UNDO", result=msg)
            except Exception as exc:
                state.update_entry(entry, CmdStatus.ERROR, result=str(exc))
        threading.Thread(target=_undo, daemon=True).start()
        return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# Raw-mode input reader (Linux / macOS — reads one char at a time)
# ═══════════════════════════════════════════════════════════════════════════════

def _read_char() -> str:
    """Block until one character (or escape sequence) is available."""
    import tty
    import termios

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # Arrow keys arrive as ESC [ A/B/C/D
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                return f"\x1b[{ch3}"  # e.g. "\x1b[A" = up arrow
            return "\x1b"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _input_loop(state: TUIState, console: Console) -> None:
    """
    Read characters from stdin in a background thread.
    Builds a line buffer; submits on Enter.
    Ctrl+C exits, Ctrl+R fires resume, Ctrl+U fires undo.
    Arrow keys scroll the history panel.
    """
    buf: list[str] = []
    _input_store["current"] = ""   # shared with renderer

    while state.running:
        try:
            ch = _read_char()
        except Exception:
            time.sleep(0.05)
            continue

        # ── Ctrl combos ──────────────────────────────────────────────────────
        if ch == "\x03":   # Ctrl+C
            state.running = False
            break

        if ch == "\x12":   # Ctrl+R — resume
            text = "resume"
            _handle_special(text, state)
            buf.clear()
            _input_store["current"] = ""
            continue

        if ch == "\x15":   # Ctrl+U — undo
            text = "undo last"
            _handle_special(text, state)
            buf.clear()
            _input_store["current"] = ""
            continue

        # ── Arrow keys ───────────────────────────────────────────────────────
        if ch == "\x1b[A":   # up
            state.scroll_up()
            continue
        if ch == "\x1b[B":   # down
            state.scroll_down()
            continue

        # ── Backspace ────────────────────────────────────────────────────────
        if ch in ("\x7f", "\x08"):
            if buf:
                buf.pop()
            _input_store["current"] = "".join(buf)
            continue

        # ── Enter ────────────────────────────────────────────────────────────
        if ch in ("\r", "\n"):
            text = "".join(buf).strip()
            buf.clear()
            _input_store["current"] = ""

            if not text:
                continue

            if text.lower() in ("exit", "quit", "q"):
                state.running = False
                break

            # Try special commands first; else route through NLU
            if not _handle_special(text, state):
                entry = state.add_entry(text)
                threading.Thread(
                    target=_process_command,
                    args=(text, entry, state),
                    daemon=True,
                ).start()
            continue

        # ── Printable character ──────────────────────────────────────────────
        if ch.isprintable():
            buf.append(ch)
            _input_store["current"] = "".join(buf)


# Shared mutable dict so render loop can read the current line without locking
_input_store: dict[str, str] = {"current": ""}


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Launch the TUI. Blocks until the user exits."""
    console = Console()

    if not sys.stdin.isatty():
        console.print("[red]TUI requires an interactive terminal.[/red]")
        sys.exit(1)

    state  = TUIState()
    layout = _build_layout()

    # Start input thread
    input_thread = threading.Thread(
        target=_input_loop,
        args=(state, console),
        daemon=True,
    )
    input_thread.start()

    console.clear()

    with Live(
        layout,
        console=console,
        refresh_per_second=12,
        screen=True,
        transient=False,
    ) as live:
        while state.running:
            # Measure available panel height
            try:
                h = console.size.height
            except Exception:
                h = 40
            history_height = max(10, h - 7)

            layout["history"].update(_render_history(state, history_height))
            layout["sidebar"].update(_render_sidebar(state))
            layout["bottom"].update(
                _render_input_bar(state, _input_store.get("current", ""))
            )

            # Clear one-shot status messages after 3 s
            if state.status_message:
                time.sleep(0.05)
            else:
                time.sleep(0.08)

    console.clear()
    console.print("[dim]AI OS Agent TUI exited.[/dim]")


# ═══════════════════════════════════════════════════════════════════════════════
# run_demo() — simulated session, no real TTY or NLU needed
# ═══════════════════════════════════════════════════════════════════════════════

def run_demo() -> None:
    """
    Simulate a three-command TUI session and render a static snapshot.
    Requires no display or interactive terminal.
    """
    import io

    print("=== TUI Demo — static layout snapshot ===\n")

    state = TUIState()

    # --- Simulate three commands ------------------------------------------

    # Command 1: completed successfully
    e1 = state.add_entry("organize my downloads folder")
    time.sleep(0.01)
    state.update_entry(
        e1, CmdStatus.DONE,
        intent="ORGANIZE_DOWNLOADS", confidence=0.91,
        result="Moved 14 files into sub-folders.",
    )

    # Command 2: error
    e2 = state.add_entry("find receipts in ~/NonExistentDir")
    time.sleep(0.01)
    state.update_entry(
        e2, CmdStatus.ERROR,
        intent="FIND_RECEIPTS", confidence=0.78,
        result="Directory not found: ~/NonExistentDir",
    )

    # Command 3: still pending (simulates in-flight)
    e3 = state.add_entry("bulk rename photos in ~/Pictures")
    state.update_entry(e3, CmdStatus.RUNNING)

    # --- Render to a captured console ------------------------------------
    buf = io.StringIO()
    demo_console = Console(file=buf, width=100, highlight=False, no_color=True)

    layout = _build_layout()
    layout["history"].update(_render_history(state, panel_height=20))
    layout["sidebar"].update(_render_sidebar(state))
    layout["bottom"].update(_render_input_bar(state, "bulk rename photos in ~/Pictures"))

    demo_console.print(layout)
    output = buf.getvalue()
    print(output[:3000])   # cap output for readability

    # --- Verify state ----------------------------------------------------
    assert len(state.history) == 3,             f"Expected 3 entries, got {len(state.history)}"
    assert state.history[0].status == CmdStatus.DONE,    "Entry 1 should be DONE"
    assert state.history[1].status == CmdStatus.ERROR,   "Entry 2 should be ERROR"
    assert state.history[2].status == CmdStatus.RUNNING, "Entry 3 should be RUNNING"
    assert state.last_intent == "ORGANIZE_DOWNLOADS",    "last_intent mismatch"
    assert abs(state.last_confidence - 0.91) < 0.01,    "last_confidence mismatch"

    # --- Simulate handle_mode_switch -------------------------------------
    try:
        from ui.launcher import handle_mode_switch
        result = handle_mode_switch("/mode cli")
        assert result == "cli", f"Expected 'cli', got {result!r}"
        print("\n[mode switch] /mode cli → 'cli'  ✓")
    except ImportError:
        print("\n[mode switch] ui.launcher not imported (ok in isolation)")

    print("\n=== Demo complete — all assertions passed ✓ ===")


# ── Allow `python -m ui.tui_main` ────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="AI OS Agent TUI")
    p.add_argument("--demo", action="store_true", help="Run run_demo() and exit")
    args = p.parse_args()
    if args.demo:
        run_demo()
    else:
        main()
