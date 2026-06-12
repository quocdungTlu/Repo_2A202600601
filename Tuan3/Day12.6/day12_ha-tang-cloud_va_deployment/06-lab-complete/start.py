"""Startup wrapper — captures import errors for debugging."""
import os
import sys
import traceback

print("=== startup begin ===", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"PORT: {os.getenv('PORT', 'not set')}", flush=True)
print(f"ENVIRONMENT: {os.getenv('ENVIRONMENT', 'not set')}", flush=True)
print(f"PYTHONPATH: {os.getenv('PYTHONPATH', 'not set')}", flush=True)
print(f"CWD: {os.getcwd()}", flush=True)

try:
    import uvicorn
    print("uvicorn imported OK", flush=True)
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting uvicorn on port {port}...", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
except Exception as exc:
    print(f"STARTUP ERROR: {exc}", flush=True)
    traceback.print_exc()
    sys.exit(1)
