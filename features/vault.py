import re
import os
import json
import secrets
import string
from pathlib import Path
from typing import Dict, Optional, List
from cryptography.fernet import Fernet
from core.ctr import CTR, validate_ctr
from core.planner import plan
from core.policy import check_policy
from core.executor import execute
from core.steps import Step
from core.logger import log_ctr
from core.ctr import CTR


VAULT_PATH = Path.home() / ".aios" / "vault.enc"
VAULT_KEY_PATH = Path.home() / ".aios" / "vault.key"


class PasswordVault:
    def __init__(self):
        self.vault_dir = Path.home() / ".aios"
        self.vault_dir.mkdir(exist_ok=True)
        
        # Generate key if doesn't exist
        if not VAULT_KEY_PATH.exists():
            key = Fernet.generate_key()
            VAULT_KEY_PATH.write_bytes(key)
            os.chmod(str(VAULT_KEY_PATH), 0o600)
        
        self.key = VAULT_KEY_PATH.read_bytes()
        self.cipher = Fernet(self.key)
    
    def _load_vault(self) -> Dict[str, Dict]:
        """Load decrypted vault."""
        if not VAULT_PATH.exists():
            return {}
        
        encrypted_data = VAULT_PATH.read_bytes()
        decrypted = self.cipher.decrypt(encrypted_data)
        return json.loads(decrypted.decode())
    
    def _save_vault(self, vault_data: Dict[str, Dict]) -> None:
        """Save encrypted vault."""
        encrypted = self.cipher.encrypt(json.dumps(vault_data).encode())
        VAULT_PATH.write_bytes(encrypted)
        os.chmod(str(VAULT_PATH), 0o600)
    
    def generate_password(self, label: str, length: int = 20, 
                         uppercase: bool = True, lowercase: bool = True,
                         digits: bool = True, symbols: bool = True):
        """Generate cryptographically secure password."""
        chars = ''
        if uppercase: chars += string.ascii_uppercase
        if lowercase: chars += string.ascii_lowercase
        if digits: chars += string.digits
        if symbols: chars += "!@#$%^&*()_+-=[]{}|;:,.<>?/"
        
        password = ''.join(secrets.choice(chars) for _ in range(length))
        score = min(100, length * 4 + (uppercase + lowercase + digits + symbols) * 15)
        
        vault = self._load_vault()
        vault[label] = {
            "password": password,
            "strength": score,
            "policy": {"length": length, "uppercase": uppercase, "lowercase": lowercase, "digits": digits, "symbols": symbols},
            "created": str(secrets.token_hex(8))
        }
        self._save_vault(vault)
        
        return password, score
    
    def get_password(self, label: str) -> Optional[str]:
        """Retrieve password by label."""
        vault = self._load_vault()
        return vault.get(label, {}).get("password")
    
    def scan_for_password_fields(self, scope: str) -> List[Dict]:
        """Browser-like: Scan files for password fields."""
        scope_path = Path(scope).expanduser()
        findings = []
        
        # Heuristics for password fields (browser-style detection)
        password_patterns = [
            r'password\s*[:=]\s*["\']?\w*["\']?',
            r'pwd\s*[:=]\s*["\']?\w*["\']?',
            r'pass(wd)?\s*[:=]\s*["\']?\w*["\']?',
            r'autocomplete=["\']?password["\']?',
            r'type=["\']?password["\']?',
            r'input.*name=["\']?(pwd|pass|password)["\']?'
        ]
        
        for file_path in scope_path.rglob("*"):
            if file_path.is_file() and file_path.suffix in ['.html', '.htm', '.txt', '.md', '.conf', '.json', '.yaml', '.yml']:
                try:
                    content = file_path.read_text()
                    for i, pattern in enumerate(password_patterns):
                        if re.search(pattern, content, re.IGNORECASE):
                            findings.append({
                                "file": str(file_path),
                                "line": "Detected password field pattern",
                                "suggestion": "generate_new" if not self.get_password(file_path.stem) else "autofill_saved",
                                "confidence": 80 + i * 5
                            })
                            break
                except:
                    continue
        
        return findings
    
    def detect_app_login(self, app_name: str) -> Optional[str]:
        """Detect if app needs password (CLI heuristic)."""
        login_patterns = {
            "spotify": "spotify_account",
            "discord": "discord_user", 
            "steam": "steam_account",
            "slack": "slack_workspace",
            "zoom": "zoom_personal",
            "teams": "teams_work"
        }
        return login_patterns.get(app_name.lower())
    
    def autofill_app(self, app_name: str, dry_run: bool = True) -> bool:
        """Autofill detected app login."""
        label = self.detect_app_login(app_name)
        if not label:
            print(f"[VAULT] ℹ️  No login pattern known for '{app_name}'")
            print("     Add to vault with: aios generate-password <custom-label>")
            return False
        
        password = self.get_password(label)
        if not password:
            print(f"[VAULT] ❌ No saved password for '{label}'")
            print(f"     Generate: aios generate-password {label}")
            return False
        
        if dry_run:
            print(f"[DRY-RUN] Would autofill '{app_name}' from vault:{label}")
            print(f"         Password: {password[:8]}**** (copied to clipboard)")
        else:
            try:
                import pyperclip
                pyperclip.copy(password)
                print(f"[AUTOFILL] ✅ '{app_name}' password copied to clipboard from {label}")
                print(f"         Ready to paste (Ctrl+V)")
            except ImportError:
                print(f"[AUTOFILL] ✅ Password ready: {password[:8]}**** from {label}")
        
        return True
    
    def autofill_config(self, file_path: str, dry_run: bool = True) -> List[str]:
        """Scan config for password placeholders."""
        path = Path(file_path).expanduser()
        if not path.exists():
            print(f"[VAULT] ❌ File not found: {file_path}")
            return []
        
        content = path.read_text()
        patterns = [
            r'(password|pwd|pass(?:word)?)\s*[:=]\s*["\']?([^"\',\s\n\r]+)["\']?',
            r'autocomplete=["\']?password["\']',
            r'type=["\']?password["\']'
        ]
        
        matches = []
        for pattern in patterns:
            found = re.finditer(pattern, content, re.IGNORECASE)
            for match in found:
                field = match.group(1).lower()
                placeholder = match.group(2) if len(match.groups()) > 1 and match.group(2) else "MISSING"
                label = f"{path.stem}_{field}"
                
                matches.append({
                    "field": field,
                    "placeholder": placeholder,
                    "label": label,
                    "has_saved": bool(self.get_password(label))
                })
        
        if matches:
            print(f"[VAULT] Found {len(matches)} password fields:")
            for m in matches:
                action = "🆕 Generate" if not m["has_saved"] else "💾 Autofill"
                print(f"  {action} {m['field']}='{m['placeholder']}' → vault:{m['label']}")
        
        return matches


# Global vault instance
vault = PasswordVault()

# Replace generate_password_action and scan_password_fields with:
def generate_password_action(label: str, length: int = 20, 
                           uppercase: bool = True, lowercase: bool = True,
                           digits: bool = True, symbols: bool = True,
                           dry_run: bool = True) -> None:
    """CTR workflow for password generation."""
    ctr = CTR(
        task_type="GENERATE_PASSWORD",
        params={
            "label": label,
            "length": length,
            "uppercase": uppercase,
            "lowercase": lowercase,
            "digits": digits,
            "symbols": symbols
        }
    )
    
    print(f"[WORKFLOW] CTR: {ctr}")
    
    # Simple logging (no workflow.py)
    log_ctr(ctr, "STARTED")
    validate_ctr(ctr)
    log_ctr(ctr, "VALIDATED")
    
    print(f"[PLANNER] Generated password for '{label}'")
    affected_paths = [str(VAULT_PATH), str(VAULT_KEY_PATH)]
    check_policy(ctr, affected_paths)
    log_ctr(ctr, "POLICY_APPROVED")
    
    if dry_run:
        print("[EXECUTOR] DRY-RUN: Would generate & store password")
        log_ctr(ctr, "COMPLETED", {"dry_run": True})
    else:
        password, strength = vault.generate_password(label, length, uppercase, lowercase, digits, symbols)
        print(f"[EXECUTOR] ✅ Generated: {password[:8]}... (strength: {strength}/100)")
        print(f"           Stored in vault: {VAULT_PATH}")
        log_ctr(ctr, "COMPLETED", {"strength": strength})



def scan_password_fields(scope: str, dry_run: bool = True) -> None:
    """CTR workflow for password field detection."""
    ctr = CTR(
        task_type="SCAN_PASSWORD_FIELDS",
        params={"scope": scope}
    )
    
    print(f"[WORKFLOW] CTR: {ctr}")
    from core.workflow import run_workflow
    run_workflow(ctr, dry_run)
    
    if not dry_run:
        findings = vault.scan_for_password_fields(scope)
        print(f"[EXECUTOR] Found {len(findings)} potential password fields:")
        for f in findings:
            sug = "🆕 Generate new" if f["suggestion"] == "generate_new" else "💾 Autofill saved"
            print(f"  - {f['file']}: {sug} (confidence: {f['confidence']}%)")
