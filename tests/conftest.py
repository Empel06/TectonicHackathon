"""Test configuration: a random demo password per run (no credentials in the repository)."""
import os
import secrets

os.environ["DEMO_PASSWORD"] = TEST_PASSWORD = secrets.token_urlsafe(16)
os.environ.setdefault("DEMO_MODE", "true")
