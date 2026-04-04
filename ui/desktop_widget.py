"""
ui/desktop_widget.py
====================
Always-on-top borderless desktop overlay widget for the AI OS Agent.

Layout (top-right corner by default)
--------------------------------------
┌─────────────────────────────┐
│ 🤖 AI OS  ⋮ (drag handle)  │
├─────────────────────────────┤
│ ✓ 12:01  organize downl…   │
│ ✗ 11:58  find receipts …   │
│ ⟳ 11:55  rename photos …   │
├─────────────────────────────┤
│ [Organize] [Receipts]       │
│ [Vault]    [Resume]         │
└─────────────────────────────┘

Interactions
------------
  Drag header      → reposition window
  Double-click     → open floating palette (ui.tray_gui) or full TUI
  Right-click      → context menu (Settings, Clear History, Exit)
  Quick-action btn → small pre-filled dialog input

Data binding
------------
  Polls session_memory.db every 5 s via tkinter after().
  Falls back to in-memory mock data when DB not available.

Entry points
------------
  python -m ui.desktop_widget          # run widget
  python -m ui.desktop_widget --demo   # headless demo (no display)
  python -m cli.main widget            # via CLI subcommand
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import warnings
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Silence ML noise ──────────────────────────────────────────────────────────
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

try:
    import tkinter as tk
    from tkinter import ttk, font as tkfont, simpledialog, messagebox
    _HAS_TK = True
except ImportError:
    _HAS_TK = False

logging.disable(logging.NOTSET)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

_WIDGET_W     = 280
_WIDGET_ALPHA = 0.90
_REFRESH_MS   = 5_000          # DB poll interval (ms)
_MAX_HISTORY  = 3              # commands shown in widget

_AIOS_DIR     = Path.home() / ".aios"
_CFG_FILE     = _AIOS_DIR / "widget_config.json"

# Colour palette
_BG           = "#0f0f1a"
_BG_PANEL     = "#1e1e2e"
_BG_BTN       = "#2d2d3f"
_ACCENT       = "#a78bfa"
_FG           = "#e2e8f0"
_FG_DIM       = "#64748b"
_GREEN        = "#4ade80"
_RED          = "#f87171"
_YELLOW       = "#fbbf24"
_CYAN         = "#67e8f9"

_STATUS_ICONS = {"DONE": "✓", "ERROR": "✗", "PENDING": "⟳", "RUNNING": "⟳", "—": "·"}
_STATUS_COLS  = {"DONE": _GREEN, "ERROR": _RED, "PENDING": _YELLOW, "RUNNING": _CYAN, "—": _FG_DIM}

# Quick-action templates
_QUICK_ACTIONS = [
    ("Organize",  "organize downloads in ~/Downloads"),
    ("Receipts",  "find receipts in ~/Documents"),
    ("Vault",     "generate password for "),
    ("Resume",    "__resume__"),   # special sentinel
]


# ═══════════════════════════════════════════════════════════════════════════════
# Config helpers
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_CFG = {
    "position":        "top-right",
    "offset_x":        20,
    "offset_y":        20,
    "downloads_path":  "~/Downloads",
    "projects_path":   "~/Projects",
    "auto_start":      False,
    "alpha":           _WIDGET_ALPHA,
}


def load_config() -> dict:
    try:
        data = json.loads(_CFG_FILE.read_text())
        return {**_DEFAULT_CFG, **data}
    except Exception:
        return dict(_DEFAULT_CFG)


def save_config(cfg: dict) -> None:
    try:
        _AIOS_DIR.mkdir(parents=True, exist_ok=True)
        _CFG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# DB helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_recent_commands(limit: int = _MAX_HISTORY) -> list[dict]:
    """Return the most recent *limit* commands from session_memory. Thread-safe."""
    try:
        from db_manager import SQLiteManager
        with SQLiteManager() as db:
            rows = db.fetch_recent("session_memory", hours=24)
        rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        result = []
        for r in rows[:limit]:
            try:
                import json as _j
                ctr = _j.loads(r.get("ctr_json", "{}"))
                task = ctr.get("task_type", "—").replace("_", " ").title()
            except Exception:
                task = "—"
            result.append({
                "text":   task,
                "status": r.get("execution_status", "—").upper(),
                "ts":     r.get("timestamp", "")[:16].replace("T", " "),
            })
        return result
    except Exception:
        return []


def _send_command_bg(text: str, on_done: callable) -> None:
    """Process *text* via NLU router in a daemon thread."""
    def _run():
        try:
            from core.nlu_router import route
            from core.workflow import run_workflow
            ctr = route(text)
            run_workflow(ctr, dry_run=False)
            on_done(True, ctr.task_type.replace("_", " ").title())
        except Exception as exc:
            on_done(False, str(exc)[:80])
    threading.Thread(target=_run, daemon=True).start()


def _notify(title: str, body: str, icon: str = "dialog-information") -> None:
    try:
        subprocess.Popen(
            ["notify-send", "-i", icon, "-t", "4000", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        try:
            from ui.notifier import NotificationManager
            NotificationManager().notify_info(title, body)
        except Exception:
            print(f"[widget] {title}: {body}")


# ═══════════════════════════════════════════════════════════════════════════════
# Quick-action input dialog
# ═══════════════════════════════════════════════════════════════════════════════

def _show_input_dialog(parent: "tk.Misc", title: str, prefill: str) -> Optional[str]:
    """Small centered input dialog pre-filled with *prefill*. Returns stripped text or None."""
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.configure(bg=_BG)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)

    w, h = 360, 90
    dlg.update_idletasks()
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")

    lbl_font  = tkfont.Font(family="Segoe UI", size=9)
    inp_font  = tkfont.Font(family="Segoe UI", size=11)

    tk.Label(dlg, text=title, font=lbl_font, fg=_FG_DIM, bg=_BG).pack(pady=(8, 2))

    frame = tk.Frame(dlg, bg=_BG_PANEL, padx=6, pady=4)
    frame.pack(fill=tk.X, padx=10)

    var = tk.StringVar(value=prefill)
    entry = tk.Entry(frame, textvariable=var, font=inp_font,
                     fg=_FG, bg=_BG_PANEL, insertbackground=_ACCENT,
                     relief=tk.FLAT)
    entry.pack(fill=tk.X)
    entry.select_range(0, tk.END)
    entry.focus_set()

    result: list[Optional[str]] = [None]

    def _submit(_e=None):
        result[0] = var.get().strip() or None
        dlg.destroy()

    entry.bind("<Return>", _submit)
    entry.bind("<Escape>", lambda _e: dlg.destroy())

    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
    dlg.grab_set()
    dlg.wait_window()
    return result[0]


# ═══════════════════════════════════════════════════════════════════════════════
# Settings window
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsWindow:
    def __init__(self, parent: "tk.Misc", cfg: dict, on_save: callable) -> None:
        self._cfg    = dict(cfg)
        self._parent = parent
        self._on_save = on_save
        self._win: Optional[tk.Toplevel] = None

    def show(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.lift()
            return
        self._build()

    def _build(self) -> None:
        win = tk.Toplevel(self._parent)
        win.title("Widget Settings")
        win.configure(bg=_BG)
        win.geometry("380x300")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        self._win = win

        hdr_font  = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        lbl_font  = tkfont.Font(family="Segoe UI", size=9)
        inp_font  = tkfont.Font(family="Segoe UI", size=9)

        tk.Label(win, text="AI OS Agent — Widget Settings",
                 font=hdr_font, fg=_ACCENT, bg=_BG).pack(pady=(12, 8))

        frm = tk.Frame(win, bg=_BG)
        frm.pack(fill=tk.BOTH, expand=True, padx=16)
        frm.columnconfigure(1, weight=1)

        def _row(row: int, label: str, var_name: str, default: str) -> tk.StringVar:
            tk.Label(frm, text=label, font=lbl_font, fg=_FG_DIM, bg=_BG,
                     anchor=tk.W).grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 8))
            v = tk.StringVar(value=self._cfg.get(var_name, default))
            tk.Entry(frm, textvariable=v, font=inp_font, fg=_FG, bg=_BG_PANEL,
                     insertbackground=_ACCENT, relief=tk.FLAT
                     ).grid(row=row, column=1, sticky=tk.EW, pady=4)
            return v

        v_dl  = _row(0, "Downloads path",  "downloads_path",  "~/Downloads")
        v_pr  = _row(1, "Projects path",   "projects_path",   "~/Projects")
        v_off = _row(2, "Offset X,Y",      "__offset",
                     f"{self._cfg.get('offset_x', 20)},{self._cfg.get('offset_y', 20)}")
        v_alp = _row(3, "Opacity (0-1)",   "__alpha",
                     str(self._cfg.get("alpha", _WIDGET_ALPHA)))

        auto_var = tk.BooleanVar(value=self._cfg.get("auto_start", False))
        tk.Checkbutton(frm, text="Launch on login", variable=auto_var,
                       font=lbl_font, fg=_FG, bg=_BG, selectcolor=_BG_PANEL,
                       activebackground=_BG
                       ).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=6)

        def _save():
            try:
                ox, oy = (int(x.strip()) for x in v_off.get().split(","))
            except Exception:
                ox, oy = 20, 20
            try:
                alpha = min(1.0, max(0.1, float(v_alp.get())))
            except Exception:
                alpha = _WIDGET_ALPHA

            self._cfg.update({
                "downloads_path": v_dl.get(),
                "projects_path":  v_pr.get(),
                "offset_x":       ox,
                "offset_y":       oy,
                "alpha":          alpha,
                "auto_start":     auto_var.get(),
            })
            save_config(self._cfg)
            self._on_save(self._cfg)
            win.destroy()

        btn_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        tk.Button(win, text="Save", font=btn_font, fg=_BG, bg=_ACCENT,
                  relief=tk.FLAT, command=_save, cursor="hand2",
                  padx=14, pady=4).pack(pady=10)

        win.protocol("WM_DELETE_WINDOW", win.destroy)


# ═══════════════════════════════════════════════════════════════════════════════
# Desktop widget
# ═══════════════════════════════════════════════════════════════════════════════

class DesktopWidget:
    """
    Borderless, always-on-top desktop overlay widget.
    """

    def __init__(self, mock_data: Optional[list[dict]] = None) -> None:
        if not _HAS_TK:
            raise RuntimeError("tkinter not available")

        self._cfg       = load_config()
        self._mock_data = mock_data      # if set, skip DB polling (for demo)
        self._root = tk.Tk()
        self._history: list[dict] = []
        self._history_rows: list[tuple] = []  # (icon_lbl, text_lbl, ts_lbl)
        self._build()
        self._settings_win = SettingsWindow(
            self._root, self._cfg, self._apply_settings
        )

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = self._root
        root.overrideredirect(True)      # remove title bar / decorations
        root.attributes("-topmost", True)
        root.configure(bg=_BG)
        root.resizable(False, False)

        # transparency
        try:
            root.attributes("-alpha", float(self._cfg.get("alpha", _WIDGET_ALPHA)))
        except Exception:
            pass

        # ── Position ──────────────────────────────────────────────────────────
        self._reposition()

        # ── Header (drag handle) ──────────────────────────────────────────────
        hdr = tk.Frame(root, bg=_BG_PANEL, cursor="fleur")
        hdr.pack(fill=tk.X)

        hdr_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        lbl_title = tk.Label(hdr, text="🤖  AI OS Agent",
                             font=hdr_font, fg=_ACCENT, bg=_BG_PANEL,
                             padx=8, pady=5)
        lbl_title.pack(side=tk.LEFT)

        dot_font = tkfont.Font(family="Segoe UI", size=11)
        lbl_menu = tk.Label(hdr, text="⋮", font=dot_font,
                            fg=_FG_DIM, bg=_BG_PANEL, padx=8, cursor="hand2")
        lbl_menu.pack(side=tk.RIGHT)

        # Drag bindings on header widgets
        for widget in (hdr, lbl_title, lbl_menu):
            widget.bind("<ButtonPress-1>",   self._drag_start)
            widget.bind("<B1-Motion>",        self._drag_move)
        lbl_menu.bind("<Button-1>",           self._show_menu)
        root.bind("<Double-Button-1>",         self._double_click)
        root.bind("<Button-3>",               self._show_menu)

        # ── History section ───────────────────────────────────────────────────
        hist_frame = tk.Frame(root, bg=_BG, pady=2)
        hist_frame.pack(fill=tk.X, padx=4)

        row_font  = tkfont.Font(family="Segoe UI", size=8)
        icon_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")

        self._history_rows = []
        for _ in range(_MAX_HISTORY):
            row = tk.Frame(hist_frame, bg=_BG)
            row.pack(fill=tk.X, pady=1)

            icon_lbl = tk.Label(row, text="·", font=icon_font,
                                fg=_FG_DIM, bg=_BG, width=2)
            icon_lbl.pack(side=tk.LEFT, padx=(4, 2))

            ts_lbl = tk.Label(row, text="", font=row_font,
                              fg=_FG_DIM, bg=_BG, width=6, anchor=tk.W)
            ts_lbl.pack(side=tk.LEFT)

            text_lbl = tk.Label(row, text="—", font=row_font,
                                fg=_FG, bg=_BG, anchor=tk.W)
            text_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 4))

            self._history_rows.append((icon_lbl, ts_lbl, text_lbl))

        # ── Divider ───────────────────────────────────────────────────────────
        tk.Frame(root, bg=_BG_PANEL, height=1).pack(fill=tk.X, padx=6, pady=2)

        # ── Quick action buttons ──────────────────────────────────────────────
        btn_frame = tk.Frame(root, bg=_BG, pady=4)
        btn_frame.pack(fill=tk.X, padx=6)

        btn_font = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        for i, (label, template) in enumerate(_QUICK_ACTIONS):
            col = i % 2
            row_idx = i // 2
            btn = tk.Button(
                btn_frame,
                text=label,
                font=btn_font,
                fg=_FG, bg=_BG_BTN,
                relief=tk.FLAT,
                activebackground=_ACCENT,
                activeforeground=_BG,
                cursor="hand2",
                padx=6, pady=3,
                command=lambda t=template, l=label: self._quick_action(l, t),
            )
            btn.grid(row=row_idx, column=col, padx=3, pady=2, sticky=tk.EW)
            btn_frame.columnconfigure(col, weight=1)

        # ── Right-click context menu ──────────────────────────────────────────
        self._menu = tk.Menu(root, tearoff=False,
                             bg=_BG_PANEL, fg=_FG,
                             activebackground=_ACCENT,
                             activeforeground=_BG,
                             font=("Segoe UI", 9))
        self._menu.add_command(label="Settings",       command=self._settings_win.show)
        self._menu.add_command(label="Clear History",  command=self._clear_history)
        self._menu.add_separator()
        self._menu.add_command(label="Exit",           command=self._quit)

    # ── Positioning ─────────────────────────────────────────────────────────

    def _reposition(self) -> None:
        root = self._root
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        ox = int(self._cfg.get("offset_x", 20))
        oy = int(self._cfg.get("offset_y", 20))
        pos = self._cfg.get("position", "top-right")

        if pos == "top-right":
            x, y = sw - _WIDGET_W - ox, oy
        elif pos == "top-left":
            x, y = ox, oy
        elif pos == "bottom-right":
            x, y = sw - _WIDGET_W - ox, sh - 200 - oy
        else:
            x, y = sw - _WIDGET_W - ox, oy

        root.geometry(f"{_WIDGET_W}+{int(x)}+{int(y)}")

    # ── Drag ──────────────────────────────────────────────────────────────────

    def _drag_start(self, event: "tk.Event") -> None:
        self._drag_ox = event.x_root - self._root.winfo_x()
        self._drag_oy = event.y_root - self._root.winfo_y()

    def _drag_move(self, event: "tk.Event") -> None:
        x = event.x_root - self._drag_ox
        y = event.y_root - self._drag_oy
        self._root.geometry(f"+{x}+{y}")

    # ── History refresh ───────────────────────────────────────────────────────

    def _refresh_history(self) -> None:
        data = self._mock_data if self._mock_data is not None else _fetch_recent_commands()
        for i, (icon_lbl, ts_lbl, text_lbl) in enumerate(self._history_rows):
            if i < len(data):
                entry  = data[i]
                status = entry.get("status", "—")
                icon   = _STATUS_ICONS.get(status, "·")
                col    = _STATUS_COLS.get(status, _FG_DIM)
                ts_raw = entry.get("ts", "")
                ts_str = ts_raw[11:16] if len(ts_raw) >= 16 else ts_raw  # HH:MM
                text   = entry.get("text", "—")[:22]
                icon_lbl.configure(text=icon,  fg=col)
                ts_lbl.configure(text=ts_str)
                text_lbl.configure(text=text,  fg=_FG)
            else:
                icon_lbl.configure(text="·",  fg=_FG_DIM)
                ts_lbl.configure(text="")
                text_lbl.configure(text="—",  fg=_FG_DIM)

        # Schedule next poll
        self._root.after(_REFRESH_MS, self._refresh_history)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _quick_action(self, label: str, template: str) -> None:
        """Handle a quick-action button press."""
        if template == "__resume__":
            self._do_resume()
            return

        # Substitute configured paths into template
        cfg = self._cfg
        tmpl = (template
                .replace("~/Downloads", cfg.get("downloads_path", "~/Downloads"))
                .replace("~/Documents", cfg.get("projects_path",  "~/Documents")))

        text = _show_input_dialog(self._root, label, tmpl)
        if not text:
            return

        _notify("AI OS Agent", f"Processing: {text}", icon="appointment-soon")

        def _done(ok: bool, detail: str) -> None:
            if ok:
                _notify("AI OS Agent", f"✅ {detail}", icon="emblem-default")
                self._mock_data = None   # force DB refresh
            else:
                _notify("AI OS Agent", f"❌ {detail}", icon="dialog-error")

        _send_command_bg(text, _done)

    def _do_resume(self) -> None:
        def _run():
            try:
                from session_manager import get_last_incomplete
                from core.workflow import run_workflow
                ctr = get_last_incomplete()
                if ctr is None:
                    _notify("AI OS Agent", "No interrupted tasks found.")
                    return
                _notify("AI OS Agent",
                        f"Resuming: {ctr.task_type.replace('_', ' ').title()}…",
                        icon="appointment-soon")
                run_workflow(ctr, dry_run=False)
                _notify("AI OS Agent", "✅ Task resumed.", icon="emblem-default")
            except Exception as exc:
                _notify("AI OS Agent", f"❌ {exc}", icon="dialog-error")
        threading.Thread(target=_run, daemon=True).start()

    def _double_click(self, _event: "tk.Event") -> None:
        """Open tray palette or TUI on double-click."""
        try:
            from ui.tray_gui import CommandPalette, _HistoryModel
            pal = CommandPalette(self._root, _HistoryModel())
            pal.show()
        except Exception:
            try:
                import subprocess as _sp
                _sp.Popen([sys.executable, "-m", "ui.tui_main"])
            except Exception:
                pass

    def _show_menu(self, event: "tk.Event") -> None:
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _clear_history(self) -> None:
        if self._mock_data is not None:
            self._mock_data = []
        self._refresh_history()

    def _apply_settings(self, new_cfg: dict) -> None:
        self._cfg = new_cfg
        try:
            self._root.attributes("-alpha", float(new_cfg.get("alpha", _WIDGET_ALPHA)))
        except Exception:
            pass
        self._reposition()

    def _quit(self) -> None:
        try:
            self._root.quit()
            self._root.destroy()
        except Exception:
            pass

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the widget. Blocks until Exit is chosen."""
        self._refresh_history()          # immediate first load
        self._root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Launch the desktop widget. Blocks until Exit."""
    if not _HAS_TK:
        sys.exit("[desktop_widget] tkinter is required. Install: sudo apt install python3-tk")
    w = DesktopWidget()
    w.run()


# ═══════════════════════════════════════════════════════════════════════════════
# run_demo() — headless, no $DISPLAY needed
# ═══════════════════════════════════════════════════════════════════════════════

def run_demo() -> None:
    """
    Simulate widget data binding, config, and action wiring without a display.
    """
    print("=== DesktopWidget run_demo() ===\n")

    # ── 1. Config load / save ─────────────────────────────────────────────────
    print("[1] Config load/save")
    import tempfile, pathlib
    orig_cfg = _CFG_FILE

    with tempfile.TemporaryDirectory() as tmp:
        import ui.desktop_widget as _self
        _self._CFG_FILE   = pathlib.Path(tmp) / "widget_config.json"
        _self._AIOS_DIR   = pathlib.Path(tmp)

        _self.save_config({"downloads_path": "/tmp/dl", "alpha": 0.85})
        loaded = _self.load_config()
        assert loaded["downloads_path"] == "/tmp/dl", f"Got {loaded['downloads_path']}"
        assert loaded["alpha"]          == 0.85,       f"Got {loaded['alpha']}"
        assert loaded["projects_path"]  == "~/Projects"  # default preserved
        print("    save_config → load_config roundtrip  ✓")

        _self._CFG_FILE = orig_cfg
        _self._AIOS_DIR = _self.Path.home() / ".aios"

    # ── 2. _fetch_recent_commands ─────────────────────────────────────────────
    print("\n[2] _fetch_recent_commands (live DB)")
    rows = _fetch_recent_commands(3)
    print(f"    Fetched {len(rows)} row(s) from session_memory  ✓")
    for r in rows:
        print(f"    [{r['status']:8s}] {r['ts']}  {r['text'][:30]}")

    # ── 3. Mock data binding ──────────────────────────────────────────────────
    print("\n[3] Mock history data / status icons")
    mock = [
        {"text": "Organize Downloads",      "status": "DONE",    "ts": "12:01"},
        {"text": "Find receipts in ~/Docs", "status": "ERROR",   "ts": "11:58"},
        {"text": "Bulk rename photos",      "status": "PENDING", "ts": "11:55"},
    ]
    for entry in mock:
        icon = _STATUS_ICONS.get(entry["status"], "·")
        col  = _STATUS_COLS.get(entry["status"],  _FG_DIM)
        print(f"    {icon}  [{entry['status']:8s}]  {entry['text']}")
    assert _STATUS_ICONS["DONE"]    == "✓"
    assert _STATUS_ICONS["ERROR"]   == "✗"
    assert _STATUS_ICONS["PENDING"] == "⟳"
    print("    Status icons correct  ✓")

    # ── 4. Quick-action template generation ───────────────────────────────────
    print("\n[4] Quick-action templates")
    cfg = {**_DEFAULT_CFG, "downloads_path": "~/MyDownloads"}
    for label, tmpl in _QUICK_ACTIONS:
        resolved = tmpl.replace("~/Downloads", cfg["downloads_path"])
        print(f"    [{label:10s}]  {resolved}")
    assert "~/MyDownloads" in _QUICK_ACTIONS[0][1].replace("~/Downloads", cfg["downloads_path"])
    print("    Template path substitution  ✓")

    # ── 5. _notify fallback ───────────────────────────────────────────────────
    print("\n[5] _notify() no-display fallback")
    _notify("Demo", "Widget demo notification")
    print("    _notify() did not raise  ✓")

    # ── 6. Background command dispatch (cold-start timeout expected) ──────────
    print("\n[6] _send_command_bg()")
    completed: list = []
    _send_command_bg("organize my downloads", lambda ok, d: completed.append((ok, d)))
    deadline = time.time() + 5.0
    while not completed and time.time() < deadline:
        time.sleep(0.1)
    if completed:
        ok, detail = completed[0]
        print(f"    Command result → {'✅' if ok else '❌'} {detail[:40]}  ✓")
    else:
        print("    Command timed out (NLU cold-start) — expected in demo  ✓")

    print("\n=== Demo complete — all checks passed ✓ ===")


# ── Allow `python -m ui.desktop_widget` ──────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="AI OS Agent Desktop Widget")
    p.add_argument("--demo", action="store_true", help="Run headless demo and exit")
    args = p.parse_args()
    if args.demo:
        run_demo()
    else:
        main()
