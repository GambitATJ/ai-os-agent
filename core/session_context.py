"""
Session context stores the result of the last executed
command so subsequent commands can reference it naturally.
Examples:
  "find the ipad receipt" → stores found file path
  "mail it to abhijit" → resolves "it" to found file
  "send that to mark" → resolves "that" to last file
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import datetime


@dataclass
class SessionContext:
    last_task_type: Optional[str] = None
    last_result_path: Optional[str] = None
    last_result_paths: list = field(default_factory=list)
    last_query: Optional[str] = None
    last_intent_description: Optional[str] = None
    timestamp: Optional[str] = None

    def set_result(self, task_type: str,
                   result_path: str = None,
                   result_paths: list = None,
                   query: str = None,
                   description: str = None):
        self.last_task_type = task_type
        self.last_result_path = result_path
        self.last_result_paths = result_paths or []
        self.last_query = query
        self.last_intent_description = description
        self.timestamp = datetime.datetime.utcnow().isoformat()

    def clear(self):
        self.__init__()

    def has_recent_file(self) -> bool:
        return bool(self.last_result_path or
                    self.last_result_paths)

    def get_primary_file(self) -> Optional[str]:
        if self.last_result_path:
            return self.last_result_path
        if self.last_result_paths:
            return self.last_result_paths[0]
        return None


# Module-level singleton — shared across the pipeline
_context = SessionContext()


def get_context() -> SessionContext:
    return _context


def update_context(task_type: str,
                   result_path: str = None,
                   result_paths: list = None,
                   query: str = None,
                   description: str = None):
    _context.set_result(
        task_type=task_type,
        result_path=result_path,
        result_paths=result_paths,
        query=query,
        description=description
    )


def clear_context():
    _context.clear()
