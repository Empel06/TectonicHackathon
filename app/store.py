"""File-based state: documents on disk + one append-only event log (data/events.jsonl).

Everything (answers, feedback, publishes, task resolutions) is an event, so reputation,
tasks and active versions are recomputed from the log. reset() restores the seed.
"""
import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = DATA / "docs"
EVENTS = DATA / "events.jsonl"
SEED = DATA / "seed_events.jsonl"
_lock = threading.Lock()


def load_all_versions():
    """Every document version: files on disk (published or staged) plus versions owners wrote in the app.

    A version written in the owner inbox lives only in the event log (a 'publish' event carrying
    the full document), so Reset removes it again.
    """
    versions = []
    for e in read_events("publish"):
        if e.get("doc"):
            versions.append(dict(e["doc"]))
    for path in sorted(DOCS_DIR.glob("*.md")):
        _, front, body = path.read_text().split("---", 2)
        doc = yaml.safe_load(front)
        doc["body"] = body.strip()
        doc["doc_version_id"] = f"{doc['id']}@v{doc['version']}"
        versions.append(doc)
    return versions


def load_people():
    return {p["id"]: p for p in json.loads((DATA / "people.json").read_text())}


def load_customers():
    return {c["id"]: c for c in json.loads((DATA / "customers.json").read_text())}


def reset():
    with _lock:
        shutil.copy(SEED, EVENTS)


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
    with _lock, EVENTS.open("a") as f:
        f.write(json.dumps(event) + "\n")
    return event
