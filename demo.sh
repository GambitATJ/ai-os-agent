#!/bin/bash
# AI-OS Agent — Live Demo Script
# ================================
# Paste each section one-by-one in your terminal.
# Run `aios` first to activate the environment.
#
#   aios
#
# ──────────────────────────────────────────────

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
# DONE
# ════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  🎉  Demo complete!                          ║"
echo "║  github.com/GambitATJ/ai-os-agent            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
