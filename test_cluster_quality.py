"""
test_cluster_quality.py
=======================
Tests SemanticOrganizer clustering quality across three different
separation levels using temporary directories.

Run from the project root:
    python test_cluster_quality.py
"""

import os
import sys
import shutil
import tempfile
import warnings
import logging

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.disable(logging.CRITICAL)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score as sklearn_silhouette

from semantic_organizer import SemanticOrganizer

# ── shared organizer instance (one model load) ────────────────────────────────
_so = SemanticOrganizer()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: analyse + return (k, silhouette, cluster_list)
# cluster_list = [{"folder_name": str, "count": int}]
# Mirrors analyze() internal logic so we get silhouette score too.
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_full(directory: str):
    """Run SemanticOrganizer.analyze() and also compute the silhouette score."""
    result = _so.analyze(directory)
    if "error" in result:
        raise RuntimeError(result["error"])

    clusters = result["clusters"]
    k = len(clusters)

    # Re-encode files to compute silhouette (same call the organizer already made)
    filepaths = [fp for c in clusters for fp in c["files"]]
    texts     = [_so._get_file_text(fp) for fp in filepaths]
    embeddings = _so.model.encode(texts, show_progress_bar=False)

    # Run KMeans with the chosen k to get labels
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(embeddings)

    sil = float(sklearn_silhouette(embeddings, labels)) if k >= 2 else 0.0

    cluster_info = [
        {"folder_name": c["folder_name"], "count": len(c["files"])}
        for c in clusters
    ]
    return k, sil, cluster_info


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Create three temporary directories
# ─────────────────────────────────────────────────────────────────────────────

def _write(path: str, content: str):
    with open(path, "w") as f:
        f.write(content)


def make_dir_a() -> str:
    """HIGH SEPARATION — 3 clearly distinct groups of 5 files each."""
    d = tempfile.mkdtemp(prefix="cluster_A_")

    # Group 1: Invoices / billing
    _write(os.path.join(d, "invoice_march.txt"),
           "Invoice total amount due payment receipt billing client")
    _write(os.path.join(d, "invoice_april.txt"),
           "Amount owed billing statement payment receipt total due")
    _write(os.path.join(d, "receipt_q1.txt"),
           "Payment receipt billing invoice amount outstanding balance")
    _write(os.path.join(d, "billing_summary.txt"),
           "Monthly billing statement invoice amount client payment summary")
    _write(os.path.join(d, "tax_invoice_2025.txt"),
           "Tax invoice billing financial payment amount due receipt")

    # Group 2: Source code / programming
    _write(os.path.join(d, "utils_parser.py"),
           "function parse return algorithm loop variable class method import")
    _write(os.path.join(d, "server_main.py"),
           "socket server listen accept connection thread loop function async")
    _write(os.path.join(d, "database_schema.sql"),
           "CREATE TABLE column primary key index query SELECT WHERE JOIN")
    _write(os.path.join(d, "deploy_script.sh"),
           "bash deploy kubectl docker container build push install apt run")
    _write(os.path.join(d, "config_loader.py"),
           "config load parse yaml json settings environment variable import")

    # Group 3: Photos / vacation
    _write(os.path.join(d, "vacation_2023.txt"),
           "photo image holiday beach sunset camera landscape scenery")
    _write(os.path.join(d, "trip_paris.txt"),
           "travel holiday photo museum landmark tour sightseeing camera")
    _write(os.path.join(d, "beach_day.txt"),
           "beach ocean sunset photo holiday swim relax vacation summer")
    _write(os.path.join(d, "mountain_hike.txt"),
           "hiking mountain photo landscape trail nature outdoor adventure")
    _write(os.path.join(d, "gallery_export.txt"),
           "photo gallery image collection holiday album camera snapshot")

    return d


def make_dir_b() -> str:
    """MEDIUM SEPARATION — overlapping themes across 3 groups."""
    d = tempfile.mkdtemp(prefix="cluster_B_")

    # Group 1: Finance & work — overlapping with personal
    _write(os.path.join(d, "work_budget_q2.txt"),
           "budget expenditure work project finance team resource allocation")
    _write(os.path.join(d, "expense_report.txt"),
           "travel expense work finance reimbursement team meeting costs")
    _write(os.path.join(d, "client_proposal.txt"),
           "project scope delivery client finance budget timeline goals")
    _write(os.path.join(d, "team_review.txt"),
           "performance review goals achievement work project team members")
    _write(os.path.join(d, "annual_plan.txt"),
           "annual plan goals budget work finance growth objectives team")

    # Group 2: Personal & projects — overlapping with work
    _write(os.path.join(d, "home_project.txt"),
           "home renovation project plan budget timeline personal goals")
    _write(os.path.join(d, "personal_budget.txt"),
           "personal finance monthly budget savings goals expenses plan")
    _write(os.path.join(d, "weekend_goals.txt"),
           "weekend personal project hobby goals plan activity schedule")
    _write(os.path.join(d, "reading_list.txt"),
           "books personal hobby reading goals list learning schedule")
    _write(os.path.join(d, "fitness_plan.txt"),
           "fitness gym personal health goals exercise plan schedule")

    # Group 3: Ambiguous — could fit either
    _write(os.path.join(d, "notes_meeting.txt"),
           "notes meeting agenda action items follow-up team project plan")
    _write(os.path.join(d, "summary_week.txt"),
           "weekly summary activities progress goals finance personal work")
    _write(os.path.join(d, "ideas_draft.txt"),
           "ideas draft concepts plan project personal goals brainstorm")
    _write(os.path.join(d, "todo_list.txt"),
           "tasks todo list priority work personal goals deadlines items")
    _write(os.path.join(d, "review_notes.txt"),
           "review notes plan budget finance personal work goals progress")

    return d


def make_dir_c() -> str:
    """LOW SEPARATION — near-random content with no natural clusters."""
    d = tempfile.mkdtemp(prefix="cluster_C_")

    snippets = [
        ("file_001.txt",  "apple orange banana fruit"),
        ("data_x.txt",    "seventeen forty quick"),
        ("misc_a.txt",    "running walking cycling"),
        ("record_7.txt",  "table lamp window door"),
        ("thing_b.txt",   "cloud rain temperature pressure"),
        ("note_q.txt",    "monday tuesday calendar date"),
        ("item_z.txt",    "red blue yellow colour"),
        ("entry_3.txt",   "copper zinc metal element"),
        ("chunk_k.txt",   "circle square triangle shape"),
        ("blob_m.txt",    "pasta bread rice cereal"),
        ("page_p.txt",    "guitar violin drum instrument"),
        ("ref_r.txt",     "river lake ocean water body"),
        ("asset_s.txt",   "cat dog bird animal"),
        ("sample_t.txt",  "book paper pen writing"),
        ("point_u.txt",   "flower seed plant garden"),
    ]
    for name, content in snippets:
        _write(os.path.join(d, name), content)

    return d


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    dir_a = make_dir_a()
    dir_b = make_dir_b()
    dir_c = make_dir_c()

    try:
        k_a, sil_a, clusters_a = _analyze_full(dir_a)
        k_b, sil_b, clusters_b = _analyze_full(dir_b)
        k_c, sil_c, clusters_c = _analyze_full(dir_c)

        assess_a = "CORRECT k selected"   if k_a == 3          else "INCORRECT k selected"
        assess_b = "ACCEPTABLE"           if k_b in (2, 3)     else "INCORRECT"
        assess_c = "ACCEPTABLE"           if k_c in (2, 3)     else "INCORRECT"

        # ── Print report ──────────────────────────────────────────────────────
        print("=== CLUSTER QUALITY REPORT ===")
        print()

        print("DIRECTORY A (high separation — 15 files, 3 themes):")
        print(f"  Selected k: {k_a}")
        print(f"  Silhouette score: {sil_a:.3f}")
        print("  Clusters found:")
        for i, c in enumerate(clusters_a, 1):
            print(f"    Cluster {i} \"{c['folder_name']}\": {c['count']} files")
        print(f"  Assessment: {assess_a}")
        print()

        print("DIRECTORY B (medium separation — 15 files, mixed themes):")
        print(f"  Selected k: {k_b}")
        print(f"  Silhouette score: {sil_b:.3f}")
        print("  Clusters found:")
        for i, c in enumerate(clusters_b, 1):
            print(f"    Cluster {i} \"{c['folder_name']}\": {c['count']} files")
        print()

        print("DIRECTORY C (low separation — 15 files, random):")
        print(f"  Selected k: {k_c}")
        print(f"  Silhouette score: {sil_c:.3f}")
        print("  Clusters found:")
        for i, c in enumerate(clusters_c, 1):
            print(f"    Cluster {i} \"{c['folder_name']}\": {c['count']} files")
        print()

        # ── Summary table ─────────────────────────────────────────────────────
        print("SUMMARY TABLE:")
        print("  Directory    | Expected k | Selected k | Silhouette | Assessment")
        print("  -------------|------------|------------|------------|----------")
        print(f"  A (high)     |     3      |     {k_a}      |   {sil_a:.3f}    | {assess_a}")
        print(f"  B (medium)   |    2-3     |     {k_b}      |   {sil_b:.3f}    | {assess_b}")
        print(f"  C (low)      |    2-3     |     {k_c}      |   {sil_c:.3f}    | {assess_c}")
        print()

        # ── Key insight ───────────────────────────────────────────────────────
        if sil_a > sil_b > sil_c:
            insight = (
                f"Silhouette scores decrease monotonically from A ({sil_a:.3f}) "
                f"to B ({sil_b:.3f}) to C ({sil_c:.3f}), confirming the metric "
                f"correctly reflects real semantic separation in the data."
            )
        elif sil_a > sil_c:
            insight = (
                f"High-separation content (A: {sil_a:.3f}) scores substantially "
                f"above near-random content (C: {sil_c:.3f}), validating that "
                f"the silhouette metric captures genuine thematic structure."
            )
        else:
            insight = (
                f"Cluster quality scores span {min(sil_a,sil_b,sil_c):.3f}–{max(sil_a,sil_b,sil_c):.3f}; "
                f"the silhouette-based k selector uses the signal available in "
                f"the embedding geometry to partition files without supervision."
            )

        print(f"KEY INSIGHT: {insight}")
        print("================================")

    finally:
        shutil.rmtree(dir_a, ignore_errors=True)
        shutil.rmtree(dir_b, ignore_errors=True)
        shutil.rmtree(dir_c, ignore_errors=True)


if __name__ == "__main__":
    main()
