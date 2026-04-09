import re
import os
import csv
import sys
import json
from datetime import datetime
from typing import Dict, Tuple, List
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_manager import SQLiteManager
from sentence_transformers import SentenceTransformer
from core.ctr import CTR
from core.session_context import get_context

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
    ],
    "EMAIL_TASK": [
        "email the receipt to john",
        "send the invoice to my boss",
        "mail the pdf to sarah",
        "send an email to mark with the attachment",
        "email the ipad receipt to abhijit",
        "forward the receipt to accounts",
        "send the document to my manager",
        "mail the report to the team",
        "email my friend the file",
        "send this to mark by email",
        "mail it to sarah",
        "forward this document to john by email",
    ],
    "CALENDAR_TASK": [
        "add a meeting tomorrow at 3pm",
        "schedule a call with john on friday",
        "create a calendar event for monday",
        "what do I have today",
        "show my schedule for tomorrow",
        "book a meeting at 2pm",
        "add project review to my calendar",
        "what meetings do I have this week",
        "schedule standup for 9am tomorrow",
        "remind me about the demo on friday",
        "delete the standup meeting",
        "cancel my 3pm meeting",
        "remove the project review event",
        "delete my meeting tomorrow",
        "cancel the friday call",
    ],
    "SEMANTIC_ORGANIZE": [
        "organise my files by content",
        "sort my downloads folder by topic",
        "cluster my documents semantically",
        "group similar files together",
        "reorganise my folder by meaning",
        "sort files by what they are about",
        "intelligently organise my downloads",
        "group my files by content type",
        "smart sort my documents folder",
        "arrange files by similarity",
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

    # If text contains an explicit file path, suppress ambiguity —
    # it is almost certainly a file operation, not an email.
    has_explicit_path = bool(re.search(r'[~\/][\w\/\.\-]+', text))
    if has_explicit_path and best_task in [
        "FIND_RECEIPTS", "ORGANIZE_DOWNLOADS",
        "BULK_RENAME", "SCAN_PASSWORD_FIELDS",
        "SEMANTIC_ORGANIZE"
    ]:
        return best_task, best_score

    if len(all_scores) >= 2:
        intent_1, score_1 = all_scores[0]
        intent_2, score_2 = all_scores[1]

        if best_score >= 0.5 and (score_1 - score_2) < CONFIDENCE_THRESHOLD:
            print(
                f"\nAmbiguous command. Did you mean "
                f"(1) {intent_1} or (2) {intent_2}? Enter 1 or 2:"
            )
            
            try:
                from cli.main import pause_spinner, resume_spinner
                pause_spinner()
            except ImportError:
                resume_spinner = lambda: None
                
            try:
                choice = input().strip()
            except EOFError:
                choice = "1"  # non-interactive fallback
                
            try:
                resume_spinner()
            except Exception:
                pass

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

    elif task == "SEMANTIC_ORGANIZE":
        paths = extract_paths(text)
        source = paths[0] if paths else "~/Downloads"
        return CTR("SEMANTIC_ORGANIZE",
                   {"source_dir": source})

    elif task == "CALENDAR_TASK":
        text_lower = text.lower()
        
        # Determine action — check delete first, then list, else create
        delete_words = ["delete", "cancel", "remove", "unschedule"]
        list_words = ["what", "show", "list", "check",
                      "do i have", "schedule"]
        if any(w in text_lower for w in delete_words):
            action = "delete"
        elif any(w in text_lower for w in list_words):
            action = "list"
        else:
            action = "create"
        
        # Extract time
        time_match = re.search(
            r'(\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{2}:\d{2})',
            text, re.IGNORECASE)
        time_str = time_match.group(1) if time_match else "09:00"
        
        # Extract date
        date_words = ["tomorrow", "today", "monday", "tuesday",
                      "wednesday", "thursday", "friday", 
                      "saturday", "sunday"]
        date_str = "tomorrow"
        for w in date_words:
            if w in text_lower:
                date_str = w
                break
        
        # Extract title — remove noise words
        title = text
        for noise in ["add", "schedule", "create", "book",
                      "meeting", "calendar", "event", "at",
                      time_str, date_str, "a", "an", "the",
                      "my", "for", "on", "tomorrow", "today"]:
            title = re.sub(
                r'\b' + re.escape(noise) + r'\b', 
                '', title, flags=re.IGNORECASE
            )
        title = " ".join(title.split()).strip()
        if not title:
            title = "Meeting"
        
        # Extract attendee
        attendee_match = re.search(
            r'\bwith\s+([a-zA-Z]+)', text, re.IGNORECASE)
        attendee_name = (attendee_match.group(1) 
                         if attendee_match else None)
        
        # Days ahead for list
        days_map = {"today": 1, "tomorrow": 2, 
                    "week": 7, "this week": 7}
        days_ahead = 1
        for k, v in days_map.items():
            if k in text_lower:
                days_ahead = v
                break
        
        return CTR("CALENDAR_TASK", {
            "action": action,
            "title": title,
            "date_str": date_str,
            "time_str": time_str,
            "attendee_name": attendee_name,
            "days_ahead": days_ahead
        })

    elif task == "EMAIL_TASK":
        # Extract recipient name — word after "to"
        to_match = re.search(
            r'\bto\s+([a-zA-Z]+)', text, re.IGNORECASE)
        to_name = to_match.group(1) if to_match else "unknown"
        
        # Extract explicit file path if provided
        # After context resolution, explicit_paths may contain
        # the resolved path from context
        explicit_paths = extract_paths(text)
        explicit_attachment = (explicit_paths[0]
                               if explicit_paths else None)

        # Detect receipt/document keywords suggesting
        # a search is needed
        search_keywords = [
            "receipt", "invoice", "document", "pdf",
            "file", "attachment", "report"
        ]
        # Only search if no path was resolved from context
        # AND search keywords are present
        needs_search = (
            any(kw in text.lower() for kw in search_keywords)
            and not explicit_attachment
        )
        
        # Extract search query if search is needed
        # Remove common email words to get the search term
        query = text.lower()
        for noise in ["mail", "email", "send", "to", 
                      to_name.lower(), "the", "my", "a",
                      "forward", "attach", "with", "and",
                      "receipt", "invoice", "document"]:
            query = query.replace(noise, " ")
        query_words = [w for w in query.split() if len(w) > 2]
        search_query = " ".join(query_words).strip()
        if not search_query:
            search_query = "receipt"
        
        return CTR("EMAIL_TASK", {
            "to_name": to_name,
            "subject": "Document from AI-OS",
            "body": (f"Please find the attached document "
                     f"as requested."),
            "attachment_path": explicit_attachment,
            "needs_search": needs_search,
            "search_query": search_query,
            "search_dir": "~/Downloads"
        })

    raise ValueError(f"Unknown task: {task}")


def load_saved_commands_into_examples() -> None:
    """
    Reads all rows from command_paraphrases table in SQLite.
    For each unique command_name, collects all phrases and 
    adds them to INTENT_EXAMPLES under a key formatted as:
    f"SAVED:{command_name}"
    
    This allows the sentence transformer to recognise saved 
    user commands using their stored paraphrases.
    
    Also ensures _INTENT_EMBEDDINGS is reset to None so it 
    gets rebuilt on next classify_intent call.
    """
    global _INTENT_EMBEDDINGS, INTENT_EXAMPLES
    
    from db_manager import SQLiteManager
    db = SQLiteManager()
    
    try:
        rows = db.fetch_all("command_paraphrases")
        if not rows:
            return
        
        grouped = {}  # command_name -> list of phrases
        for row in rows:
            try:
                name = row["command_name"]
            except KeyError:
                name = row[1]
            try:
                phrase = row["phrase"]
            except KeyError:
                phrase = row[2]
                
            if name not in grouped:
                grouped[name] = []
            grouped[name].append(phrase)
        
        for name, phrases in grouped.items():
            intent_key = f"SAVED:{name}"
            INTENT_EXAMPLES[intent_key] = phrases
            print(f"[NLU] Loaded saved command: '{name}' ({len(phrases)} phrases)")
            
        try:
            prefs = db.fetch_all("user_preferences")
            if prefs:
                for row in prefs:
                    try:
                        k = row["key"]
                    except KeyError:
                        k = row[0]
                    if k.startswith("disabled_feature_"):
                        try:
                            v = row["value"]
                        except KeyError:
                            v = row[1]
                        
                        feat = v.strip().upper()
                        if feat in INTENT_EXAMPLES:
                            del INTENT_EXAMPLES[feat]
                            print(f"[NLU] Feature disabled by user: {feat}")
        except Exception:
            pass
        
        _INTENT_EMBEDDINGS = None  # force rebuild
    except Exception as e:
        print(f"[NLU] Warning: could not load saved commands: {e}")

try:
    load_saved_commands_into_examples()
except Exception:
    pass

# --------------------------------------------------
# 5. Context Resolution
# --------------------------------------------------

def resolve_context_references(text: str) -> str:
    """
    Replaces vague references in user text with concrete
    values from session context before classification.

    Examples:
      "mail it to mark" + context(last_result_path=
        "~/Downloads/receipt.pdf")
      → "mail ~/Downloads/receipt.pdf to mark"

      "send that file to sarah" + same context
      → "send ~/Downloads/receipt.pdf to sarah"
    """
    ctx = get_context()

    if not ctx.has_recent_file():
        return text

    primary_file = ctx.get_primary_file()

    # Pronouns and vague references to replace
    # Order matters — replace longer phrases first
    reference_patterns = [
        "that file",
        "the file",
        "that document",
        "the document",
        "the receipt",
        "that receipt",
        "the same file",
        "the result",
        "that",
        "it",
    ]

    text_lower = text.lower()

    # Only resolve if the command looks like it wants
    # to use a previous result (send/mail/move/copy/open)
    action_words = ["mail", "send", "email", "forward",
                    "move", "copy", "open", "attach",
                    "share", "upload"]

    has_action = any(w in text_lower for w in action_words)
    if not has_action:
        return text

    # Check if text already has an explicit path
    has_explicit_path = bool(re.search(
        r'[~\/][\w\/\.\-]+', text))
    if has_explicit_path:
        return text

    # Resolve references
    resolved = text
    for pattern in reference_patterns:
        # Case-insensitive replacement
        regex = re.compile(
            r'\b' + re.escape(pattern) + r'\b',
            re.IGNORECASE
        )
        if regex.search(resolved):
            resolved = regex.sub(primary_file, resolved,
                                  count=1)
            print(f"  [CONTEXT] Resolved '{pattern}' → "
                  f"'{primary_file}'")
            break

    return resolved


# --------------------------------------------------
# 6. Public Router
# --------------------------------------------------

MULTI_TASK_PATTERNS = [
    (r'find.*and.*(?:mail|send|email)',
     ["FIND_RECEIPTS", "EMAIL_TASK"]),
    (r'search.*and.*(?:mail|send|email)',
     ["FIND_RECEIPTS", "EMAIL_TASK"]),
    (r'(?:mail|send|email).*receipt.*to',
     ["FIND_RECEIPTS", "EMAIL_TASK"]),
]


def route(text: str) -> CTR:
    original_text = text  # save before any resolution
    # Resolve any context references before classification
    text = resolve_context_references(text)

    # Detect explicit multi-task commands — run on ORIGINAL text
    # so a resolved path (e.g. ".../receipt.pdf") doesn't falsely
    # trigger the ".*receipt.*" pattern.
    for pattern, task_sequence in MULTI_TASK_PATTERNS:
        if re.search(pattern, original_text.lower()):
            print(f"\n  [NLU] Multi-step command detected.")
            print(f"  Will execute: "
                  f"{' → '.join(task_sequence)}\n")

            # Build CTRs for each task in sequence
            ctrs = []
            for task in task_sequence:
                try:
                    ctr = build_ctr(task, text)
                    ctrs.append(ctr)
                except Exception:
                    pass

            if len(ctrs) == len(task_sequence):
                # Return a special MULTI_TASK CTR
                return CTR(
                    task_type="MULTI_TASK",
                    params={
                        "tasks": [json.loads(c.to_json())
                                  for c in ctrs],
                        "description": text
                    }
                )
            break

    best_task, confidence = classify_intent(text)

    # Handle saved command retrieval
    if best_task and best_task.startswith("SAVED:"):
        command_name = best_task[len("SAVED:"):]
        from db_manager import SQLiteManager
        db = SQLiteManager()
        rows = db.fetch_where("user_commands", "command_name", command_name)
        if rows:
            try:
                stored_ctr_json = rows[0]["ctr_json"]
            except KeyError:
                stored_ctr_json = rows[0][2]
            # CTR is already imported at module level
            retrieved_ctr = CTR.from_json(stored_ctr_json)

            # Mark as replay so shell_executor skips the approval UI
            if retrieved_ctr.task_type == "SHELL_PLAN":
                retrieved_ctr.params["_is_saved_replay"] = True

            print(f"[NLU] Matched saved command: '{command_name}'")
            return retrieved_ctr
        else:
            print(f"[NLU] Warning: saved command '{command_name}' found in examples but not in database.")

    # LLM fallback when confidence is too low
    if confidence < 0.5:
        print(f"[NLU] Confidence {confidence:.2f} below threshold. Escalating to LLM planner...")
        try:
            from core.llm_planner import generate_plan
            # CTR is already imported at module level
            plan_dict = generate_plan(text)
            plan_dict["_from_llm"] = True
            shell_ctr = CTR(
                task_type="SHELL_PLAN",
                params=plan_dict,
                version="1.0"
            )
            return shell_ctr
        except RuntimeError as e:
            # API key not set
            raise ValueError(f"[NLU] Command not recognised and LLM fallback unavailable: {e}")
        except Exception as e:
            raise ValueError(f"[NLU] Command not recognised and LLM planning failed: {e}. Try rephrasing your command.")

    if confidence < 0.25 and not (best_task and best_task.startswith("SAVED:")):
        raise ValueError(f"Low confidence intent detection ({confidence:.2f})")

    return build_ctr(best_task, text)
