"""
DisruptionShield Coordinator - Configuration
Handles environment variables and app-wide settings.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── LLM Config ─────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Default model: Gemini
DEFAULT_LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Handle Vercel's read-only filesystem by using /tmp for SQLite
IS_VERCEL = os.getenv("VERCEL") == "1"

DATABASE_URL: str = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    if IS_VERCEL:
        DATABASE_URL = "sqlite+aiosqlite:////tmp/disruption_shield.db"
    else:
        DATABASE_URL = "sqlite+aiosqlite:///./disruption_shield.db"

# ─── App Settings ────────────────────────────────────────────────────────────
APP_NAME: str = "DisruptionShield Coordinator"
APP_VERSION: str = "1.0.0"
DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

# ─── Severity Levels ─────────────────────────────────────────────────────────
SEVERITY_LEVELS = ["Minor", "Moderate", "Major"]

# ─── Disruption Type Keywords ────────────────────────────────────────────────
DISRUPTION_KEYWORDS = {
    "power_cut": ["power cut", "power outage", "electricity", "no power", "blackout"],
    "client_call": ["client call", "urgent call", "unexpected meeting", "client meeting"],
    "traffic": ["traffic", "traffic jam", "stuck in traffic", "commute", "road block"],
    "family_emergency": ["family emergency", "emergency", "hospital", "accident", "family"],
    "health": ["sick", "unwell", "not feeling well", "headache", "doctor"],
    "technical": ["laptop crashed", "system down", "internet down", "technical issue"],
    "other": [],
}

def get_llm_config() -> dict:
    """Returns active LLM provider configuration. Non-blocking if key is missing."""
    if GEMINI_API_KEY:
        return {"provider": "gemini", "model": GEMINI_MODEL, "api_key": GEMINI_API_KEY}
    return {"provider": "none", "error": "GEMINI_API_KEY missing"}
