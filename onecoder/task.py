"""Task identity is structural: branch `onecoder/<id>` (and, optionally, a worktree). Nothing is inferred from diffs."""

import json
import re
import time
from pathlib import Path

from . import gitutil as g

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,40}$")
BRIEF = """---
id: {id}
kind: ship          # ship = authorized change; scout = investigation, report only
---
# {id}

## Goal
<one paragraph: what and why>

## Acceptance criteria
<!-- One line each, ids AC-1.. The reviewer must give a verdict with evidence for every one. -->
- [ ] AC-1: <observable, checkable statement>
"""


class TaskError(Exception):
    pass


def tasks_dir(root):
    return g.state_root(root) / ".onecoder" / "tasks"


def task_path(root, tid):
    return tasks_dir(root) / tid


def load(root, tid):
    p = task_path(root, tid) / "state.json"
    if not p.exists():
        raise TaskError(f"no such task: {tid}")
    return json.loads(p.read_text())


def current(root, env=None):
    import os
    env = os.environ if env is None else env
    b = g.current_branch(root) or ""
    if b.startswith("onecoder/"):
        return b[len("onecoder/"):]
    return env.get("ONECODER_TASK") or None


def new(root, tid, mode, isolation, base=None):
    if not ID_RE.match(tid):
        raise TaskError(f"invalid task id {tid!r}: use [a-z0-9][a-z0-9._-]*, max 41 chars")
    if isolation not in ("none", "branch", "worktree"):
        raise TaskError(f"isolation must be resolved to none|branch|worktree, got {isolation!r}")
    root = Path(root)
    g.ensure_excluded(root)
    tdir = task_path(root, tid)
    if (tdir / "state.json").exists():
        raise TaskError(f"task {tid} already exists")
    base = base or g.default_branch(root) or "HEAD"
    branch = f"onecoder/{tid}"
    workdir = str(root)
    if isolation == "branch":
        rc, _, err = g.git(root, "switch", "-c", branch)
        if rc != 0:
            raise TaskError(f"git switch -c {branch} failed: {err}")
    elif isolation == "worktree":
        wt = g.state_root(root).parent / f"{g.state_root(root).name}.onecoder" / tid
        wt.parent.mkdir(parents=True, exist_ok=True)
        rc, _, err = g.git(root, "worktree", "add", "-b", branch, str(wt))
        if rc != 0:
            raise TaskError(f"git worktree add failed: {err}")
        workdir = str(wt)
    else:
        branch = g.current_branch(root)
    tdir.mkdir(parents=True)
    (tdir / "brief.md").write_text(BRIEF.format(id=tid))
    state = {"id": tid, "mode": mode, "isolation": isolation, "branch": branch, "workdir": workdir,
             "base": base, "base_sha": g.head_sha(root), "created": int(time.time())}
    (tdir / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    return state


def list_tasks(root):
    d = tasks_dir(root)
    out = []
    if d.exists():
        for p in sorted(d.iterdir()):
            if (p / "state.json").exists():
                out.append(json.loads((p / "state.json").read_text()))
    return out
