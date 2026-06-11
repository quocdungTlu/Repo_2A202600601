"""
Lab 11 — Configuration & API Key Setup
"""
import os
from getpass import getpass


# Single source of truth for the LLM backend.
# gemini-2.0-flash has a much higher free-tier quota than 2.5-flash-lite.
MODEL_NAME = "gemini-2.0-flash"


def setup_api_key():
    """Load Google API key from environment or prompt (hidden input)."""
    if "GOOGLE_API_KEY" not in os.environ:
        os.environ["GOOGLE_API_KEY"] = getpass("Enter Google API Key: ")
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "0"
    print("API key loaded.")


# Allowed banking topics (used by topic_filter)
ALLOWED_TOPICS = [
    "banking", "account", "transaction", "transfer",
    "loan", "interest", "savings", "credit",
    "deposit", "withdrawal", "balance", "payment",
    "tai khoan", "giao dich", "tiet kiem", "lai suat",
    "chuyen tien", "the tin dung", "so du", "vay",
    "ngan hang", "atm",
]

# Blocked topics (immediate reject)
BLOCKED_TOPICS = [
    "hack", "exploit", "weapon", "drug", "illegal",
    "violence", "gambling", "bomb", "kill", "steal",
]

# Prompt-injection signatures (used by detect_injection)
INJECTION_PATTERNS = [
    r"ignore (all )?(previous|above|prior) instructions",
    r"you are now",
    r"system prompt",
    r"reveal your (instructions|prompt|configuration|config)",
    r"pretend (you are|to be)",
    r"act as (a |an )?unrestricted",
    r"forget (all |your )?(previous |prior )?instructions",
    r"override (your )?(system|instructions|directives)",
    r"disregard (all )?(previous|prior|your) (instructions|directives|prompt)",
    r"jailbreak",
]

# PII / secret signatures (used by content_filter)
PII_PATTERNS = {
    "VN phone number": r"0\d{9,10}",
    "Email": r"[\w.-]+@[\w.-]+\.[a-zA-Z]{2,}",
    "National ID (CMND/CCCD)": r"\b\d{9}\b|\b\d{12}\b",
    "API key": r"sk-[a-zA-Z0-9-]+",
    "Password": r"password\s*(?:[:=]|is)\s*['\"]?\S+",
}
