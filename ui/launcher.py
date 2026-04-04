"""
ui/launcher.py
==============
Unified entry point for all AI OS Agent UI modes.

Priority order for auto-detection
----------------------------------
1. GUI   – $DISPLAY is set AND tkinter is importable
2. TUI   – stdin/stdout are TTYs AND rich is importable
3. Voice – microphone accessible AND speech_recognition + pyaudio present
4. CLI   – always available (classic REPL fallback)

CLI flags
---------
--gui, --tui, --voice, --cli   Force a specific mode
--choose                        Show the launch menu even if a preference exists
--demo                          Run run_demo() and exit

Mode switching at runtime
-------------------------
In any interactive UI loop call handle_mode_switch("/mode tui") (or gui/voice/cli).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Optional-dependency availability flags (populated by detect_capabilities) ─
_HAS_TKINTER = False
_HAS_RICH = False
_HAS_VOICE = False
_DISPLAY_SET = False
_IS_TTY = False


# ═══════════════════════════════════════════════════════════════════════════════
# Capability detection
# ═══════════════════════════════════════════════════════════════════════════════

def detect_capabilities() -> dict[str, bool]:
    """Probe the runtime environment and return a capability map."""
    global _HAS_TKINTER, _HAS_RICH, _HAS_VOICE, _DISPLAY_SET, _IS_TTY

    # GUI: needs $DISPLAY (X11/Wayland) and tkinter
    _DISPLAY_SET = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    try:
        import tkinter  # noqa: F401
        _HAS_TKINTER = True
    except Exception:
        _HAS_TKINTER = False

    # TUI: needs a real interactive terminal and rich
    _IS_TTY = sys.stdin.isatty() and sys.stdout.isatty()
    try:
        import rich  # noqa: F401
        _HAS_RICH = True
    except Exception:
        _HAS_RICH = False

    # Voice: needs pyaudio + speech_recognition
    try:
        import pyaudio  # noqa: F401
        import speech_recognition  # noqa: F401
        _HAS_VOICE = True
    except Exception:
        _HAS_VOICE = False

    return {
        "gui":   _DISPLAY_SET and _HAS_TKINTER,
        "tui":   _IS_TTY and _HAS_RICH,
        "voice": _HAS_VOICE,
        "cli":   True,  # always available
    }


def available_modes(caps: dict[str, bool]) -> list[str]:
    """Return an ordered list of available mode names."""
    order = ["gui", "tui", "voice", "cli"]
    return [m for m in order if caps.get(m)]


# ═══════════════════════════════════════════════════════════════════════════════
# Preference persistence
# ═══════════════════════════════════════════════════════════════════════════════

_AIOS_DIR = Path.home() / ".aios"
_JSON_PREF_FILE = _AIOS_DIR / "ui_config.json"


def _load_json_pref() -> Optional[str]:
    """Read the JSON preference file; return None if absent/corrupt."""
    try:
        data = json.loads(_JSON_PREF_FILE.read_text())
        return data.get("ui_mode")
    except Exception:
        return None


def _save_json_pref(mode: str) -> None:
    """Write the mode preference to the JSON file."""
    try:
        _AIOS_DIR.mkdir(parents=True, exist_ok=True)
        _JSON_PREF_FILE.write_text(json.dumps({"ui_mode": mode}, indent=2))
    except Exception:
        pass  # non-fatal


def _db_get_pref(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a preference from SQLite via SQLiteManager."""
    try:
        from db_manager import SQLiteManager
        with SQLiteManager() as db:
            return db.get_preference(key, default)
    except Exception:
        return default


def _db_set_pref(key: str, value: str) -> None:
    """Persist a preference to SQLite via SQLiteManager."""
    try:
        from db_manager import SQLiteManager
        with SQLiteManager() as db:
            db.set_preference(key, value)
    except Exception:
        pass  # non-fatal


def load_mode_preference() -> Optional[str]:
    """Return the saved mode preference (SQLite preferred, JSON fallback)."""
    pref = _db_get_pref("ui_mode")
    if pref:
        return pref
    return _load_json_pref()


def save_mode_preference(mode: str) -> None:
    """Persist the mode preference to both SQLite and JSON."""
    _db_set_pref("ui_mode", mode)
    _save_json_pref(mode)


# ═══════════════════════════════════════════════════════════════════════════════
# Launch menu (first-run / --choose)
# ═══════════════════════════════════════════════════════════════════════════════

_MODE_LABELS = {
    "gui":   "GUI       – graphical tray window (requires display + tkinter)",
    "tui":   "TUI       – rich terminal UI       (requires rich)",
    "voice": "Voice     – voice command mode      (requires pyaudio + speech_recognition)",
    "cli":   "CLI       – classic text REPL       (always available)",
}


def show_launch_menu(caps: dict[str, bool]) -> str:
    """Print the numbered menu and return the user's chosen mode."""
    modes = available_modes(caps)

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║         AI OS Agent — Choose Your Interface      ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()
    for i, mode in enumerate(modes, 1):
        print(f"  [{i}]  {_MODE_LABELS[mode]}")
    print()

    while True:
        try:
            raw = input("  Select mode (number or name): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Defaulting to CLI mode.")
            return "cli"

        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(modes):
                chosen = modes[idx]
                break
            print(f"  ⚠  Please enter a number between 1 and {len(modes)}.")
        elif raw in modes:
            chosen = raw
            break
        else:
            print(f"  ⚠  Unknown mode '{raw}'. Options: {', '.join(modes)}")

    print(f"\n  ✓  Preference saved — launching {chosen.upper()} mode.\n")
    save_mode_preference(chosen)
    return chosen


# ═══════════════════════════════════════════════════════════════════════════════
# Mode switching at runtime
# ═══════════════════════════════════════════════════════════════════════════════

def handle_mode_switch(text: str) -> Optional[str]:
    """
    Parse a "/mode <name>" command and return the requested mode name,
    or None if *text* is not a mode-switch command.

    Call this inside any UI loop:
        new_mode = handle_mode_switch(user_input)
        if new_mode:
            launch_mode(new_mode)
    """
    stripped = text.strip().lower()
    if not stripped.startswith("/mode"):
        return None

    parts = stripped.split(maxsplit=1)
    if len(parts) < 2:
        print("  Usage: /mode [gui|tui|voice|cli]")
        return None

    requested = parts[1].strip()
    valid = {"gui", "tui", "voice", "cli"}
    if requested not in valid:
        print(f"  ⚠  Unknown mode '{requested}'. Valid: {', '.join(sorted(valid))}")
        return None

    print(f"\n  ↪  Switching to {requested.upper()} mode…\n")
    save_mode_preference(requested)
    return requested


# ═══════════════════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════════════════

def _health_check() -> list[str]:
    """
    Run startup health checks.
    Returns a (possibly empty) list of human-readable warning strings.
    """
    warnings_out: list[str] = []

    # Check vault DB
    project_root = Path(__file__).resolve().parent.parent
    vault_db = project_root / "session_memory.db"
    if not vault_db.exists():
        warnings_out.append(
            "⚠  Vault database not found. Run any command once to initialise it."
        )

    # Check for sentence-transformer model cache
    model_cache = Path.home() / ".cache" / "torch" / "sentence_transformers"
    if not model_cache.exists():
        warnings_out.append(
            "⚠  Sentence-transformer models not cached yet — first NL command will be slow."
        )

    return warnings_out


def _print_warnings(warnings: list[str]) -> None:
    if warnings:
        print()
        for w in warnings:
            print(f"  {w}")
        print()


# ═══════════════════════════════════════════════════════════════════════════════
# GUI splash screen
# ═══════════════════════════════════════════════════════════════════════════════

def _show_splash(duration: float = 2.5) -> None:
    """
    Display a tkinter splash window that fades in the logo, shows a loading bar,
    then destroys itself.  No-ops if tkinter is unavailable.
    """
    if not (_HAS_TKINTER and _DISPLAY_SET):
        return

    try:
        import tkinter as tk
        from tkinter import font as tkfont

        root = tk.Tk()
        root.withdraw()  # hide the main window during splash

        splash = tk.Toplevel(root)
        splash.overrideredirect(True)  # borderless
        splash.configure(bg="#0f0f1a")

        # Centre on screen
        sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
        w, h = 480, 260
        x, y = (sw - w) // 2, (sh - h) // 2
        splash.geometry(f"{w}x{h}+{x}+{y}")
        splash.attributes("-alpha", 0.0)

        # Logo / title
        header_font = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        sub_font    = tkfont.Font(family="Segoe UI", size=10)

        tk.Label(
            splash, text="🤖  AI OS Agent",
            font=header_font, fg="#a78bfa", bg="#0f0f1a"
        ).pack(pady=(40, 4))

        tk.Label(
            splash, text="Initialising…",
            font=sub_font, fg="#94a3b8", bg="#0f0f1a"
        ).pack()

        # Progress bar canvas
        canvas = tk.Canvas(splash, width=360, height=10, bg="#1e1e2e",
                           highlightthickness=0)
        canvas.pack(pady=20)
        bar = canvas.create_rectangle(0, 0, 0, 10, fill="#a78bfa", outline="")

        status_var = tk.StringVar(value="Loading…")
        tk.Label(
            splash, textvariable=status_var,
            font=sub_font, fg="#64748b", bg="#0f0f1a"
        ).pack()

        # ── Animation helpers ────────────────────────────────────────────────
        _alpha = [0.0]
        _progress = [0.0]
        steps = [
            (0.3, "Checking dependencies…"),
            (0.6, "Loading session memory…"),
            (0.85, "Warming up NLU router…"),
            (1.0, "Ready!"),
        ]
        _step_idx = [0]

        def _fade_in():
            if _alpha[0] < 1.0:
                _alpha[0] = min(_alpha[0] + 0.05, 1.0)
                splash.attributes("-alpha", _alpha[0])
                splash.after(30, _fade_in)
            else:
                _animate()

        def _animate():
            if _step_idx[0] < len(steps):
                target, label = steps[_step_idx[0]]
                _progress[0] = min(_progress[0] + 0.04, target)
                canvas.coords(bar, 0, 0, int(360 * _progress[0]), 10)
                status_var.set(label)
                if _progress[0] >= target:
                    _step_idx[0] += 1
                splash.after(40, _animate)
            else:
                splash.after(400, _finish)

        def _finish():
            splash.destroy()
            root.destroy()

        splash.after(50, _fade_in)
        root.mainloop()

    except Exception:
        pass  # splash is decorative — never block startup


# ═══════════════════════════════════════════════════════════════════════════════
# Mode launchers
# ═══════════════════════════════════════════════════════════════════════════════

def launch_cli() -> None:
    """Launch the classic text REPL."""
    from cli.main import interactive_mode
    interactive_mode()


def launch_tui() -> None:
    """Launch the rich TUI (ui.tui_main)."""
    try:
        from ui.tui_main import main as tui_main
        tui_main()
    except ImportError:
        print("  ⚠  TUI not available (ui/tui_main.py not found). Falling back to CLI.")
        launch_cli()


def launch_gui() -> None:
    """Launch the system-tray GUI (ui.tray_gui), preceded by a splash screen."""
    _show_splash()
    try:
        from ui.tray_gui import main as gui_main
        gui_main()
    except ImportError:
        print("  ⚠  GUI not available (ui/tray_gui.py not found). Falling back to CLI.")
        launch_cli()


def launch_voice() -> None:
    """Launch the voice command interface (ui.voice_mode)."""
    try:
        from ui.voice_mode import main as voice_main
        voice_main()
    except ImportError:
        print("  ⚠  Voice mode not available (ui/voice_mode.py not found). Falling back to CLI.")
        launch_cli()


_LAUNCHERS = {
    "gui":   launch_gui,
    "tui":   launch_tui,
    "voice": launch_voice,
    "cli":   launch_cli,
}


def launch_mode(mode: str) -> None:
    """Dispatch to the appropriate launcher function."""
    launcher = _LAUNCHERS.get(mode)
    if launcher is None:
        print(f"  ⚠  Unknown mode '{mode}'. Falling back to CLI.")
        launch_cli()
    else:
        launcher()


# ═══════════════════════════════════════════════════════════════════════════════
# Demo
# ═══════════════════════════════════════════════════════════════════════════════

def run_demo() -> None:
    """
    Simulate auto-detection, preference save/load, and mode-switch parsing.
    Requires no display, microphone, or real UI frameworks.
    """
    print("=== UI Launcher — run_demo() ===\n")

    # 1. Capability detection
    caps = detect_capabilities()
    print(f"[1] Detected capabilities: {caps}")
    modes = available_modes(caps)
    print(f"    Available modes (in priority order): {modes}\n")

    # 2. Preference persistence (in-memory SQLite via db_manager demo path)
    print("[2] Preference persistence")
    try:
        from db_manager import SQLiteManager
        with SQLiteManager(db_path=":memory:") as db:
            db.set_preference("ui_mode", "cli")
            val = db.get_preference("ui_mode")
            assert val == "cli", f"Expected 'cli', got {val!r}"
            print(f"    set_preference('ui_mode', 'cli') → get_preference → {val!r}  ✓")
    except Exception as exc:
        print(f"    SQLiteManager not available in demo: {exc}")

    # 3. JSON preference file (temp path)
    print("\n[3] JSON preference file")
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        global _AIOS_DIR, _JSON_PREF_FILE
        orig_dir, orig_file = _AIOS_DIR, _JSON_PREF_FILE
        _AIOS_DIR = pathlib.Path(tmp)
        _JSON_PREF_FILE = _AIOS_DIR / "ui_config.json"
        _save_json_pref("tui")
        loaded = _load_json_pref()
        assert loaded == "tui", f"Expected 'tui', got {loaded!r}"
        print(f"    _save_json_pref('tui') → _load_json_pref() → {loaded!r}  ✓")
        _AIOS_DIR, _JSON_PREF_FILE = orig_dir, orig_file

    # 4. Mode-switch command parsing
    print("\n[4] handle_mode_switch()")
    test_cases = [
        ("/mode tui",     "tui"),
        ("/mode gui",     "gui"),
        ("/mode voice",   "voice"),
        ("/mode cli",     "cli"),
        ("hello world",   None),
        ("/mode unknown", None),
    ]
    for text, expected in test_cases:
        # Patch save to avoid touching real DB during demo
        orig_save = save_mode_preference.__code__
        result = handle_mode_switch(text)
        status = "✓" if result == expected else f"✗ (got {result!r})"
        print(f"    {text!r:25s} → {str(result):8s} {status}")

    # 5. Health check
    print("\n[5] Health check")
    warnings = _health_check()
    if warnings:
        for w in warnings:
            print(f"    {w}")
    else:
        print("    All systems nominal  ✓")

    print("\n=== Demo complete ===")


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ui.launcher",
        description="AI OS Agent — unified UI launcher",
        add_help=True,
    )
    mode_group = p.add_mutually_exclusive_group()
    mode_group.add_argument("--gui",   action="store_true", help="Force GUI mode")
    mode_group.add_argument("--tui",   action="store_true", help="Force TUI mode")
    mode_group.add_argument("--voice", action="store_true", help="Force Voice mode")
    mode_group.add_argument("--cli",   action="store_true", help="Force CLI REPL mode")
    p.add_argument("--choose", action="store_true",
                   help="Always show the launch menu, even if a preference exists")
    p.add_argument("--demo",   action="store_true",
                   help="Run run_demo() and exit (no UI launched)")
    return p


def main(argv: Optional[list[str]] = None) -> None:
    """Orchestrate detection → menu → health check → launch."""
    parser = _build_parser()
    # parse_known_args so we don't choke when called from cli.main which may
    # have already consumed its own argv
    args, _ = parser.parse_known_args(argv)

    # ── Demo mode ──────────────────────────────────────────────────────────────
    if args.demo:
        run_demo()
        return

    # ── Probe environment ──────────────────────────────────────────────────────
    caps = detect_capabilities()

    # ── Flag override ──────────────────────────────────────────────────────────
    forced_mode: Optional[str] = None
    if args.gui:
        forced_mode = "gui"
    elif args.tui:
        forced_mode = "tui"
    elif args.voice:
        forced_mode = "voice"
    elif args.cli:
        forced_mode = "cli"

    # ── Determine mode ─────────────────────────────────────────────────────────
    if forced_mode:
        mode = forced_mode
        if not caps.get(mode) and mode != "cli":
            print(f"  ⚠  Requested mode '{mode}' may not be fully available on this system.")
    elif args.choose or load_mode_preference() is None:
        mode = show_launch_menu(caps)
    else:
        mode = load_mode_preference()  # type: ignore[assignment]
        # Fall back gracefully if the saved mode is no longer available
        if not caps.get(mode):
            print(f"  ⚠  Saved mode '{mode}' not available — showing launch menu.")
            mode = show_launch_menu(caps)

    # ── Health check ───────────────────────────────────────────────────────────
    _print_warnings(_health_check())

    # ── Launch ─────────────────────────────────────────────────────────────────
    launch_mode(mode)


# ── Allow `python -m ui.launcher` ───────────────────────────────────────────
if __name__ == "__main__":
    main()
