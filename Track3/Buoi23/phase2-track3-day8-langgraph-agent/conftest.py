"""Pytest bootstrap: load .env before test collection.

The smoke-test skip conditions read os.getenv() at collection time, so the API
key must be present in the environment before tests are collected. Loading the
.env here (rather than only inside llm.py) lets the LLM-backed smoke tests run
when a key is configured.
"""

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass
