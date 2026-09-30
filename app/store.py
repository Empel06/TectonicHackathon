"""File-based state: documents on disk + one append-only event log (data/events.jsonl).

Everything (answers, feedback, publishes, task resolutions) is an event, so reputation,
tasks and active versions are recomputed from the log. reset() restores the seed.
"""
import functools
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = DATA / "docs"
# runtime state lives outside the image's data folder so the container can mount it as a volume
EVENTS = Path(os.environ.get("TRUST_RUNTIME_DIR", DATA)) / "events.jsonl"
SEED = DATA / "seed_events.jsonl"
_lock = threading.Lock()


def load_all_versions():
    """Every document version: files on disk (published or staged) plus versions owners wrote in the app.

    A version written in the owner inbox lives only in the event log (a 'publish' event carrying
    the full document), so Reset removes it again.
    """
    versions = [dict(e["doc"]) for e in read_events("publish") if e.get("doc")]
    written = {v["doc_version_id"] for v in versions}  # owner text replaces a staged draft of the same version
    signature = tuple((p.name, p.stat().st_mtime_ns) for p in sorted(DOCS_DIR.glob("*.md")))
    versions += [dict(d) for d in _parse_files(signature) if d["doc_version_id"] not in written]
    return versions


@functools.lru_cache(maxsize=4)
def _parse_files(signature):
    """Parse the document files once; the cache key changes when any file is added, removed or edited."""
    docs = []
    for name, _ in signature:
        _, front, body = (DOCS_DIR / name).read_text().split("---", 2)
        doc = yaml.safe_load(front)
        doc["body"] = body.strip()
        doc["doc_version_id"] = f"{doc['id']}@v{doc['version']}"
        docs.append(doc)
    return tuple(docs)


def load_people():
    return {p["id"]: p for p in json.loads((DATA / "people.json").read_text())}


def load_customers():
    return {c["id"]: c for c in json.loads((DATA / "customers.json").read_text())}


GENESIS = "0" * 64


def _chain_hash(prev_hash, event):
    """Hash of the previous event + this event's content: editing any line breaks every hash after it."""
    body = {k: v for k, v in event.items() if k not in ("hash", "prev_hash")}
    return hashlib.sha256((prev_hash + json.dumps(body, sort_keys=True)).encode()).hexdigest()


def reset():
    """Restore the seeded history, re-chaining it so the audit log starts intact."""
    prev, lines = GENESIS, []
    for line in SEED.read_text().splitlines():
        if line.strip():
            event = json.loads(line)
            event.setdefault("type", "feedback")
            event["prev_hash"], event["hash"] = prev, _chain_hash(prev, event)
            prev = event["hash"]
            lines.append(json.dumps(event))
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        EVENTS.write_text("\n".join(lines) + "\n")


def verify_chain():
    """Return (ok, index_of_first_bad_event or None, total)."""
    if not EVENTS.exists():
        reset()
    prev = GENESIS
    lines = [line for line in EVENTS.read_text().splitlines() if line.strip()]
    for i, line in enumerate(lines):
        event = json.loads(line)
        if event.get("prev_hash") != prev or event.get("hash") != _chain_hash(prev, event):
            return False, i, len(lines)
        prev = event["hash"]
    return True, None, len(lines)


def simulate_tampering():
    """Demo only: silently change one stored event, the way an insider editing the file would."""
    lines = EVENTS.read_text().splitlines()
    event = json.loads(lines[1])
    event["reason_code"] = "trusted_used" if event.get("reason_code") != "trusted_used" else "incorrect"
    lines[1] = json.dumps(event)
    EVENTS.write_text("\n".join(lines) + "\n")


def read_events(type_=None):
    if not EVENTS.exists():
        reset()
    with _lock:
        lines = EVENTS.read_text().splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    for e in events:
        e.setdefault("type", "feedback")
    return [e for e in events if type_ is None or e["type"] == type_]


def append_event(event):
    event = {"id": f"{event['type'][:3]}-{uuid.uuid4().hex[:8]}",
             "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event}
    if not EVENTS.exists():
        reset()
    with _lock:
        lines = [line for line in EVENTS.read_text().splitlines() if line.strip()]
        prev = json.loads(lines[-1]).get("hash", GENESIS) if lines else GENESIS
        event["prev_hash"], event["hash"] = prev, _chain_hash(prev, event)
        with EVENTS.open("a") as f:
            f.write(json.dumps(event) + "\n")
    return event
