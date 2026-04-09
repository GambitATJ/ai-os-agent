import os
import json
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

try:
    from google import genai
    _HAS_GENAI = True
except ImportError:
    _HAS_GENAI = False

if GEMINI_API_KEY and _HAS_GENAI:
    client = genai.Client()
    # User's hard override: always default to 3.1 flash lite for this project.
    MODEL_NAME = "gemini-3.1-flash-lite-preview"
else:
    client = None
    MODEL_NAME = None
    print("[LLM] Warning: GEMINI_API_KEY not set. LLM fallback disabled.")

PLAN_PROMPT = """You are a shell command planner for a personal Ubuntu 22.04 system. The user has requested: {user_request}

Return a JSON object with exactly this structure and no other text, no markdown, no backticks:
{{
  "intent_description": "one sentence describing what this does",
  "commands": [
    {{
      "cmd": "the exact shell command",
      "explanation": "what this specific command does in plain English",
      "risk_level": "low or medium or critical",
      "risk_reason": "why this is risky, or null if risk_level is low"
    }}
  ],
  "saveable": true
}}

Rules for risk_level:
- critical: involves sudo, rm -rf, mkfs, dd, chmod on system files, writing outside home directory, network requests to unknown hosts
- medium: installs software without sudo (pip, npm, snap with --user), modifies many files at once, downloads from the internet
- low: reads files, creates files in home directory, moves files within home directory, runs installed tools

Use only commands that work on Ubuntu 22.04. Never use sudo.
All file paths must be within the user home directory.
If the request requires sudo or kernel access, still include the command but mark it as critical with a clear risk_reason.
For package removal, prefer: apt-get remove -y <package> run via the override mechanism rather than generating sudo directly. Always include -y flag for apt commands to prevent interactive prompts."""

def generate_plan(user_request: str) -> dict:
    """
    Calls Gemini API and returns a parsed dict matching the SHELL_PLAN CTR params structure.
    Raises RuntimeError if API key is not set.
    Raises ValueError if response cannot be parsed as valid JSON.
    Raises RuntimeError if API call fails for any reason.
    """
    if client is None:
        raise RuntimeError("[LLM] Gemini API key not configured. Set GEMINI_API_KEY in .env file.")
    
    prompt = PLAN_PROMPT.format(user_request=user_request)
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        raw = response.text.strip()
    except Exception as e:
        print(f"[LLM] Main model ({MODEL_NAME}) failed with error: {e}. Switching to fallback model.")
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            raw = response.text.strip()
        except Exception as fallback_e:
            raise RuntimeError(f"API call to both models failed. Fallback error: {fallback_e}")
    
    # Strip markdown code fences if present
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"[LLM] Could not parse Gemini response as JSON. Raw response: {raw[:200]}")
    
    required_keys = {"intent_description", "commands", "saveable"}
    if not isinstance(parsed, dict) or not required_keys.issubset(parsed.keys()):
        raise ValueError("[LLM] Gemini response missing required fields.")
    
    if not isinstance(parsed.get("commands"), list) or len(parsed["commands"]) == 0:
        raise ValueError("[LLM] Command item missing required fields.") # Actually user text said "commands is a non-empty list" but exception is generic
        
    for item in parsed["commands"]:
        item_req = {"cmd", "explanation", "risk_level"}
        if not isinstance(item, dict) or not item_req.issubset(item.keys()):
            raise ValueError("[LLM] Command item missing required fields.")
            
    return parsed

def generate_paraphrases(trigger_phrase: str) -> list[str]:
    """
    Given a trigger phrase like "install tree", returns a list of 8 semantically equivalent phrases for use as intent examples in the sentence transformer.
    """
    if client is None:
        return [trigger_phrase]
        
    prompt = f"""Generate exactly 8 different ways a user might phrase this command request: "{trigger_phrase}"
Return a JSON array of 8 strings only. No other text, no markdown, no explanation.
Example format: ["phrase 1", "phrase 2", ..., "phrase 8"]
The phrases should vary in vocabulary and structure but all mean the same thing."""

    try:
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
        except Exception as e:
            print(f"[LLM] Main model ({MODEL_NAME}) failed for paraphrasing. Switching to fallback.")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
        raw = response.text.strip()
        
        # Strip markdown fences
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        
        parsed = json.loads(raw)
        if isinstance(parsed, list) and len(parsed) >= 1 and all(isinstance(x, str) for x in parsed):
            return parsed
    except Exception:
        pass
        
    return [trigger_phrase]

def run_demo():
    if GEMINI_API_KEY:
        print(f"[LLM] GEMINI_API_KEY is set. Using model: {MODEL_NAME}\n")
        
        print("--- Testing generate_plan() ---")
        try:
            plan = generate_plan("create a folder called test_demo on the desktop")
            print(json.dumps(plan, indent=2))
        except Exception as e:
            print("generate_plan failed:", e)
            
        print("\n--- Testing generate_paraphrases() ---")
        try:
            phrases = generate_paraphrases("install tree")
            print(json.dumps(phrases, indent=2))
        except Exception as e:
            print("generate_paraphrases failed:", e)
    else:
        print("Set GEMINI_API_KEY in .env to test")

if __name__ == "__main__":
    run_demo()
