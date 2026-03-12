# AGENTS.md — Notes for AI Assistants

This file is intended to help any AI coding assistant (Antigravity, Copilot, etc.) understand the project layout and conventions before making changes.

## What This Project Does

`ai-os-agent` is a **local, offline** AI productivity agent for Linux desktops. Users type natural language commands (e.g., "organize my downloads", "find Starbucks receipt") and the system classifies the intent, extracts parameters, and executes file system operations.

There is **no external API** (no OpenAI, no cloud). NL understanding uses `sentence-transformers` (embedding cosine similarity) locally.

## Architecture at a Glance

```
User text
   │
   ▼
core/nlu_router.py      ← Intent classification (embedding similarity) + param extraction (regex)
   │  produces CTR
   ▼
core/ctr.py             ← CTR (Command Task Record): task_type + params dict (Pydantic model)
   │
   ▼
core/workflow.py        ← Orchestrates execution: plan → steps → execute
   │
   ▼
features/*.py           ← Feature modules (downloads, vault, rename, receipts, projects, ...)
```

The entry point is `cli/main.py` (argparse). The `nl` subcommand routes through `nlu_router → workflow`. Direct subcommands skip NLU and call feature functions directly.

## Key Conventions

- **Dry-run by default.** All feature functions accept a `dry_run=True` parameter. Pass `--apply` to actually execute.
- **CTR is the contract.** `core/ctr.py` defines `TaskType` (a `Literal`) and the `CTR` Pydantic model. When adding a new feature, add its `TaskType` to the `Literal`, add examples to `INTENT_EXAMPLES` in `nlu_router.py`, add a `build_ctr` branch, and implement the feature in `features/`.
- **Vault data lives in `~/.aios/`**, which is `.gitignore`d. Never commit vault files.
- **No top-level scripts** — run via `python -m cli.main <subcommand>`.

## Adding a New Feature — Checklist

1. Add a new `TaskType` literal in `core/ctr.py`
2. Add intent examples in `core/nlu_router.py` → `INTENT_EXAMPLES`
3. Add a `build_ctr` branch in `nlu_router.py` → `build_ctr()`
4. Add a CLI subcommand in `cli/main.py`
5. Implement the feature in `features/<feature_name>.py`
6. Add the feature call to `cli/main.py`'s `if/elif` dispatch block
7. Update `demo.sh` with a NL example of the new command

## System Dependencies (not in requirements.txt)

These must be installed via `apt`:
- `tesseract-ocr` — OCR engine used by `features/receipts.py` via `pytesseract`
- `poppler-utils` — PDF → image conversion used by `pdf2image`
- `xclip` — clipboard access for vault autofill
