"""Environment detection -> recommended (mode, isolation), each with the reasons that produced it.

Mode:       yolo only when the environment is a sandbox AND nobody is attending, otherwise human-driver.
Isolation:  worktree is optional. It is chosen only when it solves a concrete collision.
"""

import os
import shutil
import sys
from pathlib import Path

from . import gitutil as g
from .policy import MODES, ISOLATIONS

SANDBOX_ENV = ("CI", "GITHUB_ACTIONS", "CODESPACES", "CLAUDE_CODE_REMOTE", "KUBERNETES_SERVICE_HOST", "GITPOD_WORKSPACE_ID")
TOOLS = ("tmux", "gh", "osv-scanner", "syft", "trivy", "gitleaks", "jq")
HARNESS_DIRS = {"claude": ".claude", "codex": ".codex", "pi": ".pi", "opencode": ".opencode", "cursor": ".cursor"}


def _truthy(v):
    return v not in (None, "", "0", "false", "False")


def sandbox_evidence(env, fs_exists=os.path.exists):
    if "ONECODER_SANDBOX" in env:  # explicit declaration beats guessing
        return ["ONECODER_SANDBOX"] if _truthy(env["ONECODER_SANDBOX"]) else []
    ev = [k for k in SANDBOX_ENV if _truthy(env.get(k))]
    if fs_exists("/.dockerenv"):
        ev.append("/.dockerenv")
    if _truthy(env.get("container")):
        ev.append("container")
    return ev


def attended(env, ttys=None):
    """Explicit signals first; a tty is the fallback. Returns (bool, reason)."""
    if "ONECODER_ATTENDED" in env:
        return _truthy(env["ONECODER_ATTENDED"]), "ONECODER_ATTENDED"
    if "CLAUDE_CODE_SESSION_ATTENDED" in env:
        return _truthy(env["CLAUDE_CODE_SESSION_ATTENDED"]), "CLAUDE_CODE_SESSION_ATTENDED"
    if _truthy(env.get("CI")):
        return False, "CI"
    if ttys is None:
        ttys = [s.isatty() for s in (sys.stdin, sys.stdout, sys.stderr)]
    return (any(ttys), "tty" if any(ttys) else "no tty")


def harness_hints(root, env, home=None):
    hints = []
    if _truthy(env.get("CLAUDECODE")):
        hints.append("claude (env)")
    home = Path(home or Path.home())
    for name, d in HARNESS_DIRS.items():
        if (Path(root) / d).exists() or (home / d).exists():
            hints.append(f"{name} (dir)")
    return hints


def git_facts(root):
    if not root or g.repo_root(root) is None:
        return {"is_repo": False}
    return {
        "is_repo": True,
        "branch": g.current_branch(root),
        "default_branch": g.default_branch(root),
        "dirty": g.is_dirty(root),
        "worktrees": g.worktree_count(root),
        "linked_worktree": g.in_linked_worktree(root),
    }


def active_tasks(root):
    d = g.state_root(root) / ".onecoder" / "tasks"
    return sorted(p.name for p in d.iterdir() if (p / "state.json").exists()) if d.exists() else []


def recommend_mode(sandbox, is_attended, policy, env):
    reasons = []
    req = env.get("ONECODER_MODE") or policy["modes"]["default"]
    if req not in MODES:
        raise ValueError(f"ONECODER_MODE must be one of {MODES}")
    if req == "auto":
        if sandbox and not is_attended:
            mode, why = "yolo", "sandboxed and unattended"
        else:
            mode, why = "human-driver", "attended or not sandboxed"
        reasons.append(f"auto: {why}")
    else:
        mode = req
        reasons.append(f"explicit: {req}")
    if mode == "yolo" and not sandbox and not policy["modes"]["allow_yolo_on_host"]:
        mode = "human-driver"
        reasons.append("yolo downgraded: not a sandbox and modes.allow_yolo_on_host is false")
    return mode, reasons


def recommend_isolation(facts, parallel, policy, env):
    reasons = []
    req = env.get("ONECODER_ISOLATION") or policy["isolation"]["default"]
    if req not in ISOLATIONS:
        raise ValueError(f"ONECODER_ISOLATION must be one of {ISOLATIONS}")
    if req != "auto":
        return req, [f"explicit: {req}"]
    if not facts.get("is_repo"):
        return "none", ["not a git repo"]
    if facts["linked_worktree"]:
        return "none", ["already inside a linked worktree"]
    if parallel:
        return "worktree", [f"{parallel} other task(s) active: isolate to avoid collisions"]
    if facts["dirty"]:
        return "worktree", ["working tree has uncommitted changes: do not mix them into the task"]
    on_default = facts["branch"] in (None, facts["default_branch"])
    if on_default:
        return "branch", ["on the default branch: work on a task branch"]
    return "none", [f"already on feature branch '{facts['branch']}' with a clean tree: the branch is the isolation"]


def profile(root, policy, env=None, ttys=None):
    env = dict(os.environ) if env is None else env
    sandbox = sandbox_evidence(env)
    is_att, att_why = attended(env, ttys)
    facts = git_facts(root)
    parallel = len(active_tasks(root)) if facts.get("is_repo") else 0
    mode, mreasons = recommend_mode(bool(sandbox), is_att, policy, env)
    iso, ireasons = recommend_isolation(facts, parallel, policy, env)
    return {
        "sandbox": bool(sandbox), "sandbox_evidence": sandbox,
        "attended": is_att, "attended_from": att_why,
        "git": facts, "active_tasks": parallel,
        "harness_hints": harness_hints(root, env) if root else [],
        "tools": {t: bool(shutil.which(t)) for t in TOOLS},
        "recommend": {"mode": mode, "mode_reasons": mreasons, "isolation": iso, "isolation_reasons": ireasons},
    }
