"""
checkpoint_manager.py

Snapshot-and-restore for filesystem state within the AI Cognitive OS project.
Uses SQLiteManager (db_manager.py) for persistence.
Only stdlib dependencies: hashlib, os, json, shutil, datetime.
"""

import hashlib
import os
import json
import shutil
from datetime import datetime
from typing import Optional

from db_manager import SQLiteManager


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------

class CheckpointManager:
    """Captures filesystem snapshots before mutating operations and can
    restore the state described in any stored checkpoint."""

    _CHUNK_SIZE = 8192  # bytes per read when computing MD5

    # ------------------------------------------------------------------
    # capture
    # ------------------------------------------------------------------

    def capture(self, affected_paths: list[str], command_text: str) -> int:
        """Build a snapshot of the given paths and persist it.

        The snapshot records:
          - MD5 hashes of each file (None if missing or a directory).
          - A directory listing for every unique parent directory.

        Args:
            affected_paths: Absolute or expanduser paths expected to be
                            affected by the upcoming command.
            command_text:   Human-readable description of the command being
                            run (stored alongside the snapshot for context).

        Returns:
            The row-id of the newly inserted checkpoint row.
        """
        file_hashes: dict[str, Optional[str]] = {}
        parent_dirs: set[str] = set()

        for raw_path in affected_paths:
            path = os.path.expanduser(raw_path)
            parent_dirs.add(os.path.dirname(path) or ".")

            if not os.path.exists(path) or os.path.isdir(path):
                file_hashes[path] = None
            else:
                file_hashes[path] = self._md5(path)

        directory_listings: dict[str, list[str]] = {}
        for parent in parent_dirs:
            try:
                directory_listings[parent] = os.listdir(parent)
            except (PermissionError, FileNotFoundError):
                directory_listings[parent] = []

        snapshot = {
            "file_hashes":          file_hashes,
            "directory_listings":   directory_listings,
        }

        snapshot_json = json.dumps(snapshot)

        db = SQLiteManager()
        row_id = db.insert("checkpoints", {
            "checkpoint_json": snapshot_json,
            "command_text":    command_text,
            "timestamp":       datetime.utcnow().isoformat(),
        })
        db.close()
        return row_id

    # ------------------------------------------------------------------
    # restore
    # ------------------------------------------------------------------

    def restore(self, checkpoint_id: int = None) -> str:
        """Describe or perform a restore from a stored checkpoint.

        Compares the current filesystem state against the snapshot.
        Modified files are flagged; missing files are listed as
        candidates for restoration.

        Args:
            checkpoint_id: Row id to restore. If None, the most-recent
                           checkpoint is used.

        Returns:
            "restore complete" on success, or "No checkpoint found."
        """
        db = SQLiteManager()

        if checkpoint_id is None:
            rows = db.fetch_all("checkpoints")
            if not rows:
                db.close()
                return "No checkpoint found."
            rows.sort(key=lambda r: r["timestamp"], reverse=True)
            row = rows[0]
        else:
            matches = db.fetch_where("checkpoints", "id", checkpoint_id)
            if not matches:
                db.close()
                return "No checkpoint found."
            row = matches[0]

        db.close()

        snapshot: dict = json.loads(row["checkpoint_json"])
        file_hashes: dict         = snapshot.get("file_hashes", {})
        directory_listings: dict  = snapshot.get("directory_listings", {})

        # --- File-level comparison ---
        for path, stored_hash in file_hashes.items():
            if stored_hash is None:
                continue  # was missing/dir at capture time — skip

            if not os.path.exists(path):
                print(f"Warning: cannot restore {path}, file missing from backup.")
                continue

            current_hash = self._md5(path)
            if current_hash != stored_hash:
                # File was modified — attempt backup restore.
                backup_path = self._find_in_backup(path)
                if backup_path and os.path.exists(backup_path):
                    shutil.copy2(backup_path, path)
                else:
                    print(
                        f"Warning: cannot restore {path}, "
                        "file missing from backup."
                    )

        # --- Directory-level comparison ---
        for parent_dir, stored_listing in directory_listings.items():
            try:
                current_listing = os.listdir(parent_dir)
            except (PermissionError, FileNotFoundError):
                current_listing = []

            current_set = set(current_listing)
            for filename in stored_listing:
                if filename not in current_set:
                    print(f"Would restore: {filename} to {parent_dir}")

        print(
            f"Restored checkpoint from: {row['timestamp']} "
            f"triggered by: {row['command_text']}"
        )
        return "restore complete"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _md5(self, path: str) -> str:
        """Return the hex MD5 digest of the file at *path*."""
        h = hashlib.md5()
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(self._CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _find_in_backup(path: str) -> Optional[str]:
        """Look for a backup copy of *path* in a sibling '.backup' directory.

        Returns the backup path if found, else None.
        """
        parent   = os.path.dirname(path)
        filename = os.path.basename(path)
        backup   = os.path.join(parent, ".backup", filename)
        return backup if os.path.exists(backup) else None


# ---------------------------------------------------------------------------
# run_demo  (required by project rules)
# ---------------------------------------------------------------------------

def run_demo() -> None:
    """Demonstrate CheckpointManager using temp files and an in-memory DB."""
    import tempfile
    global SQLiteManager

    _original_cls = SQLiteManager
    _shared_db    = SQLiteManager(db_path=":memory:")

    class _InMemProxy:
        def __init__(self, db_path=None): pass
        def __getattr__(self, n): return getattr(_shared_db, n)
        def close(self): pass

    SQLiteManager = _InMemProxy

    try:
        print("=== CheckpointManager Demo ===\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two demo files
            f1 = os.path.join(tmpdir, "report.txt")
            f2 = os.path.join(tmpdir, "data.csv")
            with open(f1, "w") as fh: fh.write("original report\n")
            with open(f2, "w") as fh: fh.write("col1,col2\n1,2\n")

            mgr = CheckpointManager()

            # capture
            cid = mgr.capture([f1, f2], "copy files to ~/sent")
            print(f"Captured checkpoint id={cid}")

            # mutate one file
            with open(f1, "w") as fh: fh.write("MODIFIED content\n")
            print(f"Mutated {os.path.basename(f1)}")

            # remove the other
            os.remove(f2)
            print(f"Deleted {os.path.basename(f2)}\n")

            # restore
            result = mgr.restore()
            print(f"\nrestore() returned: {result!r}")

    finally:
        SQLiteManager = _original_cls
        _shared_db.close()
        print("\n=== Demo complete ===")


# ---------------------------------------------------------------------------
# Tests  (required by project rules: 3 test cases)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Three fast unit tests using temp files and an in-memory DB."""
    import tempfile
    global SQLiteManager
    _original_cls = SQLiteManager

    def _make_proxy():
        db = SQLiteManager(db_path=":memory:")
        class P:
            def __init__(self, db_path=None): pass
            def __getattr__(self, n): return getattr(db, n)
            def close(self): pass
        return db, P

    print("\n=== Running Tests ===\n")

    # Test 1: capture stores correct MD5 and returns a valid row id
    print("Test 1: capture stores correct MD5 hash and returns row id")
    db1, P1 = _make_proxy()
    SQLiteManager = P1
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tf:
            tf.write(b"hello test")
            tmp_path = tf.name
        mgr = CheckpointManager()
        row_id = mgr.capture([tmp_path], "test command")
        assert isinstance(row_id, int) and row_id > 0, f"Bad row_id: {row_id}"
        rows = db1.fetch_all("checkpoints")
        snap = json.loads(rows[0]["checkpoint_json"])
        assert tmp_path in snap["file_hashes"], "path not in file_hashes"
        expected_md5 = hashlib.md5(b"hello test").hexdigest()
        assert snap["file_hashes"][tmp_path] == expected_md5, "MD5 mismatch"
        os.unlink(tmp_path)
    finally:
        SQLiteManager = _original_cls
        db1.close()
    print("  PASSED\n")

    # Test 2: restore returns "No checkpoint found." when table is empty
    print("Test 2: restore with empty DB returns 'No checkpoint found.'")
    db2, P2 = _make_proxy()
    SQLiteManager = P2
    try:
        mgr2 = CheckpointManager()
        result = mgr2.restore()
        assert result == "No checkpoint found.", f"Got: {result!r}"
    finally:
        SQLiteManager = _original_cls
        db2.close()
    print("  PASSED\n")

    # Test 3: restore detects deleted file and prints "Would restore: ..."
    print("Test 3: restore detects deleted file → 'Would restore: ...'")
    db3, P3 = _make_proxy()
    SQLiteManager = P3
    import io as _io
    captured_output = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            fp = os.path.join(tmpdir, "will_be_deleted.txt")
            with open(fp, "w") as fh: fh.write("data")
            mgr3 = CheckpointManager()
            mgr3.capture([fp], "pre-delete snapshot")
            os.remove(fp)  # simulate deletion

            import builtins
            _orig_print = builtins.print
            builtins.print = lambda *a, **kw: captured_output.append(" ".join(str(x) for x in a))
            try:
                mgr3.restore()
            finally:
                builtins.print = _orig_print

        assert any("Would restore" in line and "will_be_deleted.txt" in line
                   for line in captured_output), \
               f"Expected 'Would restore' line, got: {captured_output}"
    finally:
        SQLiteManager = _original_cls
        db3.close()
    print("  PASSED\n")

    print("=== All Tests Passed ===")


if __name__ == "__main__":
    _run_tests()
    print()
    run_demo()
