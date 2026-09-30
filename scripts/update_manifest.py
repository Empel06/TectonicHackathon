"""Record the SHA-256 of every reviewed document file in data/docs.manifest.json.

Run after a document change has been reviewed: python scripts/update_manifest.py
The app loads only files whose hash matches the manifest; tests fail if the manifest is out of date.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import store  # noqa: E402

manifest = {p.name: store.file_digest(p) for p in sorted(store.DOCS_DIR.glob("*.md"))}
store.MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
print(f"{len(manifest)} documents recorded in {store.MANIFEST.name}")
