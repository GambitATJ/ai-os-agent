"""
AI-OS Global Hotkey Daemon
--------------------------
Listens for a configurable hotkey (default: Ctrl+Alt+V).

On trigger:
  - Detects the currently focused window title / app name
  - If vault has a password for that app → copies to clipboard
  - If not → generates a secure password, stores in vault, copies to clipboard
  - Shows a desktop notification either way

Run with:
    python hotkey_daemon.py
    python hotkey_daemon.py --key "<ctrl>+<alt>+v"

Or via CLI:
    python -m cli.main hotkey
"""

import os
import re
import sys
import time
import signal
import logging
import warnings
import argparse
import subprocess
import threading

# ── Silence ML noise we don't need in the daemon ─────────────────────────────
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# ── Import vault after silencing ──────────────────────────────────────────────
from pathlib import Path
from features.vault import PasswordVault

logging.disable(logging.NOTSET)

_vault = PasswordVault()
_HOTKEY_DEFAULT = "<ctrl>+<alt>+v"


# ─────────────────────────────────────────────────────────────────────────────
# Window detection
# ─────────────────────────────────────────────────────────────────────────────

def get_focused_app() -> str:
    """
    Return a clean, lowercase app name for the currently focused window.
    Uses xdotool (X11) or falls back to empty string.
    """
    try:
        win_id = subprocess.check_output(
            ["xdotool", "getactivewindow"], stderr=subprocess.DEVNULL
        ).decode().strip()
        win_name = subprocess.check_output(
            ["xdotool", "getwindowname", win_id], stderr=subprocess.DEVNULL
        ).decode().strip().lower()
    except Exception:
        return ""

    # Heuristically extract app name from window title
    # e.g. "Spotify - Music" → "spotify"
    # e.g. "Discord | #general" → "discord"
    # e.g. "GitHub - Google Chrome" → "github"
    known_apps = [
        "spotify", "discord", "steam", "slack", "zoom", "teams",
        "firefox", "chrome", "chromium", "code", "vscode",
        "github", "gitlab", "figma", "notion", "telegram",
        "thunderbird", "gimp", "inkscape", "vlc", "obs",
    ]
    for app in known_apps:
        if app in win_name:
            return app

    # Fallback: take first word before common separators
    cleaned = re.split(r"[\s\-–—|·:]+", win_name)[0].strip()
    return cleaned if cleaned else win_name.split()[0] if win_name else ""


# ─────────────────────────────────────────────────────────────────────────────
# Desktop notification
# ─────────────────────────────────────────────────────────────────────────────

def notify(title: str, body: str, icon: str = "dialog-password") -> None:
    """Send a desktop notification via notify-send (non-blocking)."""
    try:
        subprocess.Popen(
            ["notify-send", "-i", icon, "-t", "3000", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # notify-send not installed — silent fallback


# ─────────────────────────────────────────────────────────────────────────────
# Core hotkey action
# ─────────────────────────────────────────────────────────────────────────────

def handle_hotkey(app_name: str | None = None) -> None:
    """
    Called when the hotkey fires.
    Detects focused app (or uses supplied app_name), checks vault, acts.
    Runs in a separate thread so the listener never blocks.
    """
    import pyperclip

    if not app_name:
        app_name = get_focused_app()

    if not app_name:
        notify("AI-OS Vault", "⚠️ Could not detect focused app", "dialog-warning")
        print("[HOTKEY] Could not detect focused app")
        return

    print(f"[HOTKEY] Triggered for app: '{app_name}'")

    # Check vault — direct label first, then legacy lookup
    label = app_name.lower().strip()
    password = _vault.get_password(label)

    if not password:
        legacy = _vault.detect_app_login(app_name)
        if legacy:
            password = _vault.get_password(legacy)
            if password:
                label = legacy

    if password:
        pyperclip.copy(password)
        msg = f"Password for '{app_name}' copied to clipboard ✅"
        print(f"[HOTKEY] {msg}")
        notify("AI-OS Vault", msg)
    else:
        # Generate a new password
        print(f"[HOTKEY] No password found for '{app_name}' — generating...")
        pw, strength = _vault.generate_password(label)
        pyperclip.copy(pw)
        msg = f"New password generated for '{app_name}' & copied to clipboard 🔑"
        print(f"[HOTKEY] {msg}  (strength: {strength}/100)")
        notify("AI-OS Vault", msg)


# ─────────────────────────────────────────────────────────────────────────────
# Daemon
# ─────────────────────────────────────────────────────────────────────────────

def run_daemon(hotkey: str = _HOTKEY_DEFAULT) -> None:
    """Start the global hotkey listener. Blocks until Ctrl+C."""
    try:
        from pynput import keyboard
    except ImportError:
        print("❌ pynput is required for the hotkey daemon.")
        print("   Install with:  pip install pynput")
        sys.exit(1)

    def _fire():
        # Run in a thread so the listener loop never stalls
        t = threading.Thread(target=handle_hotkey, daemon=True)
        t.start()

    print(f"🔑 AI-OS Vault Daemon started")
    print(f"   Hotkey : {hotkey}")
    print(f"   Vault  : {Path.home() / '.aios' / 'vault.enc'}")
    print(f"   Press {hotkey} while any window is focused to copy its password.")
    print(f"   Ctrl+C to stop.\n")

    with keyboard.GlobalHotKeys({hotkey: _fire}) as h:
        # Keep alive; handle Ctrl+C gracefully
        try:
            h.join()
        except KeyboardInterrupt:
            print("\n[HOTKEY] Daemon stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (standalone usage)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-OS Global Hotkey Daemon")
    parser.add_argument(
        "--key",
        default=_HOTKEY_DEFAULT,
        help=f"Hotkey combination (default: {_HOTKEY_DEFAULT})",
    )
    args = parser.parse_args()
    run_daemon(args.key)
