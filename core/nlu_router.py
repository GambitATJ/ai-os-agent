import re
import os
import csv
import sys
from datetime import datetime
from typing import Dict, Tuple, List
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_manager import SQLiteManager
from sentence_transformers import SentenceTransformer
from core.ctr import CTR

# --------------------------------------------------
# Ambiguity threshold: if the top-2 intent scores differ by less
# than this value the command is considered ambiguous and the user
# is asked to disambiguate.
CONFIDENCE_THRESHOLD = 0.15

# Path to the online-adaptation log (project root)
_ADAPTATION_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "adaptation_log.csv",
)

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
        "get spotify password",
        "paste password for discord",
        "get my discord password",
        "autofill discord",
        "copy password for github",
        "fill in my password for steam"
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
        "make password for spotify",
        "generate password for github",
        "create a new password for discord",
        "new password for steam",
        "make me a password",
        "generate password"
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

    # Collect (intent, best_score_for_intent) across all intents
    all_scores: List[Tuple[str, float]] = []
    for task, example_embeddings in _INTENT_EMBEDDINGS.items():
        scores = np.dot(example_embeddings, query_embedding)
        all_scores.append((task, float(np.max(scores))))

    # Sort descending by score
    all_scores.sort(key=lambda x: x[1], reverse=True)

    best_task, best_score = all_scores[0]

    # ------------------------------------------------------------------
    # Ambiguity resolution: if the top-2 scores are too close, ask user.
    # ------------------------------------------------------------------
    if len(all_scores) >= 2:
        intent_1, score_1 = all_scores[0]
        intent_2, score_2 = all_scores[1]

        if (score_1 - score_2) < CONFIDENCE_THRESHOLD:
            print(
                f"Ambiguous command. Did you mean "
                f"(1) {intent_1} or (2) {intent_2}? Enter 1 or 2:"
            )
            try:
                choice = input().strip()
            except EOFError:
                choice = "1"  # non-interactive fallback

            correct_intent = intent_2 if choice == "2" else intent_1
            best_task  = correct_intent
            best_score = score_1  # report original top score

            # --- Log correction to DB ---
            try:
                db = SQLiteManager()
                db.insert("corrections", {
                    "command_embedding": query_embedding.astype("float32").tobytes(),
                    "correct_intent":   correct_intent,
                    "timestamp":        datetime.utcnow().isoformat(),
                })
                db.close()
            except Exception as _exc:
                print(f"[NLU] Warning: could not save correction: {_exc}")

            # --- Online prototype adaptation ---
            _maybe_update_prototype(correct_intent, query_embedding)

    return best_task, float(best_score)


def _maybe_update_prototype(
    intent_name: str,
    query_embedding: "np.ndarray" = None,
) -> None:
    """Incrementally update the intent prototype every 5 confirmed corrections.

    Args:
        intent_name:     The intent that the user confirmed.
        query_embedding: The embedding vector of the most-recent ambiguous query
                         (used only as a proxy metric for the adaptation log).
    """
    global _INTENT_EMBEDDINGS

    db = SQLiteManager()
    rows = db.fetch_where("corrections", "correct_intent", intent_name)
    db.close()

    count = len(rows)

    # Update every 5 corrections, starting from 5
    if count < 5 or (count % 5) != 0:
        return

    # Reconstruct correction embedding vectors
    correction_vecs = [
        np.frombuffer(row["command_embedding"], dtype=np.float32)
        for row in rows
    ]
    mean_correction = np.mean(correction_vecs, axis=0)

    # Current prototype = mean of stored example embeddings for this intent
    if _INTENT_EMBEDDINGS is None or intent_name not in _INTENT_EMBEDDINGS:
        return

    current_prototype = np.mean(_INTENT_EMBEDDINGS[intent_name], axis=0)

    # Proxy accuracy metrics (cosine similarity against old and new prototype)
    accuracy_before = float(np.dot(current_prototype, query_embedding) /
                            max(np.linalg.norm(current_prototype) *
                                np.linalg.norm(query_embedding), 1e-9))\
        if query_embedding is not None else 0.0

    new_prototype = 0.9 * current_prototype + 0.1 * mean_correction

    accuracy_after = float(np.dot(new_prototype, query_embedding) /
                           max(np.linalg.norm(new_prototype) *
                               np.linalg.norm(query_embedding), 1e-9))\
        if query_embedding is not None else 0.0

    # Replace the stored embeddings with a single updated prototype vector
    # (broadcast as a (1, D) array so the rest of the pipeline is unaffected)
    _INTENT_EMBEDDINGS[intent_name] = new_prototype.reshape(1, -1)

    # --- Append to adaptation log ---
    ts = datetime.utcnow().isoformat()
    log_exists = os.path.exists(_ADAPTATION_LOG)
    try:
        with open(_ADAPTATION_LOG, "a", newline="") as fh:
            writer = csv.writer(fh)
            if not log_exists:
                writer.writerow(
                    ["timestamp", "intent_name", "correction_count",
                     "accuracy_before", "accuracy_after"]
                )
            writer.writerow(
                [ts, intent_name, count,
                 round(accuracy_before, 6), round(accuracy_after, 6)]
            )
    except Exception as _exc:
        print(f"[NLU] Warning: could not write adaptation log: {_exc}")

    print(f"[NLU] Prototype for '{intent_name}' updated after {count} corrections.")


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

    # 2️⃣ Strip trailing clauses: "and copy to <dir>", then "in <dir>"
    cleaned = re.sub(r'\s+and\s+copy\s+to\s+\S+', '', text_lower)
    cleaned = re.sub(r'\s+copy\s+to\s+\S+', '', cleaned)
    cleaned = re.sub(r'\s+in\s+\S+', '', cleaned)

    # 3️⃣ Remove command verbs, filler words, and orphaned conjunctions
    cleaned = re.sub(
        r'\b(find|search|look|lookup|for|receipts?|receipt|documents?|document|and)\b',
        '',
        cleaned
    )

    cleaned = cleaned.strip()

    if cleaned:
        return cleaned

    return ""


def extract_app_name(text: str) -> str:
    """
    Extract clean app name from vault commands like:
    - autofill spotify           → 'spotify'
    - generate password for github → 'github'
    - login to discord           → 'discord'
    """
    text = text.lower().strip()
    # Remove noise words, keep the meaningful noun(s)
    noise = r'\b(generate|create|make|new|a|an|the|password|pass|pw|for|autofill|fill|copy|get|login|to|use|account|my|me|into|in|secure|strong)\b'
    cleaned = re.sub(noise, '', text).strip()
    # Collapse extra spaces, take first remaining token as the app name
    tokens = cleaned.split()
    return tokens[0] if tokens else text.split()[-1]


def build_ctr(task: str, text: str) -> CTR:

    paths = extract_paths(text)

    # --------------------------------------------------

    if task == "ORGANIZE_DOWNLOADS":
        # Only use extracted path if it looks like a real path (contains / or ~)
        real_path = next((p for p in paths if '/' in p or p.startswith('~')), None)
        source = real_path if real_path else "~/Downloads"
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

        # Detect export FIRST (so "in" pattern doesn't eat it) — "copy to <dir>"
        match_copy = re.search(r'copy\s+to\s+(\S+)', text, re.IGNORECASE)
        if match_copy:
            export = match_copy.group(1)

        # Detect source after "in <dir>" (skip if it's part of copy-to fragment)
        match_in = re.search(r'\bin\s+(\S+)', text, re.IGNORECASE)
        if match_in:
            candidate = match_in.group(1)
            # Ignore "in" matches that are part of the copy-to phrase
            if export and candidate.rstrip(',') == export.lstrip('~/'):
                pass
            else:
                source = candidate

        # Resolve bare directory names (no ~ or /) relative to home
        if source and not source.startswith('~') and not source.startswith('/'):
            source = f'~/{source}'
        if export and not export.startswith('~') and not export.startswith('/'):
            export = f'~/{export}'

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
        # Only use extracted path if it looks like a real path (contains / or ~)
        real_path = next((p for p in paths if '/' in p or p.startswith('~')), None)
        source = real_path if real_path else "."
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
