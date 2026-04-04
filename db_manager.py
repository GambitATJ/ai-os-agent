"""
db_manager.py

Structured persistent state for the AI Cognitive OS project.
Uses only sqlite3 from the Python standard library.
Database file: session_memory.db (project root).
"""

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_memory.db")

ALLOWED_EXECUTION_STATUSES = {"complete", "interrupted", "failed"}


class SQLiteManager:
    """Manages all SQLite interactions for the AI Cognitive OS project.

    Tables created on instantiation (if they do not already exist):
    - session_memory
    - corrections
    - checkpoints
    - user_commands
    - performance_log
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row  # rows accessible by column name
        self._create_tables()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cursor(self) -> sqlite3.Cursor:
        return self._conn.cursor()

    def _create_tables(self) -> None:
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS session_memory (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                ctr_json                TEXT    NOT NULL,
                timestamp               TEXT    NOT NULL,
                execution_status        TEXT    NOT NULL
                                            CHECK(execution_status IN ('complete', 'interrupted', 'failed')),
                natural_language_summary TEXT   NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS corrections (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                command_embedding BLOB    NOT NULL,
                correct_intent    TEXT    NOT NULL,
                timestamp         TEXT    NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_json TEXT    NOT NULL,
                command_text    TEXT    NOT NULL,
                timestamp       TEXT    NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_commands (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                command_name TEXT    NOT NULL UNIQUE,
                ctr_json     TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS performance_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name     TEXT    NOT NULL,
                estimated_seconds REAL,
                actual_seconds   REAL,
                file_count       INTEGER,
                step_count       INTEGER,
                timestamp        TEXT    NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS command_paraphrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_name TEXT NOT NULL,
                phrase TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
        ]
        cursor = self._cursor()
        for stmt in ddl_statements:
            cursor.execute(stmt)
        self._conn.commit()

    @staticmethod
    def _now_iso() -> str:
        """Return the current UTC time as an ISO 8601 string."""
        return datetime.utcnow().isoformat()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def insert(self, table_name: str, data_dict: dict) -> int:
        """Insert a row into *table_name* using the key-value pairs in *data_dict*.

        Returns the rowid of the newly inserted row.
        Raises ValueError for invalid execution_status in session_memory.
        """
        if table_name == "session_memory":
            status = data_dict.get("execution_status", "")
            if status not in ALLOWED_EXECUTION_STATUSES:
                raise ValueError(
                    f"Invalid execution_status '{status}'. "
                    f"Allowed: {ALLOWED_EXECUTION_STATUSES}"
                )

        columns = ", ".join(data_dict.keys())
        placeholders = ", ".join(["?"] * len(data_dict))
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        cursor = self._cursor()
        cursor.execute(sql, list(data_dict.values()))
        self._conn.commit()
        return cursor.lastrowid

    def fetch_all(self, table_name: str) -> list[dict]:
        """Return every row in *table_name* as a list of dicts."""
        sql = f"SELECT * FROM {table_name}"
        cursor = self._cursor()
        cursor.execute(sql)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_where(self, table_name: str, column: str, value) -> list[dict]:
        """Return rows from *table_name* where *column* equals *value*."""
        sql = f"SELECT * FROM {table_name} WHERE {column} = ?"
        cursor = self._cursor()
        cursor.execute(sql, (value,))
        return [dict(row) for row in cursor.fetchall()]

    def delete(self, table_name: str, row_id: int) -> int:
        """Delete the row with the given *row_id* from *table_name*.

        Returns the number of rows deleted (0 or 1).
        """
        sql = f"DELETE FROM {table_name} WHERE id = ?"
        cursor = self._cursor()
        cursor.execute(sql, (row_id,))
        self._conn.commit()
        return cursor.rowcount

    def delete_where(self, table_name: str, column: str, value: str) -> int:
        """
        Deletes all rows from table_name where column = value.
        Returns the number of rows deleted.
        """
        conn = self._conn
        cursor = conn.execute(
            f"DELETE FROM {table_name} WHERE {column} = ?",
            (value,)
        )
        conn.commit()
        return cursor.rowcount

    def list_user_commands(self) -> list[dict]:
        """
        Returns all rows from user_commands as a list of dicts
        with keys: id, command_name, created_at.
        Does not return ctr_json (too long to display).
        """
        conn = self._conn
        cursor = conn.execute(
            "SELECT id, command_name, created_at FROM user_commands ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        return [{"id": r[0], "command_name": r[1], "created_at": r[2]} for r in rows]

    def fetch_recent(self, table_name: str, hours: int = 24) -> list[dict]:
        """Return rows from *table_name* whose timestamp column is within the
        last *hours* hours (UTC).

        Assumes the timestamp column stores ISO 8601 strings produced by
        datetime.utcnow().isoformat().
        """
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        # All tables use 'timestamp' except user_commands which uses 'created_at'.
        ts_col = "created_at" if table_name == "user_commands" else "timestamp"
        sql = f"SELECT * FROM {table_name} WHERE {ts_col} >= ?"
        cursor = self._cursor()
        cursor.execute(sql, (cutoff,))
        return [dict(row) for row in cursor.fetchall()]

    def set_preference(self, key: str, value: str) -> None:
        """Upsert a key-value pair in the *user_preferences* table."""
        sql = (
            "INSERT INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at"
        )
        cursor = self._cursor()
        cursor.execute(sql, (key, value, self._now_iso()))
        self._conn.commit()

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        """Return the stored value for *key*, or *default* if not found."""
        sql = "SELECT value FROM user_preferences WHERE key = ?"
        cursor = self._cursor()
        cursor.execute(sql, (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# ----------------------------------------------------------------------
# Demo  (required by project rules: every module must expose run_demo())
# ----------------------------------------------------------------------

def run_demo() -> None:
    """Demonstrate SQLiteManager usage with example data.

    Uses an in-memory database so the demo is self-contained and leaves
    no files on disk.
    """
    import json

    print("=== SQLiteManager Demo ===\n")

    manager = SQLiteManager(db_path=":memory:")

    # ---- session_memory ----
    sm_id = manager.insert("session_memory", {
        "ctr_json": json.dumps({"action": "organize_downloads", "params": {}}),
        "timestamp": manager._now_iso(),
        "execution_status": "complete",
        "natural_language_summary": "Organized 12 files in ~/Downloads into sub-folders.",
    })
    print(f"[session_memory] Inserted row id={sm_id}")
    rows = manager.fetch_all("session_memory")
    print(f"[session_memory] fetch_all → {len(rows)} row(s): {rows}\n")

    # ---- corrections ----
    import struct
    dummy_embedding = struct.pack("f" * 4, 0.1, 0.2, 0.3, 0.4)
    c_id = manager.insert("corrections", {
        "command_embedding": dummy_embedding,
        "correct_intent":    "organize_downloads",
        "timestamp":         manager._now_iso(),
    })
    print(f"[corrections] Inserted row id={c_id}")
    print(f"[corrections] fetch_where intent='organize_downloads' → "
          f"{manager.fetch_where('corrections', 'correct_intent', 'organize_downloads')}\n")

    # ---- checkpoints ----
    cp_id = manager.insert("checkpoints", {
        "checkpoint_json": json.dumps({"step": 1, "files_moved": []}),
        "command_text":    "organize downloads",
        "timestamp":       manager._now_iso(),
    })
    print(f"[checkpoints] Inserted row id={cp_id}")
    deleted = manager.delete("checkpoints", cp_id)
    print(f"[checkpoints] Deleted row id={cp_id}: {deleted} row(s) removed\n")

    # ---- user_commands ----
    uc_id = manager.insert("user_commands", {
        "command_name": "organize_downloads",
        "ctr_json":     json.dumps({"action": "organize_downloads"}),
        "created_at":   manager._now_iso(),
    })
    print(f"[user_commands] Inserted row id={uc_id}")
    print(f"[user_commands] fetch_recent(hours=1) → "
          f"{manager.fetch_recent('user_commands', hours=1)}\n")

    # ---- performance_log ----
    pl_id = manager.insert("performance_log", {
        "feature_name":      "organize_downloads",
        "estimated_seconds": 5.0,
        "actual_seconds":    3.8,
        "file_count":        12,
        "step_count":        4,
        "timestamp":         manager._now_iso(),
    })
    print(f"[performance_log] Inserted row id={pl_id}")
    print(f"[performance_log] fetch_recent(hours=24) → "
          f"{manager.fetch_recent('performance_log', hours=24)}\n")

    manager.close()
    print("=== Demo complete ===")


# ----------------------------------------------------------------------
# Test cases  (required by project rules: 3 test cases per module)
# ----------------------------------------------------------------------

def _run_tests() -> None:
    """Three self-contained test cases for SQLiteManager."""
    import json

    print("\n=== Running Tests ===\n")

    # Test 1: insert and fetch_all for session_memory
    print("Test 1: insert & fetch_all")
    with SQLiteManager(db_path=":memory:") as db:
        db.insert("session_memory", {
            "ctr_json": '{"action":"test"}',
            "timestamp": db._now_iso(),
            "execution_status": "complete",
            "natural_language_summary": "Test summary.",
        })
        rows = db.fetch_all("session_memory")
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
        assert rows[0]["execution_status"] == "complete"
    print("  PASSED\n")

    # Test 2: fetch_where and delete
    print("Test 2: fetch_where & delete")
    with SQLiteManager(db_path=":memory:") as db:
        rid = db.insert("checkpoints", {
            "checkpoint_json": '{"step":1}',
            "command_text": "move files",
            "timestamp": db._now_iso(),
        })
        found = db.fetch_where("checkpoints", "command_text", "move files")
        assert len(found) == 1, f"Expected 1 row, got {len(found)}"
        deleted = db.delete("checkpoints", rid)
        assert deleted == 1, f"Expected 1 deletion, got {deleted}"
        assert db.fetch_all("checkpoints") == []
    print("  PASSED\n")

    # Test 3: invalid execution_status raises ValueError
    print("Test 3: invalid execution_status raises ValueError")
    with SQLiteManager(db_path=":memory:") as db:
        try:
            db.insert("session_memory", {
                "ctr_json": '{}',
                "timestamp": db._now_iso(),
                "execution_status": "unknown_status",
                "natural_language_summary": "Should fail.",
            })
            assert False, "Expected ValueError was not raised"
        except ValueError as exc:
            assert "unknown_status" in str(exc)
    print("  PASSED\n")

    print("=== All Tests Passed ===")


if __name__ == "__main__":
    run_demo()
    _run_tests()
