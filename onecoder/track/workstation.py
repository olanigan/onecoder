"""Workstation identity and Git status detection helpers."""

import os
import platform
import re
import subprocess
from pathlib import Path

from .. import gitutil as g


def get_workstation_id() -> str:
    """Resolve active workstation identity."""
    if os.environ.get("WORKSTATION_ID"):
        return os.environ["WORKSTATION_ID"].strip()

    if platform.system() == "Darwin":
        try:
            r = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass

    try:
        r = subprocess.run(["hostname", "-s"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass

    node = platform.node()
    if node:
        return node.split(".")[0]

    return os.environ.get("HOSTNAME", "unknown-workstation")


def get_git_info(root=None) -> dict:
    root = root or Path.cwd()
    try:
        branch = g.current_branch(root)
        commit = g.head_sha(root)
        short_commit = commit[:7] if commit else None
        return {"branch": branch, "commit": short_commit}
    except Exception:
        return {"branch": None, "commit": None}


def get_git_status_details(root=None) -> dict:
    root = root or Path.cwd()
    try:
        rc, out, _ = g.git(root, "status", "--porcelain")
        if rc != 0:
            return {"is_dirty": False, "dirty_files_count": 0, "dirty_files": []}
        lines = [l for l in out.splitlines() if l.strip()]
        dirty_files = [l[3:].strip() for l in lines]
        return {
            "is_dirty": len(lines) > 0,
            "dirty_files_count": len(lines),
            "dirty_files": dirty_files[:20],
        }
    except Exception:
        return {"is_dirty": False, "dirty_files_count": 0, "dirty_files": []}


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "task"
