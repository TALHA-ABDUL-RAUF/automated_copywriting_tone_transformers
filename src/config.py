"""
config.py
---------
Single source of truth for:
  1. Environment / credentials
  2. Platform-specific structural constraints

Why this lives in its own file:
If marketing tells you "X's limit changed from 280 to 300 characters,"
this is the ONLY file you touch. Nothing in prompt_engine.py or
async_pipeline.py needs to change.
"""

import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not GROQ_API_KEY:
    # We don't raise here so `--help` and unit tests still work without a key.
    # The pipelines raise a clear error the moment a real API call is attempted.
    pass

# ---------------------------------------------------------------------------
# Platform constraints — the "Platform-Specific Filtering" layer from the
# blueprint. These get appended to the master prompt as hard rules, and are
# also used to validate the model's output length after generation.
# ---------------------------------------------------------------------------
PLATFORM_RULES: dict[str, dict] = {
    "linkedin": {
        "max_chars": 3000,
        "style_hint": "Professional, value-driven, no more than one emoji.",
    },
    "instagram": {
        "max_chars": 2200,
        "style_hint": "Punchy, visual, emoji-friendly, hook in the first line.",
    },
    "twitter": {
        "max_chars": 280,
        "style_hint": "Extremely concise, one clear idea, no fluff.",
    },
    "email": {
        "max_chars": 1500,
        "style_hint": "Structured with a subject line, greeting, and clear CTA.",
    },
    "facebook": {
        "max_chars": 63206,
        "style_hint": "Conversational, community-oriented, moderate length.",
    },
}

DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 1.0
DEFAULT_MAX_TOKENS = 400

# Max simultaneous in-flight requests for the real-time async pipeline.
# This is the "Semaphore Gate" from the blueprint — protects against
# HTTP 429 (Too Many Requests) when fanning out across platforms.
MAX_CONCURRENT_REQUESTS = 5
