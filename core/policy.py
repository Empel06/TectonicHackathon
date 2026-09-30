"""Loads the versioned trust policy (config/policy.yaml). The trust core reads its thresholds from here."""
from pathlib import Path

import yaml

POLICY_FILE = Path(__file__).resolve().parent.parent / "config" / "policy.yaml"
POLICY = yaml.safe_load(POLICY_FILE.read_text())
