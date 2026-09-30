"""Demo authentication: no credentials in the repository.

Accounts are the active people in data/people.json with a login-enabled role. Their password comes from the
DEMO_PASSWORD environment variable (a git-ignored .env file in the demo) and is hashed in memory at start-up with
a random salt (PBKDF2-SHA256). If DEMO_PASSWORD is not set, nobody can sign in: the app fails closed.

Production replaces this with company SSO (OIDC); roles then come from the directory.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

PEOPLE_FILE = Path(__file__).resolve().parent.parent / "data" / "people.json"
LOGIN_ROLES = {"consultant", "owner", "expert", "admin"}
ITERATIONS = 200_000
MAX_USERNAME = 64
MAX_PASSWORD = 256
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300
MAX_TRACKED = 10_000  # bound on remembered failed usernames (memory)
_failures = {}  # username -> (count, first_failure_time)
_DUMMY_SALT = secrets.token_hex(16)


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return salt, digest


_accounts = None
_accounts_for = None


def _users():
    """username -> {person_id, salt, hash}, built from DEMO_PASSWORD. Rebuilt if the variable changes."""
    global _accounts, _accounts_for
    password = os.environ.get("DEMO_PASSWORD", "")
    if _accounts_for != password:
        people = json.loads(PEOPLE_FILE.read_text())
        _accounts = {}
        if password:
            for p in people:
                if p["role"] in LOGIN_ROLES and not p["id"].startswith("emp-"):
                    salt, digest = hash_password(password)
                    _accounts[p["id"]] = {"person_id": p["id"], "salt": salt, "hash": digest}
        _accounts_for = password
    return _accounts


def configured():
    return bool(os.environ.get("DEMO_PASSWORD"))


def _prune(now):
    if len(_failures) > MAX_TRACKED:
        for name in [n for n, (_, since) in _failures.items() if now - since > LOCKOUT_SECONDS]:
            _failures.pop(name, None)
        while len(_failures) > MAX_TRACKED:  # still full: drop the oldest entries
            _failures.pop(next(iter(_failures)))


def locked(username):
    count, since = _failures.get(username, (0, 0))
    if count >= MAX_FAILURES and time.time() - since < LOCKOUT_SECONDS:
        return True
    if count >= MAX_FAILURES:
        _failures.pop(username, None)
    return False


def authenticate(username, password):
    """Return the person id on success, else None. Same work is done for unknown users (no user enumeration)."""
    username = (username or "").strip().lower()[:MAX_USERNAME]
    password = (password or "")[:MAX_PASSWORD]
    if not username or not password or locked(username):
        return None
    user = _users().get(username)
    _, digest = hash_password(password, user["salt"] if user else _DUMMY_SALT)
    if user and hmac.compare_digest(digest, user["hash"]):
        _failures.pop(username, None)
        return user["person_id"]
    now = time.time()
    count, since = _failures.get(username, (0, now))
    _failures[username] = (count + 1, since)
    _prune(now)
    return None


# Short-lived signed link tokens, so a source opened in a new tab keeps the signed-in user.
# The secret comes from the environment (production: a vault); otherwise a random one per process.
_SECRET = (os.environ.get("TRUST_LINK_SECRET") or secrets.token_hex(32)).encode()
LINK_TTL_SECONDS = 300


def make_link_token(person_id, now=None):
    expires = int((now or time.time()) + LINK_TTL_SECONDS)
    payload = f"{person_id}.{expires}"
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_link_token(token, now=None):
    """Return the person id for a valid, unexpired, untampered token, else None."""
    try:
        person_id, expires, sig = (token or "")[:200].rsplit(".", 2)
        expires_at = int(expires)
    except ValueError:
        return None
    expected = hmac.new(_SECRET, f"{person_id}.{expires}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected) or expires_at < (now or time.time()):
        return None
    return person_id
