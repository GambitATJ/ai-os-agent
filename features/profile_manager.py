from db_manager import SQLiteManager

def setup_profile() -> None:
    """Interactive first-run profile setup."""
    db = SQLiteManager()
    
    print("\n" + "─"*50)
    print("  👤  PERSONAL PROFILE SETUP")
    print("─"*50)
    print("  This helps the system personalise responses")
    print("  and enables email features.\n")
    
    fields = [
        ("name", "Your name"),
        ("email", "Your Gmail address"),
        ("gmail_app_password", 
         "Gmail app password (for sending email)\n"
         "  Get one at: myaccount.google.com/apppasswords"),
    ]
    
    for key, label in fields:
        existing = db.get_profile(key)
        if existing and key != "gmail_app_password":
            print(f"  {label}: {existing} (press Enter to keep)")
        elif key == "gmail_app_password" and existing:
            print(f"  {label}: [set] (press Enter to keep)")
        else:
            print(f"  {label}: ", end='', flush=True)
        
        value = input().strip()
        if value:
            db.set_profile(key, value)
    
    # Add contacts
    print("\n  Add contacts for email (press Enter to skip):")
    while True:
        print("  Contact name (or Enter to finish): ",
              end='', flush=True)
        name = input().strip()
        if not name:
            break
        print(f"  Email for {name}: ", end='', flush=True)
        email = input().strip()
        if email:
            db = SQLiteManager()
            db._conn.execute(
                "INSERT INTO contacts (name, email, created_at)"
                " VALUES (?, ?, ?)",
                (name, email, 
                 __import__('datetime')
                 .datetime.utcnow().isoformat())
            )
            db._conn.commit()
            print(f"  ✓ Added {name} <{email}>")
    
    print("\n  ✓ Profile saved.\n")

def get_user_name() -> str:
    """Returns stored first name or 'there' as fallback."""
    db = SQLiteManager()
    name = db.get_profile("name")
    if name:
        return name.split()[0]
    return "there"
