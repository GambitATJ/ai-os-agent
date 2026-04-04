#!/bin/bash
# AI-OS Agent — Live Demo Script
# ================================
#
# ┌─────────────────────────────────────────────────────┐
# │  START THE INTERACTIVE CHAT UI:                     │
# │                                                     │
# │      source .venv/bin/activate                      │
# │      python -m cli.main                             │
# │                                                     │
# │  Then type any command in plain English, e.g.:      │
# │    organize my downloads                            │
# │    find receipts in ~/Documents                     │
# │    generate password for spotify                    │
# │    undo last                                        │
# └─────────────────────────────────────────────────────┘
#
# Paste each section below one-by-one to demo individual features.
#

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        AI-OS Agent  —  Live Demo             ║"
echo "║  Natural Language → Structured Task → Action ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Setup test files ────────────────────────────────────────────────────────
rm -rf ~/Downloads_test ~/test_rename ~/Projects/DemoApp 2>/dev/null

mkdir -p ~/Downloads_test ~/test_rename
touch ~/Downloads_test/invoice.pdf \
      ~/Downloads_test/photo.jpg \
      ~/Downloads_test/archive.zip \
      ~/Downloads_test/notes.txt

touch ~/test_rename/photo1.jpg \
      ~/test_rename/photo2.jpg \
      ~/test_rename/holiday.jpg

echo "✅ Test files ready"


# ════════════════════════════════════════════════
# 1. FILE ORGANISER
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1️⃣  FILE ORGANISER — Messy folder → sorted"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Before:"
ls ~/Downloads_test
echo ""

python -m cli.main nl "organize ~/Downloads_test"

echo ""
echo "After:"
ls ~/Downloads_test


# ════════════════════════════════════════════════
# 2. PROJECT SCAFFOLD
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  2️⃣  PROJECT SCAFFOLD — Zero to structured"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python -m cli.main nl "create a new python project called DemoApp"

echo ""
echo "Structure created:"
find ~/Projects/DemoApp -maxdepth 2 | sort


# ════════════════════════════════════════════════
# 3. BULK RENAME
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  3️⃣  BULK RENAME — Consistent naming in one shot"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Before:"
ls ~/test_rename
echo ""

python -m cli.main bulk-rename ~/test_rename --pattern date_slug --apply

echo ""
echo "After:"
ls ~/test_rename


# ════════════════════════════════════════════════
# 4. PASSWORD VAULT — Generate
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  4️⃣  PASSWORD VAULT — Generate & store"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python -m cli.main nl "generate password for spotify"

echo ""
echo "  → Password generated, encrypted, and copied to clipboard"


# ════════════════════════════════════════════════
# 5. PASSWORD VAULT — Autofill
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  5️⃣  PASSWORD VAULT — Autofill from vault"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python -m cli.main nl "autofill spotify"

echo ""
echo "  → Ctrl+V to paste anywhere"


# ════════════════════════════════════════════════
# 6. DOCUMENT SEARCH (AI / OCR)
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  6️⃣  DOCUMENT SEARCH — AI-ranked results"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python -m cli.main nl "find ipad in ~/test_receipts"


# ════════════════════════════════════════════════
# 7. AUDIT TRAIL
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  7️⃣  FULL AUDIT TRAIL — Every action logged"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Last 6 logged actions:"
tail -6 ~/.aios/ctr.log



# ════════════════════════════════════════════════
# 8. UDCR — Unified Dual-path Command Router
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  8️⃣  UDCR — Offline intelligence + online fallback"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Parsing a multi-step workflow in natural language:"
echo ""

.venv/bin/python3 - <<'PYEOF'
from workflow_parser import WorkflowParser

parser = WorkflowParser()

workflows = [
    "Organize my downloads, then rename files in ~/Photos",
    "Scan for passwords in ~/Documents and then find receipts in ~/Invoices",
    "Create a python project called DataPipeline, then organize ~/Downloads",
]

for wf in workflows:
    print(f"  Input: \"{wf}\"")
    steps = parser.parse(wf)
    for i, step in enumerate(steps, 1):
        print(f"    Step {i}: {step['executor_type']}  params={step['parameters']}")
    print()
PYEOF

echo ""
echo "  → Offline path: sentence-transformers classify each clause, regex extracts paths."
echo "  → Online path:  Claude API races against offline; first to finish wins."
echo "  → [UDCR] tag shows which path was used — fully transparent."
echo ""
echo "  Compound multi-step command (offline, no internet required):"
echo ""

python -m cli.main nl "organize ~/Downloads_test and rename files in ~/test_rename"


# ════════════════════════════════════════════════
# 9. SEMANTIC ORGANISER — AI understands file content
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  8️⃣  SEMANTIC ORGANISER — Cluster files by meaning"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create a messy folder with files from different topics
rm -rf ~/semantic_demo && mkdir ~/semantic_demo
echo "Invoice #101. Amount: \$450. Services rendered."  > ~/semantic_demo/invoice_jan.txt
echo "Receipt for tax filing 2025. Paid in full."       > ~/semantic_demo/corp_tax_receipt.txt
echo "Contract between Vendor LLC and Client Inc."      > ~/semantic_demo/vendor_agreement.doc
echo "Q3 billing data: July 500, August 600."           > ~/semantic_demo/q3_billing.csv
echo "Day 1: Eiffel Tower. Day 2: Louvre Museum."       > ~/semantic_demo/paris_itinerary.txt
echo "EXIF: Paris, France. Landmark photo."             > ~/semantic_demo/img_paris.jpg
echo "Train ticket from London to Paris."               > ~/semantic_demo/eurostar_ticket.pdf
echo "import socket; while True: conn = s.accept()"    > ~/semantic_demo/server_loop.py
echo "CREATE TABLE users (id INT, email VARCHAR);"      > ~/semantic_demo/schema.sql
echo "kubectl apply -f . && echo 'Deployed'"            > ~/semantic_demo/deploy.sh
echo "version: '3'; services: db: image: postgres"     > ~/semantic_demo/docker_compose.yml
echo "pytest tests/ && echo 'All tests pass'"           > ~/semantic_demo/run_tests.sh

echo "Before — 12 mixed files in one folder:"
ls ~/semantic_demo
echo ""

echo "y" | .venv/bin/python3 -c "
from semantic_organizer import run_organizer_flow
run_organizer_flow('$HOME/semantic_demo')
"

echo ""
echo "After — files moved into semantic clusters:"
find ~/semantic_demo -type f | sort


# ════════════════════════════════════════════════
# 10. UNDO / CHECKPOINT RESTORE
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  9️⃣  UNDO — Roll back any file operation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Every destructive command captured a checkpoint."
echo "  Rolling back the most recent operation:"
echo ""

python -m cli.main nl "revert last"

echo ""
echo "  → Snapshot compared. Modified / missing files reported & restorable."
echo ""
echo "  Rolling back a specific past action by description:"
echo ""

python -m cli.main nl "undo the bulk rename"

echo ""
echo "  → The system embeds both your query and every past command description,"
echo "    picks the closest match by cosine similarity, and restores that snapshot."


# ════════════════════════════════════════════════
# 11. COST ESTIMATOR — Know before you commit
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1⃣1⃣  COST ESTIMATOR — Predict then track execution"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Before every planned file operation the system prints an estimate:"
echo ""

.venv/bin/python3 - <<'PYEOF'
from cost_estimator import CostEstimator
import os, tempfile

# Simulate a directory with 15 files
tmpdir = tempfile.mkdtemp()
for i in range(15):
    open(os.path.join(tmpdir, f"file{i}.txt"), "w").close()

ce = CostEstimator()
est = ce.estimate(tmpdir, ctr_step_count=8)
print("  " + ce.display_estimate(est))
print()
print(f"  Optimized estimate (depth-1, capped at 100 files):")
opt = ce.optimized_estimate(tmpdir, ctr_step_count=8)
print("  " + ce.display_estimate(opt))
print()
print("  Performance log is stored in SQLite so past estimates vs actuals")
print("  can be reviewed — proving the system learns its own timing profile.")

import shutil; shutil.rmtree(tmpdir)
PYEOF


# ════════════════════════════════════════════════
# 12. DATABASE — Live SQLite state behind every action
# ════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1️⃣2️⃣  DATABASE — Checkpoint capture → inspect → undo"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Step 1: Run the file organiser for real (writes a checkpoint to SQLite)"
echo ""

python -m cli.main nl "organize ~/Downloads_test"

echo ""
echo "  Step 2: Inspect the checkpoints table — the DB captured the state BEFORE the move"
echo ""

.venv/bin/python3 - <<'PYEOF'
from db_manager import SQLiteManager
import json

db = SQLiteManager()
rows = db.fetch_all("checkpoints")
db.close()

if not rows:
    print("  (no checkpoints yet — run the organiser first)")
else:
    latest = rows[-1]
    snapshot = json.loads(latest["checkpoint_json"])
    print(f"  Latest checkpoint  id={latest['id']}")
    print(f"  Command : {latest['command_text']}")
    print(f"  Captured: {latest['timestamp']}")
    print(f"  Files snapshotted: {len(snapshot.get('files', {}))}")
    print(f"  Dirs snapshotted : {len(snapshot.get('dirs', {}))}")
    print(f"\n  Total checkpoints in DB: {len(rows)}")
PYEOF

echo ""
echo "  Step 3: Revert — the undo command reads that checkpoint and reports changes"
echo ""

python -m cli.main nl "revert last"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Performance log — estimated vs actual timing"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Every completed command logs its predicted and actual duration."
echo "  Running rename so the cost estimator logs a row, then querying it:"
echo ""

python -m cli.main bulk-rename ~/test_rename --pattern date_slug --apply

echo ""

.venv/bin/python3 - <<'PYEOF'
from db_manager import SQLiteManager

db = SQLiteManager()
rows = db.fetch_recent("performance_log", hours=24)
db.close()

if not rows:
    print("  (no performance entries yet — run a command via the nl dispatcher first)")
else:
    print(f"  {'Feature':<30} {'Estimated':>10} {'Actual':>10} {'Files':>6} {'Steps':>6}")
    print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*6} {'-'*6}")
    for r in rows[-5:]:          # show up to last 5 entries
        print(f"  {r['feature_name']:<30} {str(r['estimated_seconds'])+'s':>10} {str(r['actual_seconds'])+'s':>10} {str(r['file_count']):>6} {str(r['step_count']):>6}")
    print(f"\n  Total entries in performance_log: {len(db.fetch_all('performance_log')) if False else len(rows)}")
PYEOF


# ════════════════════════════════════════════════
# DONE
# ════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  🎉  Demo complete!                          ║"
echo "║  github.com/GambitATJ/ai-os-agent            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

