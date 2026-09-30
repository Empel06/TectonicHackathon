"""Demo authentication: salted PBKDF2 password hashes, constant-time comparison, lockout.

Production replaces this with company SSO (OIDC); roles then come from the directory.
Passwords are never stored in plain text; data/users.json only holds salt + hash.
"""
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

USERS_FILE = Path(__file__).resolve().parent.parent / "data" / "users.json"
ITERATIONS = 200_000
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300
_failures = {}  # username -> (count, first_failure_time)


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return salt, digest


def _users():
    return {u["username"]: u for u in json.loads(USERS_FILE.read_text())}


def locked(username):
    count, since = _failures.get(username, (0, 0))
    if count >= MAX_FAILURES and time.time() - since < LOCKOUT_SECONDS:
        return True
    if count >= MAX_FAILURES:
        _failures.pop(username, None)
    return False


def authenticate(username, password):
    """Return the person id on success, else None. Same work is done for unknown users (no user enumeration)."""
    username = (username or "").strip().lower()
    if locked(username):
        return None
    user = _users().get(username)
    salt = user["salt"] if user else "00" * 16
    _, digest = hash_password(password or "", salt)
    if user and hmac.compare_digest(digest, user["hash"]):
        _failures.pop(username, None)
        return user["person_id"]
    count, since = _failures.get(username, (0, time.time()))
    _failures[username] = (count + 1, since)
    return None
