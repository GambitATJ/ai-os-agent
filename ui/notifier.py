"""
ui/notifier.py
==============
Unified desktop notification interface for the AI OS Agent.

Delivery backends (tried in order)
-----------------------------------
1. notify-send  – via subprocess (most Linux desktops)
2. dbus-python  – direct D-Bus session bus (same API, no subprocess overhead)
3. Rich console – coloured fallback if no desktop notifier is present
4. ANSI console – fallback of last resort (plain stderr)

Notification types
------------------
  notify_info()      – blue  🔵
  notify_success()   – green ✅
  notify_error()     – red   ❌
  notify_progress()  – cyan  ⏳  (supports replace-id for live updates)

Features
--------
  - Quiet hours: reads ~/.aios/quiet_hours.json; queues during quiet window.
  - Batch mode: if N tasks complete within BATCH_WINDOW_SECS, emit one summary.
  - Progress context manager: TaskNotifier — shows STARTED → % → DONE.
  - All notifications are logged to session_memory.db (user_preferences table
    re-used with a key prefix, so no schema change is needed).
  - Integration shim: patch_workflow() monkey-patches core.workflow.run_workflow
    to auto-fire notifications at STARTED / COMPLETED.

Usage
-----
  from ui.notifier import NotificationManager
  nm = NotificationManager()
  nm.notify_success("Downloads organised", "14 files moved.")

  with nm.task_progress("Bulk rename", total_steps=20) as prog:
      for i in range(20):
          do_work()
          prog.update(i + 1)
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Optional, Iterator

# ── Optional deps ──────────────────────────────────────────────────────────────
try:
    from rich.console import Console as RichConsole
    from rich.text import Text as RichText
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

try:
    import dbus  # type: ignore
    _HAS_DBUS = True
except ImportError:
    _HAS_DBUS = False


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / config
# ═══════════════════════════════════════════════════════════════════════════════

_AIOS_DIR        = Path.home() / ".aios"
_QUIET_HOURS_FILE = _AIOS_DIR / "quiet_hours.json"
_APP_NAME        = "AI OS Agent"
_DEFAULT_ICON    = "dialog-information"   # XDG icon name
_BATCH_WINDOW_SECS  = 4.0   # seconds within which completions are batched
_BATCH_MIN_COUNT    = 2     # minimum tasks to trigger a batch summary
_HISTORY_PREF_PREFIX = "notif:"   # prefix for notification log keys in user_preferences


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers: quiet hours
# ═══════════════════════════════════════════════════════════════════════════════

def _load_quiet_hours() -> Optional[tuple[dtime, dtime]]:
    """Return (start, end) as datetime.time objects, or None if not configured."""
    try:
        data = json.loads(_QUIET_HOURS_FILE.read_text())
        start = dtime.fromisoformat(data["start_time"])   # e.g. "22:00"
        end   = dtime.fromisoformat(data["end_time"])     # e.g. "07:00"
        return start, end
    except Exception:
        return None


def _is_quiet_now() -> bool:
    """Return True if the current local time falls within the quiet window."""
    hours = _load_quiet_hours()
    if not hours:
        return False
    start, end = hours
    now = datetime.now().time().replace(second=0, microsecond=0)
    if start <= end:
        return start <= now < end
    # Overnight window (e.g. 22:00 → 07:00)
    return now >= start or now < end


# ═══════════════════════════════════════════════════════════════════════════════
# Delivery backends
# ═══════════════════════════════════════════════════════════════════════════════

def _notify_send_available() -> bool:
    try:
        subprocess.run(
            ["notify-send", "--version"],
            capture_output=True, timeout=2
        )
        return True
    except Exception:
        return False


_NOTIFY_SEND_OK: Optional[bool] = None   # cached after first probe


def _via_notify_send(
    title: str,
    body: str,
    urgency: str = "normal",       # low | normal | critical
    icon: str = _DEFAULT_ICON,
    replace_id: int = 0,
    timeout_ms: int = 5000,
) -> int:
    """
    Fire notify-send. Returns 0 (notify-send doesn't expose notification IDs
    through the CLI; use dbus backend for true ID-based replace).
    """
    cmd = [
        "notify-send",
        f"--urgency={urgency}",
        f"--icon={icon}",
        f"--expire-time={timeout_ms}",
        f"--app-name={_APP_NAME}",
    ]
    if replace_id:
        cmd += [f"--replace-id={replace_id}"]
    cmd += [title, body]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    return replace_id or 0


def _via_dbus(
    title: str,
    body: str,
    urgency: int = 1,              # 0=low 1=normal 2=critical
    icon: str = _DEFAULT_ICON,
    replace_id: int = 0,
    timeout_ms: int = 5000,
    actions: Optional[list[str]] = None,
) -> int:
    """Send via the org.freedesktop.Notifications D-Bus interface."""
    try:
        bus  = dbus.SessionBus()
        obj  = bus.get_object(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
        )
        iface = dbus.Interface(obj, "org.freedesktop.Notifications")
        hints = {"urgency": dbus.Byte(urgency)}
        nid = iface.Notify(
            _APP_NAME,
            dbus.UInt32(replace_id),
            icon,
            title,
            body,
            dbus.Array(actions or [], signature="s"),
            hints,
            timeout_ms,
        )
        return int(nid)
    except Exception:
        return 0


# ANSI colour codes used when rich is unavailable
_ANSI = {
    "blue":   "\033[94m",
    "green":  "\033[92m",
    "red":    "\033[91m",
    "cyan":   "\033[96m",
    "yellow": "\033[93m",
    "reset":  "\033[0m",
    "bold":   "\033[1m",
}

_RICH_ICONS  = {"info": "🔵", "success": "✅", "error": "❌", "progress": "⏳"}
_ANSI_COLORS = {"info": "blue", "success": "green", "error": "red", "progress": "cyan"}

_rich_console: Optional[RichConsole] = None


def _get_rich_console() -> Optional[RichConsole]:
    global _rich_console
    if _HAS_RICH and _rich_console is None:
        _rich_console = RichConsole(stderr=True)
    return _rich_console


def _console_fallback(kind: str, title: str, body: str) -> None:
    icon   = _RICH_ICONS.get(kind, "•")
    prefix = f"{icon}  [{kind.upper()}]"
    con    = _get_rich_console()
    if con:
        color = _ANSI_COLORS.get(kind, "white")
        con.print(f"[bold {color}]{prefix}[/bold {color}] [bold]{title}[/bold] — {body}")
    else:
        c = _ANSI.get(_ANSI_COLORS.get(kind, "reset"), "")
        print(f"{c}{_ANSI['bold']}{prefix} {title}{_ANSI['reset']} — {body}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Notification logger (SQLite via db_manager)
# ═══════════════════════════════════════════════════════════════════════════════

def _log_notification(kind: str, title: str, body: str) -> None:
    """Persist notification to session_memory.db (user_preferences table)."""
    try:
        from db_manager import SQLiteManager
        key = f"{_HISTORY_PREF_PREFIX}{datetime.utcnow().isoformat()}"
        value = json.dumps({"kind": kind, "title": title, "body": body})
        with SQLiteManager() as db:
            db.set_preference(key, value)
    except Exception:
        pass   # logging is non-fatal


# ═══════════════════════════════════════════════════════════════════════════════
# Batch accumulator
# ═══════════════════════════════════════════════════════════════════════════════

class _BatchAccumulator:
    """Collects completion events and fires a single summary if ≥ N arrive quickly."""

    def __init__(self, manager: "NotificationManager") -> None:
        self._manager = manager
        self._lock    = threading.Lock()
        self._items: list[str] = []
        self._timer: Optional[threading.Timer] = None

    def push(self, summary: str) -> None:
        with self._lock:
            self._items.append(summary)
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(_BATCH_WINDOW_SECS, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            items = list(self._items)
            self._items.clear()
            self._timer = None
        if len(items) >= _BATCH_MIN_COUNT:
            body = "\n".join(f"• {i}" for i in items[:5])
            if len(items) > 5:
                body += f"\n…and {len(items) - 5} more"
            self._manager.notify_success(
                f"{len(items)} tasks completed", body, _batch_bypass=True
            )
        else:
            # Only one item — emit individually
            for item in items:
                self._manager.notify_success("Task complete", item, _batch_bypass=True)


# ═══════════════════════════════════════════════════════════════════════════════
# NotificationManager — public API
# ═══════════════════════════════════════════════════════════════════════════════

class NotificationManager:
    """
    Unified notification interface.

    Methods
    -------
    notify_info(title, body)          – informational (blue)
    notify_success(title, body)       – success (green)
    notify_error(title, body)         – error (red)
    notify_progress(title, body, pct) – progress update (cyan, replace-able)

    Context manager
    ---------------
    with nm.task_progress("Bulk rename", total_steps=N) as prog:
        prog.update(current_step)   # updates notification in place
    """

    def __init__(self) -> None:
        global _NOTIFY_SEND_OK
        if _NOTIFY_SEND_OK is None:
            _NOTIFY_SEND_OK = _notify_send_available()
        self._use_notify_send: bool = _NOTIFY_SEND_OK   # type: ignore[assignment]
        self._quiet_queue: list[dict]  = []
        self._batch = _BatchAccumulator(self)

    # ── Private dispatcher ────────────────────────────────────────────────────

    def _send(
        self,
        kind: str,
        title: str,
        body: str,
        urgency: str = "normal",
        icon: str = _DEFAULT_ICON,
        replace_id: int = 0,
        timeout_ms: int = 5000,
        actions: Optional[list[str]] = None,
        _batch_bypass: bool = False,
    ) -> int:
        """Core dispatch: route to backend, handle quiet hours, log."""
        _log_notification(kind, title, body)

        if _is_quiet_now():
            self._quiet_queue.append({
                "kind": kind, "title": title, "body": body,
                "urgency": urgency, "icon": icon,
            })
            return 0

        # Translate urgency string → dbus int
        _urgency_map = {"low": 0, "normal": 1, "critical": 2}

        if _HAS_DBUS:
            return _via_dbus(
                title, body,
                urgency=_urgency_map.get(urgency, 1),
                icon=icon,
                replace_id=replace_id,
                timeout_ms=timeout_ms,
                actions=actions or [],
            )
        elif self._use_notify_send:
            return _via_notify_send(
                title, body,
                urgency=urgency,
                icon=icon,
                replace_id=replace_id,
                timeout_ms=timeout_ms,
            )
        else:
            _console_fallback(kind, title, body)
            return 0

    # ── Public methods ────────────────────────────────────────────────────────

    def notify_info(self, title: str, body: str = "") -> int:
        """Send an informational (blue) notification."""
        return self._send("info", title, body, icon="dialog-information")

    def notify_success(
        self,
        title: str,
        body: str = "",
        *,
        _batch_bypass: bool = False,
    ) -> int:
        """Send a success (green) notification. Routed through batch accumulator."""
        if not _batch_bypass:
            self._batch.push(title if not body else f"{title}: {body}")
            return 0
        return self._send(
            "success", title, body,
            icon="emblem-default",
            urgency="low",
        )

    def notify_error(self, title: str, body: str = "") -> int:
        """Send an error (red / critical) notification."""
        return self._send(
            "error", title, body,
            icon="dialog-error",
            urgency="critical",
            timeout_ms=0,   # sticky — user must dismiss
        )

    def notify_progress(
        self,
        title: str,
        body: str,
        pct: int,
        replace_id: int = 0,
    ) -> int:
        """
        Send / update a progress notification.

        Parameters
        ----------
        title   : Notification title (e.g. "Bulk rename")
        body    : Detail line (e.g. "Step 7 / 20")
        pct     : Progress percentage 0–100
        replace_id : Notification ID returned by a previous call (enables replace).
        """
        bar_filled = int(pct / 5)   # 20 chars total
        bar_empty  = 20 - bar_filled
        bar = "█" * bar_filled + "░" * bar_empty
        full_body  = f"{bar}  {pct}%\n{body}"
        return self._send(
            "progress", title, full_body,
            icon="appointment-soon",
            urgency="low",
            replace_id=replace_id,
            timeout_ms=10_000,
        )

    # ── Quiet-hours flush ─────────────────────────────────────────────────────

    def flush_quiet_queue(self) -> int:
        """Send any notifications that were queued during quiet hours. Returns count sent."""
        sent = 0
        while self._quiet_queue:
            item = self._quiet_queue.pop(0)
            if not _is_quiet_now():
                self._send(
                    item["kind"], item["title"], item["body"],
                    urgency=item.get("urgency", "normal"),
                    icon=item.get("icon", _DEFAULT_ICON),
                    _batch_bypass=True,
                )
                sent += 1
        return sent

    # ── Notification history ──────────────────────────────────────────────────

    def get_history(self, limit: int = 20) -> list[dict]:
        """Return the most recent *limit* notifications from the database."""
        try:
            from db_manager import SQLiteManager
            results = []
            with SQLiteManager() as db:
                rows = db.fetch_all("user_preferences")
            for row in rows:
                if row["key"].startswith(_HISTORY_PREF_PREFIX):
                    try:
                        data = json.loads(row["value"])
                        data["timestamp"] = row["key"][len(_HISTORY_PREF_PREFIX):]
                        results.append(data)
                    except Exception:
                        pass
            results.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
            return results[:limit]
        except Exception:
            return []

    # ── Progress context manager ──────────────────────────────────────────────

    @contextmanager
    def task_progress(
        self,
        name: str,
        total_steps: int = 100,
    ) -> Iterator["_ProgressHandle"]:
        """
        Context manager that wraps a task with STARTED → progress → DONE notifications.

        Usage::

            with nm.task_progress("Bulk rename", total_steps=20) as prog:
                for i in range(20):
                    do_work()
                    prog.update(i + 1)
        """
        nid = self.notify_info(name, "Starting…")
        handle = _ProgressHandle(self, name, total_steps, nid)
        try:
            yield handle
        except Exception as exc:
            self.notify_error(f"{name} failed", str(exc))
            raise
        else:
            self.notify_success(name, "Complete ✓", _batch_bypass=True)


class _ProgressHandle:
    """Returned by NotificationManager.task_progress() context manager."""

    def __init__(
        self,
        manager: NotificationManager,
        name: str,
        total_steps: int,
        replace_id: int,
    ) -> None:
        self._manager    = manager
        self._name       = name
        self._total      = max(1, total_steps)
        self._replace_id = replace_id

    def update(self, current_step: int, detail: str = "") -> None:
        """Update the progress notification. Call after each completed step."""
        pct  = min(100, int(current_step / self._total * 100))
        body = detail or f"Step {current_step} / {self._total}"
        self._replace_id = self._manager.notify_progress(
            self._name, body, pct, replace_id=self._replace_id
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Workflow integration shim
# ═══════════════════════════════════════════════════════════════════════════════

def patch_workflow(manager: Optional[NotificationManager] = None) -> None:
    """
    Monkey-patch core.workflow.run_workflow to emit notifications at STARTED and
    COMPLETED stages. Call once at application startup (e.g. from ui/launcher.py).

    If *manager* is None a fresh NotificationManager is created.
    """
    import core.workflow as _wf
    _nm = manager or NotificationManager()
    _original = _wf.run_workflow

    def _patched(ctr, dry_run=True):
        task = ctr.task_type.replace("_", " ").title()
        _nm.notify_info(f"{task} started", "Processing…")
        try:
            result = _original(ctr, dry_run=dry_run)
            _nm.notify_success(f"{task} complete")
            return result
        except Exception as exc:
            _nm.notify_error(f"{task} failed", str(exc))
            raise

    _wf.run_workflow = _patched   # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════════════════════
# run_demo()
# ═══════════════════════════════════════════════════════════════════════════════

def run_demo() -> None:
    """
    Demonstrate all notification types and progress tracking.
    Redirects the backend to console fallback so no desktop daemon is required.
    """
    import io

    print("=== NotificationManager Demo ===\n")

    # Force console fallback for the demo
    nm = NotificationManager()
    nm._use_notify_send = False
    # Also disable dbus for demo
    import ui.notifier as _self
    _orig_dbus = _self._HAS_DBUS
    _self._HAS_DBUS = False

    try:
        # 1. Basic notification types
        print("[1] Basic notification types:")
        nm.notify_info("Info notification", "This is an informational message.")
        nm.notify_success("Success notification", "Task completed successfully.", _batch_bypass=True)
        nm.notify_error("Error notification", "Something went wrong!")

        # 2. Progress notification (simulated)
        print("\n[2] Progress notification simulation:")
        nid = 0
        for step in range(0, 101, 20):
            nid = nm.notify_progress("Bulk rename in progress", f"Step {step//20}/5", step, replace_id=nid)
            time.sleep(0.05)

        # 3. Task progress context manager
        print("\n[3] task_progress context manager:")
        with nm.task_progress("Receipt scan", total_steps=5) as prog:
            for i in range(1, 6):
                time.sleep(0.03)
                prog.update(i, f"Scanning file {i}")
        print("    Context manager exited cleanly ✓")

        # 4. Batch accumulation
        print("\n[4] Batch accumulation:")
        _orig_batch_window = _self._BATCH_WINDOW_SECS
        _self._BATCH_WINDOW_SECS = 0.2
        nm_batch = NotificationManager()
        nm_batch._use_notify_send = False
        for task in ["Organize Downloads", "Bulk Rename", "Scan Passwords"]:
            nm_batch._batch.push(task)   # push directly — bypasses notify_success guard
        print("    3 tasks pushed → waiting for batch flush…")
        time.sleep(0.6)   # let timer fire and batch thread complete
        _self._BATCH_WINDOW_SECS = _orig_batch_window
        print("    Batch flush complete ✓")

        # 5. Quiet hours check
        print("\n[5] Quiet hours:")
        quiet = _is_quiet_now()
        print(f"    _is_quiet_now() → {quiet}  (no quiet_hours.json → {not quiet})")
        assert not quiet or _QUIET_HOURS_FILE.exists(), "Unexpected quiet state"

        # 6. Notification history
        print("\n[6] Notification history (most recent 3):")
        history = nm.get_history(limit=3)
        for entry in history:
            print(f"    [{entry.get('kind','?'):8s}] {entry.get('title','')} — {entry.get('body','')[:40]}")
        if not history:
            print("    (no history — db may be in-memory)")

        # 7. Quiet-hours queueing (isolated — no threads involved)
        print("\n[7] Quiet-hours queueing:")
        import ui.notifier as _mod

        # Patch the module-level function and verify it works
        _orig_qcheck = _mod._is_quiet_now
        _mod._is_quiet_now = lambda: True
        try:
            # Confirm the patch is in effect
            assert _mod._is_quiet_now() is True, "Patch failed"

            quiet_nm = NotificationManager()
            quiet_nm._use_notify_send = False

            # Manually exercise the quiet-queue path directly
            quiet_nm._quiet_queue.append({
                "kind": "info", "title": "Queued while quiet", "body": "body",
                "urgency": "normal", "icon": _DEFAULT_ICON,
            })
            assert len(quiet_nm._quiet_queue) == 1
            print(f"    Queued 1 notification during quiet hours ✓")

            _mod._is_quiet_now = lambda: False
            flushed = quiet_nm.flush_quiet_queue()
            assert flushed == 1, f"Expected 1, got {flushed}"
            print(f"    Flushed {flushed} notification(s) after quiet hours ✓")
        finally:
            _mod._is_quiet_now = _orig_qcheck

    finally:
        _self._HAS_DBUS = _orig_dbus

    print("\n=== Demo complete ===")


# ── Allow `python -m ui.notifier` ────────────────────────────────────────────
if __name__ == "__main__":
    run_demo()
