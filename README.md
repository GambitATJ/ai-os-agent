# 🤖 AI OS Agent

A local, offline AI assistant for your Linux desktop. Control your file system, vault, and projects using natural language — no cloud required.

## ✅ Prerequisites

```bash
sudo apt install python3.10-venv git xclip tesseract-ocr poppler-utils
```

> `tesseract-ocr` and `poppler-utils` are required for the receipt-finder feature (OCR on PDFs/images).

## 🚀 Quick Start

```bash
git clone https://github.com/GambitATJ/ai-os-agent.git
cd ai-os-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 🧠 Usage

### Natural Language (recommended)
```bash
python -m cli.main nl "organize my downloads"
python -m cli.main nl "create a new project called my-app"
python -m cli.main nl "generate a password for github"
python -m cli.main nl "rename files in ~/Photos"
python -m cli.main nl "find ipad receipt in ~/Documents and copy to ~/Receipts"
```

### Interactive Chat Mode
```bash
python -m cli.main chat
```

### Direct Commands
```bash
python -m cli.main organize-downloads --apply
python -m cli.main create-project my-app --apply
python -m cli.main generate-password github --apply
python -m cli.main bulk-rename ~/Photos --apply
python -m cli.main find-receipts ~/Documents --query "ipad" --export ~/Receipts --apply
python -m cli.main scan-passwords .
python -m cli.main autofill-app spotify --apply
```

### Global Hotkey Daemon (vault autofill on demand)
```bash
python -m cli.main hotkey --key "<ctrl>+<alt>+v"
```
Press the hotkey while any text field is focused to auto-paste the matching vault password.

## 📁 Project Structure

```
ai-os-agent/
├── cli/
│   └── main.py          # CLI entry point (argparse + subcommands)
├── core/
│   ├── nlu_router.py    # NL intent classification + parameter extraction
│   ├── ctr.py           # Command Task Record (structured task object)
│   ├── workflow.py      # Executes a CTR step-by-step
│   ├── planner.py       # Breaks CTR into steps
│   ├── executor.py      # Runs individual steps
│   ├── policy.py        # Dry-run / apply policy
│   └── logger.py        # Logging helpers
├── features/
│   ├── downloads.py     # Organize downloads by file type
│   ├── projects.py      # Scaffold new project directories
│   ├── vault.py         # Encrypted password vault + autofill
│   ├── rename.py        # Bulk rename with date/number patterns
│   ├── receipts.py      # AI-powered OCR document search (PDF/image)
│   ├── sandbox.py       # Sandboxed execution helper
│   └── templates.py     # Project scaffold templates
├── hotkey_daemon.py     # Global hotkey listener (pynput/xlib)
├── requirements.txt
└── demo.sh              # Feature demo script
```

## 🔐 Vault

Passwords are stored encrypted in `~/.aios/vault.enc`. This directory is intentionally excluded from git via `.gitignore`.

## 🧪 Demo

```bash
bash demo.sh
```
