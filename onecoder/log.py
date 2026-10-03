import json
import sys
import time
from pathlib import Path

from .gitutil import state_root


def event(root, kind, **fields):
    """Append an audit record. Never include file contents or matched secret values."""
    try:
        d = state_root(root) / ".onecoder"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "log.jsonl", "a") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), "event": kind, **fields}) + "\n")
    except OSError as e:
        print(f"onecoder: audit log write failed: {e}", file=sys.stderr)
