import re
import os
from typing import Dict, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from core.ctr import CTR

# --------------------------------------------------
# 1. Load embedding model (singleton)
# --------------------------------------------------

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# --------------------------------------------------
# 2. Intent Examples
# --------------------------------------------------

INTENT_EXAMPLES = {
    "ORGANIZE_DOWNLOADS": [
        "clean my downloads",
        "organize downloads folder",
        "sort files in downloads"
    ],
    "CREATE_PROJECT_SCAFFOLD": [
        "create a new project",
        "start a python project",
        "initialize project"
    ],
    "AUTOFILL_APP": [
        "autofill spotify",
        "fill spotify password",
        "copy spotify password",
        "login to spotify",
        "use spotify account",
        "get spotify password"
    ],
    "FIND_RECEIPTS": [
        "find receipt",
        "find receipts",
        "search receipt",
        "search receipts",
        "find coffee receipt",
        "search for document",
        "look up purchase document"
    ],
    "GENERATE_PASSWORD": [
        "create password",
        "generate secure password",
        "make password for spotify"
    ],
    "BULK_RENAME": [
        "rename files in folder",
        "bulk rename photos",
        "rename all files"
    ],
    "SCAN_PASSWORD_FIELDS": [
        "scan for password fields",
        "check folder for passwords"
    ]
}


# --------------------------------------------------
# 3. Precompute embeddings
# --------------------------------------------------

_INTENT_EMBEDDINGS = None

def build_intent_embeddings():
    global _INTENT_EMBEDDINGS
    model = get_model()

    _INTENT_EMBEDDINGS = {}
    for task, examples in INTENT_EXAMPLES.items():
        _INTENT_EMBEDDINGS[task] = model.encode(examples)

def classify_intent(text: str) -> Tuple[str, float]:
    if _INTENT_EMBEDDINGS is None:
        build_intent_embeddings()

    model = get_model()
    query_embedding = model.encode([text])[0]

    best_task = None
    best_score = -1

    for task, example_embeddings in _INTENT_EMBEDDINGS.items():
        scores = np.dot(example_embeddings, query_embedding)
        max_score = np.max(scores)

        if max_score > best_score:
            best_score = max_score
            best_task = task

    return best_task, float(best_score)


# --------------------------------------------------
# 4. Parameter Extraction
# --------------------------------------------------

def extract_paths(text: str):
    """
    Extract:
    - ~/folder
    - /absolute/path
    - relative_folder
    """
    path_pattern = r"(~\/[^\s]+|\/[^\s]+|\b[a-zA-Z0-9_\-]+\/?[a-zA-Z0-9_\-]*)"
    return re.findall(path_pattern, text)


def extract_query_word(text: str):
    """
    Extract the actual search term from:
    - find ipad
    - find ipad in folder
    - search ipad
    - find 'ipad pro'
    """
    text_lower = text.lower()

    # 1️⃣ Quoted text
    quoted = re.findall(r'"([^"]+)"', text_lower)
    if quoted:
        return quoted[0]

    # 2️⃣ Remove structural words
    cleaned = re.sub(
        r"(find|search|look|lookup|receipts?|receipt|documents?|document|for|in\s+[^\s]+|copy to\s+[^\s]+)",
        "",
        text_lower
    )

    cleaned = cleaned.strip()

    if cleaned:
        return cleaned

    return ""


def extract_app_name(text: str):
    """
    For vault commands like:
    - autofill spotify
    - login to spotify
    """
    text = text.lower()
    words = text.split()

    # Usually app is last word
    return words[-1]


def build_ctr(task: str, text: str) -> CTR:

    paths = extract_paths(text)

    # --------------------------------------------------

    if task == "ORGANIZE_DOWNLOADS":
        source = paths[0] if paths else "~/Downloads"
        return CTR(
            task_type="ORGANIZE_DOWNLOADS",
            params={"source_dir": source}
        )

    # --------------------------------------------------

    if task == "CREATE_PROJECT_SCAFFOLD":
        words = text.split()
        name = words[-1]
        return CTR(
            task_type="CREATE_PROJECT_SCAFFOLD",
            params={
                "name": name,
                "location": "~/Projects",
                "project_type": "python_project"
            }
        )

    # --------------------------------------------------

    if task == "FIND_RECEIPTS":
        source = None
        export = None

        # Detect source after "in ..."
        match_in = re.search(r'in\s+([^\s]+)', text)
        if match_in:
            source = match_in.group(1)

        # Detect export after "copy to ..."
        match_copy = re.search(r'copy to\s+([^\s]+)', text)
        if match_copy:
            export = match_copy.group(1)

        query = extract_query_word(text)

        return CTR(
            task_type="FIND_RECEIPTS",
            params={
                "source_dir": source,
                "query": query,
                "export_dir": export
            }
        )

    # --------------------------------------------------

    if task == "GENERATE_PASSWORD":
        label = extract_app_name(text)
        return CTR(
            task_type="GENERATE_PASSWORD",
            params={"label": label}
        )

    # --------------------------------------------------

    if task == "AUTOFILL_APP":
        app_name = extract_app_name(text)
        return CTR(
            task_type="AUTOFILL_APP",
            params={"app_name": app_name}
        )

    # --------------------------------------------------

    if task == "BULK_RENAME":
        source = paths[0] if paths else "."
        return CTR(
            task_type="BULK_RENAME",
            params={
                "source_dir": source,
                "pattern": "date_slug"
            }
        )

    # --------------------------------------------------

    if task == "SCAN_PASSWORD_FIELDS":
        scope = paths[0] if paths else "."
        return CTR(
            task_type="SCAN_PASSWORD_FIELDS",
            params={"scope": scope}
        )

    raise ValueError(f"Unknown task: {task}")


# --------------------------------------------------
# 5. Public Router
# --------------------------------------------------

def route(text: str) -> CTR:
    task, confidence = classify_intent(text)

    if confidence < 0.25:
        raise ValueError(f"Low confidence intent detection ({confidence:.2f})")

    return build_ctr(task, text)
