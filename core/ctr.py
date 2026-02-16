from dataclasses import dataclass
from typing import Literal, Dict, Any
from pydantic import BaseModel, Field


# Define allowed task types
TaskType = Literal[
    "ORGANIZE_DOWNLOADS",
    "CREATE_PROJECT_SCAFFOLD", 
    "BULK_RENAME",
    "SEARCH_DOCUMENTS",
    "GENERATE_PASSWORD",      # ← ADD THIS
    "SCAN_PASSWORD_FIELDS",
]


@dataclass
class CTR:
    task_type: TaskType
    params: Dict[str, Any]
    version: str = "1.0"


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
    folder: str
    pattern: str = "date_slug"


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
    elif ctr.task_type == "SCAN_PASSWORD_FIELDS":
        ScanPasswordFields.model_validate(ctr_dict)
    else:
        raise ValueError(f"Unknown task_type: {ctr.task_type}")
