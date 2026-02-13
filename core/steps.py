from dataclasses import dataclass
from typing import Literal, Dict, Any


StepType = Literal["CREATE_DIR", "MOVE_FILE", "RENAME_FILE"]


@dataclass
class Step:
    step_type: StepType
    args: Dict[str, Any]
