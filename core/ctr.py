import json
import dataclasses
from dataclasses import dataclass
from typing import Literal, Dict, Any, Optional, List
from pydantic import BaseModel, Field


# Define allowed task types
TaskType = Literal[
    "ORGANIZE_DOWNLOADS",
    "CREATE_PROJECT_SCAFFOLD",
    "BULK_RENAME",
    "SEARCH_DOCUMENTS",
    "GENERATE_PASSWORD",
    "SCAN_PASSWORD_FIELDS",
    "AUTOFILL_APP",
    "FIND_RECEIPTS",
    "SHELL_PLAN",
    "SAVED_COMMAND"
]


@dataclass
class CTR:
    task_type: TaskType
    params: Dict[str, Any]
    version: str = "1.0"

    def to_json(self) -> str:
        """Serialize the entire CTR dataclass to a JSON string.

        All fields are included. Any field that is not JSON-serializable
        by default is converted to its string representation.
        """
        def _safe(obj):
            """Recursively make *obj* JSON-serializable."""
            if isinstance(obj, dict):
                return {k: _safe(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe(v) for v in obj]
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)

        raw = dataclasses.asdict(self)
        safe_dict = {k: _safe(v) for k, v in raw.items()}
        return json.dumps(safe_dict)

    @classmethod
    def from_json(cls, json_str: str) -> 'CTR':
        """Deserialize a JSON string back into a CTR dataclass instance.

        Reconstructs all fields to their original types as defined in the
        dataclass (task_type: str, params: dict, version: str).
        """
        data = json.loads(json_str)
        return cls(
            task_type=str(data["task_type"]),
            params=dict(data.get("params", {})),
            version=str(data.get("version", "1.0")),
        )


# Pydantic models for validation (more robust)
class OrganizeDownloads(BaseModel):
    task_type: Literal["ORGANIZE_DOWNLOADS"] = "ORGANIZE_DOWNLOADS"
    source_dir: str = Field(..., description="Directory to organize")


class CreateProject(BaseModel):
    task_type: Literal["CREATE_PROJECT_SCAFFOLD"] = "CREATE_PROJECT_SCAFFOLD"
    name: str
    location: str
    project_type: str = "python_project"


class BulkRename(BaseModel):
    task_type: Literal["BULK_RENAME"] = "BULK_RENAME"
    source_dir: str
    pattern: str = "date_slug"

class FindReceipts(BaseModel):
    task_type: Literal["FIND_RECEIPTS"] = "FIND_RECEIPTS"
    source_dir: str
    query: str = "receipt"
    export_dir: Optional[str] = None

class GenerateTemplate(BaseModel):
    task_type: Literal["GENERATE_TEMPLATE"] = "GENERATE_TEMPLATE"
    template: str
    output: str


class SearchDocuments(BaseModel):
    task_type: Literal["SEARCH_DOCUMENTS"] = "SEARCH_DOCUMENTS"
    scope: str
class GeneratePassword(BaseModel):
    task_type: Literal["GENERATE_PASSWORD"] = "GENERATE_PASSWORD"
    label: str
    length: int = Field(16, ge=8, le=128)
    uppercase: bool = True
    lowercase: bool = True
    digits: bool = True
    symbols: bool = True


class ScanPasswordFields(BaseModel):
    task_type: Literal["SCAN_PASSWORD_FIELDS"] = "SCAN_PASSWORD_FIELDS"
    scope: str


class AutofillApp(BaseModel):
    task_type: Literal["AUTOFILL_APP"] = "AUTOFILL_APP"
    app_name: str
    
# class BulkRename(BaseModel):
#     task_type: Literal["BULK_RENAME"] = "BULK_RENAME"
#     source_dir: str
#     pattern: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")


class ShellCommand(BaseModel):
    cmd: str
    explanation: str
    risk_level: str  # "low", "medium", or "critical"
    risk_reason: Optional[str] = None

class ShellPlan(BaseModel):
    task_type: Literal["SHELL_PLAN"] = "SHELL_PLAN"
    intent_description: str
    commands: List[ShellCommand]
    saveable: bool = True

class SavedCommand(BaseModel):
    task_type: Literal["SAVED_COMMAND"] = "SAVED_COMMAND"
    command_name: str
    original_ctr_json: str

def validate_ctr(ctr: CTR) -> None:
    """Validate CTR and convert to Pydantic model for type checking."""
    
    ctr_dict = {
        "task_type": ctr.task_type,
        **ctr.params
    }
    
    if ctr.task_type == "ORGANIZE_DOWNLOADS":
        OrganizeDownloads.model_validate(ctr_dict)
    elif ctr.task_type == "CREATE_PROJECT_SCAFFOLD":
        CreateProject.model_validate(ctr_dict)
    elif ctr.task_type == "BULK_RENAME":
        BulkRename.model_validate(ctr_dict)
    elif ctr.task_type == "SEARCH_DOCUMENTS":
        SearchDocuments.model_validate(ctr_dict)
    elif ctr.task_type == "GENERATE_PASSWORD":
        GeneratePassword.model_validate(ctr_dict)
    elif ctr.task_type == "AUTOFILL_APP":
        AutofillApp.model_validate(ctr_dict)
    elif ctr.task_type == "SCAN_PASSWORD_FIELDS":
        ScanPasswordFields.model_validate(ctr_dict)
    elif ctr.task_type == "BULK_RENAME":
        BulkRename.model_validate(ctr_dict)
    elif ctr.task_type == "FIND_RECEIPTS":
        FindReceipts.model_validate(ctr_dict)
    elif ctr.task_type == "SHELL_PLAN":
        ShellPlan.model_validate(ctr_dict)
    elif ctr.task_type == "SAVED_COMMAND":
        SavedCommand.model_validate(ctr_dict)
    else:
        raise ValueError(f"Unknown task_type: {ctr.task_type}")
