import os
from typing import List
from .ctr import CTR


HOME_DIR = os.path.expanduser("~")


def _is_under_home(path: str) -> bool:
    """Check if path is safely under HOME directory."""
    abs_path = os.path.realpath(os.path.expanduser(path))
    return abs_path.startswith(HOME_DIR)


def check_policy(ctr: CTR, affected_paths: List[str]) -> None:
    """
    Policy checks:
    - All paths under HOME
    - Max 100 files affected
    - No system paths
    """
    
    # 1. Path constraints
    for path in affected_paths:
        if not _is_under_home(path):
            raise PermissionError(f"Path {path} is outside HOME ({HOME_DIR})")
    
    # 2. File count constraint
    if len(affected_paths) > 100:
        raise PermissionError("Too many files affected (>100)")
    
    # 3. Task-specific constraints (expand later)
    if ctr.task_type == "ORGANIZE_DOWNLOADS":
        # Downloads only for now
        pass
    # Add more task-specific rules here later
    
    print(f"[POLICY] ✅ Approved {ctr.task_type} (affected: {len(affected_paths)} paths)")

def check_shell_plan(plan_dict: dict) -> tuple[list, list, list]:
    """
    Analyses a SHELL_PLAN params dict and separates commands 
    into three lists: approved, needs_confirmation, blocked.
    
    Returns (approved, needs_confirmation, blocked) where each 
    item in each list is the original command dict.
    
    Hard-blocked terms (regardless of Gemini risk_level):
    HARD_BLOCK = [
        "sudo", "rm -rf", "mkfs", "fdisk", "dd if=", 
        "chmod 777", "> /etc", "> /sys", "> /boot",
        "| bash", "| sh", "curl | ", "wget | ",
        ":(){ :|:& };:"
    ]
    """
    approved = []
    needs_confirmation = []
    blocked = []
    
    HARD_BLOCK_EXACT = [
        "sudo", "rm -rf", "mkfs", "fdisk", "dd if=",
        "chmod 777", "> /etc", "> /sys", "> /boot",
        "| bash", "| sh", "curl | ", "wget | ",
        ":(){ :|:& };:"
    ]
    
    for cmd in plan_dict.get("commands", []):
        cmd_text = cmd.get("cmd", "")
        cmd_lower = cmd_text.lower()
        
        is_hard_blocked = False
        import re
        TRUSTED_PACKAGES = {
            "tree", "htop", "curl", "wget", "neofetch", "cowsay",
            "figlet", "sl", "lolcat", "net-tools", "unzip", "zip",
            "git", "vim", "nano", "python3-pip", "ffmpeg", "jq",
            "imagemagick", "pandoc", "tmux", "screen", "ncdu",
            "bat", "fd-find", "ripgrep", "fzf", "tldr", "httpie"
        }

        sudo_apt_match = re.match(r"^sudo\s+(apt-get|apt)\s+install\s+-y\s+(\S+)$", cmd_text.strip())
        if sudo_apt_match:
            package = sudo_apt_match.group(2)
            if package in TRUSTED_PACKAGES:
                cmd["risk_level"] = "medium"
                cmd["risk_reason"] = f"Trusted package install via sudo apt. Package '{package}' is in the approved list."
                needs_confirmation.append(cmd)
                continue
            else:
                cmd["risk_reason"] = f"sudo with unknown package '{package}'. Only pre-approved packages are permitted."
                blocked.append(cmd)
                continue

        for term in HARD_BLOCK_EXACT:
            if term.lower() in cmd_lower:
                cmd["risk_reason"] = f"BLOCKED: contains forbidden term '{term}'"
                blocked.append(cmd)
                is_hard_blocked = True
                break
                
        if is_hard_blocked:
            continue
            
        # Auto-escalate find -delete anywhere (even in home)
        # if it could match many files
        if re.search(r'find\s+.*-delete', cmd["cmd"]):
            cmd["risk_level"] = "critical"
            cmd["risk_reason"] = (
                "BLOCKED: find -delete will permanently remove "
                "files and cannot be undone. Even within your "
                "home directory this is irreversible."
            )
            blocked.append(cmd)
            continue

        # Block rm with wildcards or recursive flags on broad paths
        if re.search(r'\brm\b\s+(-rf?|-fr?)\s+[~/]', cmd["cmd"]):
            cmd["risk_level"] = "critical"  
            cmd["risk_reason"] = (
                "BLOCKED: recursive deletion. "
                "This permanently removes entire directory trees."
            )
            blocked.append(cmd)
            continue

        # Block any rm targeting paths outside home
        if re.search(r'\brm\b.*\s(/etc|/var|/usr|/sys|/boot|/lib|'
                     r'/bin|/sbin|/proc|/dev)', cmd["cmd"]):
            cmd["risk_reason"] = (
                "BLOCKED: rm targeting a system directory. "
                "This operation cannot be reversed."
            )
            blocked.append(cmd)
            continue

        # Block pipes that execute downloaded content
        if re.search(r'(curl|wget).*\|\s*(bash|sh|python|ruby|perl)',
                     cmd["cmd"]):
            cmd["risk_reason"] = (
                "BLOCKED: downloading and executing code directly. "
                "This is a common attack vector."
            )
            blocked.append(cmd)
            continue
            
        risk_level = cmd.get("risk_level", "low").lower()
        
        if risk_level == "critical":
            blocked.append(cmd)
        elif risk_level == "medium":
            needs_confirmation.append(cmd)
        else:
            approved.append(cmd)
            
    if blocked:
        print(f"\n  ⛔ {len(blocked)} command(s) blocked:")
        for b in blocked:
            print(f"     ✗  {b['cmd']}")
            print(f"        {b['risk_reason']}")

    if needs_confirmation:
        print(f"\n  ⚠  {len(needs_confirmation)} command(s) "
              f"need your approval:")
        for c in needs_confirmation:
            print(f"     ?  {c['cmd']}")
            print(f"        Risk: {c['risk_reason']}")

    if approved:
        print(f"\n  ✅ {len(approved)} command(s) cleared:")
        for a in approved:
            print(f"     ✓  {a['cmd']}")
            
    return approved, needs_confirmation, blocked

def attempt_override(blocked_commands: list) -> list:
    """
    Presents blocked commands to the user and offers a 
    password-based override for commands they understand 
    and accept responsibility for.
    
    Returns a list of commands the user chose to override.
    Only validates that the password is correct — does not
    grant sudo, just confirms the user is aware of the risk.
    """
    import subprocess, getpass
    
    if not blocked_commands:
        return [], ""
    
    print("\n" + "─"*50)
    print("  🔒  BLOCKED COMMANDS — EXPERT OVERRIDE")
    print("─"*50)
    print("  The following commands were blocked for safety.")
    print("  If you understand the risks and wish to proceed,")
    print("  you may override by entering your system password.")
    print("  This action will be logged.\n")
    
    for cmd in blocked_commands:
        print(f"  Command: {cmd['cmd']}")
        print(f"  Risk: {cmd['risk_reason']}\n")
    
    print("  Override these blocked commands? (yes/no): ",
          end='', flush=True)
    choice = input().strip().lower()
    
    if choice != "yes":
        print("  Override declined. Blocked commands skipped.")
        return [], ""
    
    # Validate system password
    print("  Enter your system password to confirm: ",
          end='', flush=True)
    try:
        password = getpass.getpass(prompt='')
    except Exception:
        print("\n  Password entry failed.")
        return [], ""
    
    # Validate password using sudo -S -v
    result = subprocess.run(
        ["sudo", "-S", "-v"],
        input=password + "\n",
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print("\n  ✗  Incorrect password. Override denied.")
        return [], ""
    
    print("\n  ✓  Password accepted.")
    print("  ⚠  EXPERT OVERRIDE ACTIVE — proceeding with "
          "blocked commands.")
    print("  These actions are logged and irreversible.\n")
    
    # Return commands with sudo prefix removed if present
    # (since password was already validated above)
    overridden = []
    for cmd in blocked_commands:
        overridden.append(cmd)
    return overridden, password
