#!/bin/bash
set -e  # Exit on error

echo "🚀 AI-OS Agent: CTR Architecture Demo"
echo "======================================"

# Clean test environment
rm -rf ~/Downloads_test ~/Projects/DemoApp ~/.aios/vault.*
mkdir -p ~/Downloads_test ~/Projects

echo -e "\n1️⃣ FILE ORGANIZATION (Messy → Clean)"
echo "Before:"
ls -la ~/Downloads_test || true
touch ~/Downloads_test/{invoice.pdf,photo.jpg,archive.zip,misc.txt}
python -m cli.main organize-downloads --path ~/Downloads_test --apply
echo "✅ After:"
ls -la ~/Downloads_test

echo -e "\n2️⃣ PROJECT SCAFFOLD (Zero → Ready)"
python -m cli.main create-project DemoApp --apply
echo "✅ Created:"
tree ~/Projects/DemoApp || ls -la ~/Projects/DemoApp

echo -e "\n3️⃣ PASSWORD VAULT (Browser-style Autofill)"
python -m cli.main generate-password spotify_account --apply
python -m cli.main autofill-app spotify --apply
echo "✅ Password ready in clipboard (Ctrl+V)"

echo -e "\n4️⃣ FULL AUDIT TRAIL"
echo "Last 5 CTR actions:"
tail -3 ~/.aios/ctr.log

echo -e "\n🎉 DEMO COMPLETE! Core architecture + 3 features working"
echo "Repo: https://github.com/GambitATJ/ai-os-agent"
