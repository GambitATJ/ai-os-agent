"""
test_e2e_timing.py
==================
Times each stage of the AI-OS pipeline independently for 10 commands
covering all 7 supported intents.

Stages timed:
  1. Encoding      — model.encode([text])
  2. Classification — dot-product scoring against intent prototypes
  3. CTR build     — build_ctr(task, text)
  4. Governance    — check_policy(ctr, paths)
  5. Cost estimate — CostEstimator().estimate(dir, step_count)
  6. Checkpoint    — CheckpointManager().capture(paths, command)

Run from the project root:
    python test_e2e_timing.py
"""

import os
import sys
import shutil
import tempfile
import time
import io
import contextlib
import warnings
import logging

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.disable(logging.CRITICAL)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

# Suppress policy's print() during timing
@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield

# ── Project imports ───────────────────────────────────────────────────────────
from sentence_transformers import SentenceTransformer
import core.nlu_router as _nlu
from core.nlu_router import classify_intent, build_ctr, get_model
from core.policy import check_policy
from core.ctr import CTR
from cost_estimator import CostEstimator
from checkpoint_manager import CheckpointManager
from db_manager import SQLiteManager

# ── Warm-up: build embeddings once ───────────────────────────────────────────
_nlu.build_intent_embeddings()
_model  = get_model()
_ce     = CostEstimator()

# ── Temp working directory (must be under HOME for policy.py) ─────────────────
_HOME = os.path.expanduser("~")
_TMPDIR = tempfile.mkdtemp(prefix="e2e_timing_", dir=_HOME)
_DUMMY_PATHS = [os.path.join(_TMPDIR, f"file_{i}.txt") for i in range(3)]
for p in _DUMMY_PATHS:
    open(p, "w").close()

# ── 10 commands: all 7 intents represented, 5+ distinct intents ───────────────
COMMANDS = [
    # ORGANIZE_DOWNLOADS  (2)
    ("organize ~/Downloads",                               "ORGANIZE_DOWNLOADS"),
    ("tidy up the downloads folder",                       "ORGANIZE_DOWNLOADS"),
    # CREATE_PROJECT_SCAFFOLD  (2)
    ("create a new project called TestProject",            "CREATE_PROJECT_SCAFFOLD"),
    ("scaffold a python project named DataPipeline",       "CREATE_PROJECT_SCAFFOLD"),
    # AUTOFILL_APP  (1)
    ("autofill spotify",                                   "AUTOFILL_APP"),
    # FIND_RECEIPTS  (2)
    ("find receipt for my laptop purchase",                "FIND_RECEIPTS"),
    ("search receipts in ~/Invoices",                      "FIND_RECEIPTS"),
    # GENERATE_PASSWORD  (1)
    ("generate secure password for netflix",               "GENERATE_PASSWORD"),
    # BULK_RENAME  (1)
    ("rename all files in ~/Documents",                    "BULK_RENAME"),
    # SCAN_PASSWORD_FIELDS  (1)
    ("scan for password fields",                           "SCAN_PASSWORD_FIELDS"),
]


def _time_stage(fn):
    """Run fn(), return (result, elapsed_ms)."""
    t0 = time.perf_counter()
    result = fn()
    return result, (time.perf_counter() - t0) * 1000


def _affected_paths_for(ctr: CTR) -> list:
    """Return a small, safe list of paths for policy and checkpoint calls."""
    return _DUMMY_PATHS


def _source_dir_for(ctr: CTR) -> str:
    """Return a valid directory for the cost estimator."""
    d = ctr.params.get("source_dir") or ctr.params.get("location")
    if d:
        expanded = os.path.expanduser(d)
        if os.path.isdir(expanded):
            return expanded
    return _TMPDIR


def run_pipeline_for(text: str):
    """
    Time each stage independently.
    Returns (intent, confidence, timings_dict)
    timings_dict keys: enc, cls, ctr, gov, cost, chk
    """
    # --- Stage 1: Encoding ---
    emb, t_enc = _time_stage(lambda: _model.encode([text], show_progress_bar=False)[0])

    # --- Stage 2: Classification (dot-product only, embedding already computed) ---
    def _classify_only():
        intent_embs = _nlu._INTENT_EMBEDDINGS
        scores = []
        for intent, embs in intent_embs.items():
            s = float(np.max(np.dot(embs, emb)))
            scores.append((intent, s))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[0][0], scores[0][1]

    (intent, confidence), t_cls = _time_stage(_classify_only)

    # --- Stage 3: CTR construction ---
    ctr, t_ctr = _time_stage(lambda: build_ctr(intent, text))

    # --- Stage 4: Governance ---
    paths = _affected_paths_for(ctr)
    def _gov():
        with _quiet():
            check_policy(ctr, paths)
    _, t_gov = _time_stage(_gov)

    # --- Stage 5: Cost estimation ---
    src_dir = _source_dir_for(ctr)
    _, t_cost = _time_stage(lambda: _ce.estimate(src_dir, ctr_step_count=3))

    # --- Stage 6: Checkpoint capture ---
    cm = CheckpointManager()
    _, t_chk = _time_stage(lambda: cm.capture(paths, command_text=f"e2e_test: {text}"))

    return intent, confidence, {
        "enc":  t_enc,
        "cls":  t_cls,
        "ctr":  t_ctr,
        "gov":  t_gov,
        "cost": t_cost,
        "chk":  t_chk,
    }


def main():
    results       = []
    checkpoint_ids = []

    for text, _ in COMMANDS:
        intent, conf, timings = run_pipeline_for(text)
        results.append((text, intent, conf, timings))
        # collect checkpoint ids for cleanup
        db = SQLiteManager()
        rows = db.fetch_all("checkpoints")
        db.close()
        # grab the most recently inserted checkpoint
        if rows:
            rows.sort(key=lambda r: r["timestamp"], reverse=True)
            checkpoint_ids.append(rows[0]["id"])

    # ── Build timing arrays ───────────────────────────────────────────────────
    stage_keys   = ["enc", "cls", "ctr", "gov", "cost", "chk"]
    stage_labels = [
        "1. Encoding",
        "2. Classification",
        "3. CTR build",
        "4. Governance",
        "5. Cost estimate",
        "6. Checkpoint",
    ]

    # shape: (6 stages × 10 commands)
    matrix = np.array([[r[3][k] for r in results] for k in stage_keys])
    means  = matrix.mean(axis=1)       # per-stage means
    totals = matrix.sum(axis=0)        # per-command total (sum of stages)
    mean_total = totals.mean()

    # Bottleneck & fastest
    bottleneck_idx = int(np.argmax(means))
    fastest_idx    = int(np.argmin(means))
    bottleneck_pct = means[bottleneck_idx] / mean_total * 100

    # ── Print report ──────────────────────────────────────────────────────────
    # Column widths
    SL = 19   # stage label
    CW = 6    # per-command column
    MW = 6    # mean column

    print("=== END-TO-END PIPELINE TIMING REPORT ===")
    print()
    print("Command timings (milliseconds):")

    # Header
    cmd_hdr = " | ".join(f"Cmd{i+1:d}".center(CW) for i in range(10))
    print(f"  {'Stage':<{SL}} | {cmd_hdr} | {'Mean':>{MW}}")
    sep = f"  {'-'*SL}-|-{('-'*(CW)+'-|')*10}-{'-'*MW}"
    print(sep)

    # One row per stage + totals row
    def _row(label, values, mean_val):
        cells = " | ".join(f"{v:>{CW}.1f}" for v in values)
        return f"  {label:<{SL}} | {cells} | {mean_val:>{MW}.1f}"

    for i, (label, key) in enumerate(zip(stage_labels, stage_keys)):
        print(_row(label, matrix[i], means[i]))

    # TOTAL row
    print(sep)
    print(_row("7. TOTAL", totals, mean_total))
    print()

    # Commands tested
    print("Commands tested:")
    for i, (text, intent, conf, _) in enumerate(results, 1):
        print(f"  Cmd{i}: \"{text}\" → intent: {intent}")
    print()

    # Summary lines
    fastest_name = stage_labels[fastest_idx].split(". ", 1)[1]
    bottleneck_name = stage_labels[bottleneck_idx].split(". ", 1)[1]
    print(f"BOTTLENECK: Stage {bottleneck_idx+1} ({bottleneck_name}) accounts for "
          f"{bottleneck_pct:.1f}% of total time")
    print(f"FASTEST STAGE: Stage {fastest_idx+1} at mean {means[fastest_idx]:.1f}ms")
    print(f"TOTAL OVERHEAD (non-executor): mean {mean_total:.0f}ms per command")
    print()
    print("==========================================")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    shutil.rmtree(_TMPDIR, ignore_errors=True)

    db = SQLiteManager()
    seen = set()
    for cid in checkpoint_ids:
        if cid not in seen:
            db.delete("checkpoints", cid)
            seen.add(cid)
    db.close()


if __name__ == "__main__":
    main()
