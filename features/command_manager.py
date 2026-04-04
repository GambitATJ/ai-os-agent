def delete_user_command(command_name: str) -> bool:
    """
    Completely removes a saved user command from all storage.
    Deletes from: user_commands, command_paraphrases.
    Removes from INTENT_EXAMPLES in memory.
    Resets _INTENT_EMBEDDINGS to None to force rebuild.
    Returns True if command existed and was deleted.
    Returns False if command was not found.
    """
    from db_manager import SQLiteManager
    import core.nlu_router as router
    
    db = SQLiteManager()
    
    # Check it exists first
    existing = db.fetch_where("user_commands", 
                               "command_name", 
                               command_name.lower().strip())
    if not existing:
        print(f"[DELETE] Command '{command_name}' not found.")
        return False
    
    # Delete from both tables
    deleted_cmd = db.delete_where("user_commands", 
                                   "command_name", 
                                   command_name.lower().strip())
    deleted_phrases = db.delete_where("command_paraphrases", 
                                       "command_name", 
                                       command_name.lower().strip())
    
    # Remove from in-memory INTENT_EXAMPLES
    intent_key = f"SAVED:{command_name.lower().strip()}"
    if intent_key in router.INTENT_EXAMPLES:
        del router.INTENT_EXAMPLES[intent_key]
        print(f"[DELETE] Removed '{intent_key}' from intent examples.")
    
    # Force embedding rebuild
    router._INTENT_EMBEDDINGS = None
    
    print(f"[DELETE] ✓ Command '{command_name}' fully removed.")
    print(f"  Deleted {deleted_cmd} command record(s) and {deleted_phrases} phrase(s).")
    return True


def list_user_commands() -> None:
    """
    Prints all saved user commands in a readable format.
    """
    from db_manager import SQLiteManager
    db = SQLiteManager()
    
    commands = db.list_user_commands()
    
    if not commands:
        print("[COMMANDS] No saved user commands found.")
        return
    
    print(f"\n[COMMANDS] {len(commands)} saved command(s):\n")
    for cmd in commands:
        print(f"  • {cmd['command_name']}")
        print(f"    Saved: {cmd['created_at'][:19]}")
    print()
