"""
test_rollback_accuracy.py
=========================
Tests the semantic rollback retrieval system against two baselines.

Run from the project root:
    python test_rollback_accuracy.py
"""

import os
import sys
import warnings
import logging

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.disable(logging.CRITICAL)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from datetime import datetime, timedelta

from db_manager import SQLiteManager
from core.nlu_router import get_model

# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — 20 realistic checkpoint records spread across the last 7 days
# Categories: rename(2), organise(3), receipt search(2), export(2),
#             downloads cleanup(2), project scaffold(3), password ops(3), misc(3)
# ─────────────────────────────────────────────────────────────────────────────

_NOW = datetime.utcnow()

def _ts(days_ago: float, hours: int = 0) -> str:
    return (_NOW - timedelta(days=days_ago, hours=hours)).isoformat()

CHECKPOINTS = [
    # File renaming (2)
    {"command_text": "bulk renamed files in ~/projects/alpha using date_slug pattern",
     "timestamp": _ts(6, 2)},
    {"command_text": "renamed all jpg images in ~/Pictures/2025 with sequential numbering",
     "timestamp": _ts(5, 14)},

    # Directory organisation (3)
    {"command_text": "organised ~/Documents into subject-based subdirectories",
     "timestamp": _ts(5, 1)},
    {"command_text": "moved files from ~/Desktop into categorised folders by file type",
     "timestamp": _ts(4, 8)},
    {"command_text": "sorted ~/Music library into Artist/Album folder hierarchy",
     "timestamp": _ts(3, 20)},

    # Receipt search (2)
    {"command_text": "searched ~/Receipts for ipad purchase document",
     "timestamp": _ts(3, 10)},
    {"command_text": "located invoice for monitor payment in ~/Invoices folder",
     "timestamp": _ts(2, 22)},

    # File export (2)
    {"command_text": "exported ranked receipt results to ~/Reports/receipt_export.json",
     "timestamp": _ts(2, 15)},
    {"command_text": "copied organised files from ~/Downloads to ~/Backup directory",
     "timestamp": _ts(2, 6)},

    # Downloads cleanup (2)
    {"command_text": "organised ~/Downloads folder into Documents Images Archives categories",
     "timestamp": _ts(1, 20)},
    {"command_text": "cleaned up ~/Downloads moving installers to dedicated Installers folder",
     "timestamp": _ts(1, 12)},

    # Project scaffolding (3)
    {"command_text": "scaffolded new python project called DataPipeline in ~/Projects",
     "timestamp": _ts(1, 5)},
    {"command_text": "created project directory structure for WebScraper at ~/Projects/WebScraper",
     "timestamp": _ts(0, 22)},
    {"command_text": "initialised NLPEngine project with src tests docs folders",
     "timestamp": _ts(0, 18)},

    # Password operations (3)
    {"command_text": "generated new secure password for spotify account and saved to vault",
     "timestamp": _ts(0, 14)},
    {"command_text": "save and encrypt password vault after adding netflix credentials",
     "timestamp": _ts(0, 10)},
    {"command_text": "generated strong password for github and copied to clipboard",
     "timestamp": _ts(0, 7)},

    # Misc / additional (3)
    {"command_text": "execute file operations from plan: move invoice.pdf photo.jpg notes.txt",
     "timestamp": _ts(0, 5)},
    {"command_text": "bulk renamed screenshots in ~/Desktop/Captures with timestamp prefix",
     "timestamp": _ts(0, 3)},
    {"command_text": "organised ~/Work/Projects directory removing empty folders",
     "timestamp": _ts(0, 1)},
]

assert len(CHECKPOINTS) == 20

# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — 20 undo queries (in matching order to the checkpoints above)
# Each phrased completely differently from its command_text
# ─────────────────────────────────────────────────────────────────────────────

UNDO_QUERIES = [
    # matches CHECKPOINTS[0]
    "revert the renaming I did in my alpha project",
    # matches CHECKPOINTS[1]
    "undo the numbering I applied to my 2025 photos",
    # matches CHECKPOINTS[2]
    "roll back the documents reorganisation into topics",
    # matches CHECKPOINTS[3]
    "undo moving my desktop files into type-based folders",
    # matches CHECKPOINTS[4]
    "reverse the music library grouping by artist and album",
    # matches CHECKPOINTS[5]
    "go back on the ipad receipt lookup I ran",
    # matches CHECKPOINTS[6]
    "undo searching for the monitor invoice in my invoices",
    # matches CHECKPOINTS[7]
    "remove the json file I exported from the receipt search",
    # matches CHECKPOINTS[8]
    "undo copying downloads to the backup location",
    # matches CHECKPOINTS[9]
    "revert the downloads cleanup that sorted by category",
    # matches CHECKPOINTS[10]
    "put the installers back where they were in downloads",
    # matches CHECKPOINTS[11]
    "undo scaffolding the DataPipeline project",
    # matches CHECKPOINTS[12]
    "tear down the WebScraper directory structure I created",
    # matches CHECKPOINTS[13]
    "remove the NLPEngine project folders that were just made",
    # matches CHECKPOINTS[14]
    "delete the spotify password I just generated",
    # matches CHECKPOINTS[15]
    "revert saving the netflix login to the encrypted vault",
    # matches CHECKPOINTS[16]
    "undo adding the github password I just created",
    # matches CHECKPOINTS[17]
    "roll back moving invoice pdf and photo files",
    # matches CHECKPOINTS[18]
    "undo timestamping the screenshot filenames on desktop",
    # matches CHECKPOINTS[19]
    "restore the work projects folder before cleaning",
]

assert len(UNDO_QUERIES) == 20


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = max(float(np.linalg.norm(a) * np.linalg.norm(b)), 1e-9)
    return float(np.dot(a, b) / denom)


def main():
    # ── Insert checkpoints ────────────────────────────────────────────────────
    db = SQLiteManager()
    inserted_ids = []
    for cp in CHECKPOINTS:
        row_id = db.insert("checkpoints", {
            "checkpoint_json": "{}",
            "command_text":    cp["command_text"],
            "timestamp":       cp["timestamp"],
        })
        inserted_ids.append(row_id)
    db.close()

    # Map: position 0..19 → real DB id
    # inserted_ids[i] is the DB id for CHECKPOINTS[i]
    correct_ids = inserted_ids[:]   # correct_ids[i] == target for UNDO_QUERIES[i]

    # ── Load model and encode everything in bulk ──────────────────────────────
    model = get_model()

    cmd_texts   = [cp["command_text"] for cp in CHECKPOINTS]
    cmd_embs    = model.encode(cmd_texts,  show_progress_bar=False)
    query_embs  = model.encode(UNDO_QUERIES, show_progress_bar=False)

    # id → index lookup for semantic retrieval
    id_to_idx = {row_id: i for i, row_id in enumerate(inserted_ids)}

    # ── Step 4: Semantic retrieval ────────────────────────────────────────────
    semantic_results = []   # list of (predicted_id, confidence)
    for qe in query_embs:
        best_id    = inserted_ids[0]
        best_score = -1.0
        for i, row_id in enumerate(inserted_ids):
            score = _cosine(qe, cmd_embs[i])
            if score > best_score:
                best_score = score
                best_id    = row_id
        semantic_results.append((best_id, best_score))

    # ── Step 5: Most-recent-first baseline ───────────────────────────────────
    # Most recently inserted = last in inserted_ids
    most_recent_id = inserted_ids[-1]
    baseline_recent = [(most_recent_id, None)] * 20

    # ── Step 6: Keyword string-overlap baseline ───────────────────────────────
    def _keyword_match(query: str) -> int:
        words = set(query.lower().split())
        # ignore stop words
        stop = {"the","a","an","i","my","in","to","for","of","on","at","and",
                 "did","was","that","this","just","its","into","from","with",
                 "all","by","up","is","it","be","as","do","re","undo","roll",
                 "back","revert","go","put","remove","made","out","were","have"}
        words -= stop
        best_id    = inserted_ids[-1]   # fallback: most recent
        best_count = -1
        for i, row_id in enumerate(inserted_ids):
            cmd_words = set(cmd_texts[i].lower().split()) - stop
            overlap = len(words & cmd_words)
            if overlap > best_count:
                best_count = overlap
                best_id    = row_id
        return best_id

    baseline_keyword = [(  _keyword_match(q), None) for q in UNDO_QUERIES]

    # ── Tally results ─────────────────────────────────────────────────────────
    sem_correct = sum(1 for i,(pid,_) in enumerate(semantic_results)
                      if pid == correct_ids[i])
    rec_correct = sum(1 for i,(pid,_) in enumerate(baseline_recent)
                      if pid == correct_ids[i])
    kw_correct  = sum(1 for i,(pid,_) in enumerate(baseline_keyword)
                      if pid == correct_ids[i])

    sem_pct = sem_correct / 20 * 100
    rec_pct = rec_correct / 20 * 100
    kw_pct  = kw_correct  / 20 * 100
    improvement = sem_pct - rec_pct

    # ── Print report ──────────────────────────────────────────────────────────
    print("=== SEMANTIC ROLLBACK RETRIEVAL REPORT ===")
    print("Total test queries: 20")
    print()
    print("RESULTS BY METHOD:")
    print(f"  Semantic similarity:   {sem_correct}/20 correct ({sem_pct:.1f}%)")
    print(f"  Most-recent-first:     {rec_correct}/20 correct ({rec_pct:.1f}%)")
    print(f"  Keyword string match:  {kw_correct}/20 correct ({kw_pct:.1f}%)")
    print()
    print("PER-QUERY BREAKDOWN:")
    for i, query in enumerate(UNDO_QUERIES):
        target_id    = correct_ids[i]
        target_text  = CHECKPOINTS[i]["command_text"]
        pred_id, conf = semantic_results[i]
        tick = "✓" if pred_id == target_id else "✗"
        print(f"  Q{i+1:02d}: \"{query}\"")
        print(f"       Target: checkpoint {target_id} | \"{target_text}\"")
        print(f"       Semantic match: checkpoint {pred_id} {tick}")
        print(f"       Confidence score: {conf:.2f}")
    print()
    sign = "+" if improvement >= 0 else ""
    print(f"SEMANTIC vs BASELINE IMPROVEMENT: {sign}{improvement:.1f} pp over most-recent")
    print("==========================================")

    # ── Clean up: delete all 20 inserted rows ────────────────────────────────
    db = SQLiteManager()
    for row_id in inserted_ids:
        db.delete("checkpoints", row_id)
    db.close()


if __name__ == "__main__":
    main()
