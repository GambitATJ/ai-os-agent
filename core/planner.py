import os
from typing import List
from .ctr import CTR
from .steps import Step


def plan(ctr: CTR) -> List[Step]:
    """Main planner dispatcher."""
    if ctr.task_type == "ORGANIZE_DOWNLOADS":
        return _plan_organize_downloads(ctr.params)
    elif ctr.task_type == "CREATE_PROJECT_SCAFFOLD":
        return _plan_create_project(ctr.params)
    else:
        raise NotImplementedError(f"No planner for {ctr.task_type}")


def _plan_organize_downloads(params: dict) -> List[Step]:
    """Plan to organize downloads folder."""
    source_dir = os.path.expanduser(params.get("source_dir", "~/Downloads"))
    steps = []
    
    # File categories by extension
    categories = {
        ".pdf": "Documents",
        ".doc": "Documents", 
        ".docx": "Documents",
        ".txt": "Documents",
        ".jpg": "Images",
        ".jpeg": "Images",
        ".png": "Images",
        ".zip": "Archives",
        ".tar": "Archives",
        ".gz": "Archives",
        ".deb": "Installers",
    }
    
    for entry in os.scandir(source_dir):
        if entry.is_file():
            ext = os.path.splitext(entry.name)[1].lower()
            category = categories.get(ext, "Other")
            
            dst_dir = os.path.join(source_dir, category)
            dst_file = os.path.join(dst_dir, entry.name)
            
            # Create category dir first
            steps.append(Step(step_type="CREATE_DIR", args={"path": dst_dir}))
            # Then move file
            steps.append(Step(step_type="MOVE_FILE", args={
                "src": entry.path, 
                "dst": dst_file
            }))
    
    return steps


def _plan_create_project(params: dict) -> List[Step]:
    """Plan basic project scaffold."""
    name = params["name"]
    location = os.path.expanduser(params["location"])
    project_type = params.get("project_type", "python_project")
    
    project_path = os.path.join(location, name)
    
    steps = []
    
    # Create main project dir
    steps.append(Step(step_type="CREATE_DIR", args={"path": project_path}))
    
    if project_type == "python_project":
        # Python-specific structure
        steps.append(Step(step_type="CREATE_DIR", args={"path": os.path.join(project_path, "src")}))
        steps.append(Step(step_type="CREATE_DIR", args={"path": os.path.join(project_path, "tests")}))
        steps.append(Step(step_type="CREATE_DIR", args={"path": os.path.join(project_path, "docs")}))
    
    return steps
