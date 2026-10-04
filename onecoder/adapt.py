"""Adapters. The core is harness-agnostic; an adapter only wires a harness's hook point to `onecoder hook`/`onecoder preflight`.

claude : PreToolUse hook (Bash|Write|Edit|MultiEdit) -> `onecoder hook claude`
git    : pre-commit hook -> `onecoder preflight --staged` (works under any harness, including ones with no hook API)
"""

import json
import os
import stat
from pathlib import Path

from . import gitutil as g
from .policy import ONECODER_HOME

MARK = "# onecoder-managed"
CLAUDE_MATCHER = "Bash|Write|Edit|MultiEdit"


def _bin():
    return str(ONECODER_HOME / "bin" / "onecoder")


def claude_snippet():
    return {"hooks": {"PreToolUse": [{"matcher": CLAUDE_MATCHER, "hooks": [{"type": "command", "command": f"{_bin()} hook claude"}]}]}}


def merge_claude(existing):
    out = dict(existing)
    hooks = out.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    cmd = f"{_bin()} hook claude"
    for entry in pre:
        if any(h.get("command") == cmd for h in entry.get("hooks", [])):
            return out, False
    pre.append(claude_snippet()["hooks"]["PreToolUse"][0])
    return out, True


def write_claude(root, shared=False):
    path = Path(root) / ".claude" / ("settings.json" if shared else "settings.local.json")
    cur = json.loads(path.read_text()) if path.exists() else {}
    merged, changed = merge_claude(cur)
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2) + "\n")
    return path, changed


def write_git(root):
    rc, out, _ = g.git(root, "rev-parse", "--path-format=absolute", "--git-path", "hooks/pre-commit")
    if rc != 0:
        raise RuntimeError("not a git repository")
    path = Path(out)
    if path.exists() and MARK not in path.read_text():
        raise RuntimeError(f"{path} exists and is not onecoder-managed; refusing to overwrite")
    body = f"#!/bin/sh\n{MARK}\nexec \"{_bin()}\" preflight --staged\n"
    changed = not path.exists() or path.read_text() != body
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path, changed
