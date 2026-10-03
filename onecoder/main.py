"""Harness-agnostic preflight over a diff. Every check reports pass|warn|fail|skipped; nothing is silently skipped.

The review check is fail-closed: a missing, stale, malformed or incomplete verdict is a fail.
"""

import fnmatch
import json
import re
import shlex
import subprocess
from pathlib import Path

from . import gitutil as g
from .gate import scan_secrets, _is_protected
from . import task as tasklib

AC_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s*(AC-\d+):\s*(.*\S)\s*$", re.M)
ILLEGAL = ["*.pem", "id_rsa*", "*.p12", "*.keystore", ".env", "*.env"]
VERDICTS = ("satisfied", "not_satisfied", "not_applicable")
RANK = {"pass": 0, "skipped": 0, "warn": 1, "fail": 2}


def _chk(name, status, detail):
    return {"check": name, "status": status, "detail": detail}


def diff_added(root, staged=False, base=None):
    """{path: [added lines]} including untracked files (git diff alone would miss them)."""
    args = ["diff", "--cached", "-U0"] if staged else ["diff", "-U0", base or "HEAD"]
    rc, out, err = g.git(root, *args)
    if rc != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {err}")
    files, cur = {}, None
    for line in out.splitlines():
        if line.startswith("+++ "):
            cur = None if line == "+++ /dev/null" else line[6:]
            if cur is not None:
                files.setdefault(cur, [])
        elif line.startswith("+") and cur is not None:
            files[cur].append(line[1:])
    if not staged:
        rc, out, _ = g.git(root, "ls-files", "--others", "--exclude-standard")
        for path in out.splitlines():
            try:
                files[path] = (Path(root) / path).read_text(errors="replace").splitlines()
            except OSError:
                files[path] = []
    return files


def resolve_base(root, task_state):
    if task_state and task_state.get("base"):
        base = task_state["base"]
    else:
        base = g.default_branch(root)
    rc, out, _ = g.git(root, "merge-base", "HEAD", base) if base else (1, "", "")
    return out if rc == 0 and out else "HEAD"


def check_review(root, tid, policy):
    if not policy["review"]["require_verdict"]:
        return _chk("review", "skipped", "review.require_verdict is false")
    if not tid:
        return _chk("review", "fail", "no task identified (use branch onecoder/<id>, ONECODER_TASK, or --task) so no verdict can be checked")
    try:
        brief = (tasklib.task_path(root, tid) / "brief.md").read_text()
    except OSError:
        return _chk("review", "fail", f"no brief for task {tid}")
    criteria = dict(AC_RE.findall(brief))
    if not criteria:
        return _chk("review", "fail", "brief has no acceptance criteria lines like '- [ ] AC-1: ...'")
    if any(t.startswith("<") for t in criteria.values()):
        return _chk("review", "fail", "brief still contains placeholder criteria")
    try:
        v = json.loads((tasklib.task_path(root, tid) / "review.json").read_text())
    except FileNotFoundError:
        return _chk("review", "fail", "no review.json: run the spec-review skill in a fresh context")
    except (OSError, json.JSONDecodeError) as e:
        return _chk("review", "fail", f"review.json unreadable: {e}")
    if v.get("task") != tid:
        return _chk("review", "fail", f"review.json is for task {v.get('task')!r}, not {tid!r}")
    head = g.head_sha(root)
    if v.get("head_sha") != head:
        return _chk("review", "fail", f"stale verdict: reviewed {str(v.get('head_sha'))[:8]}, HEAD is {str(head)[:8]}")
    if v.get("fresh_context") is not True:
        return _chk("review", "fail", "verdict must come from a fresh-context reviewer (fresh_context: true)")
    seen = {}
    for c in v.get("criteria") or []:
        cid, verdict, ev = c.get("id"), c.get("verdict"), (c.get("evidence") or "").strip()
        if verdict not in VERDICTS:
            return _chk("review", "fail", f"{cid}: verdict must be one of {VERDICTS}")
        if verdict in ("satisfied", "not_applicable") and not ev:
            return _chk("review", "fail", f"{cid}: '{verdict}' requires evidence")
        seen[cid] = verdict
    missing = sorted(set(criteria) - set(seen))
    if missing:
        return _chk("review", "fail", f"criteria without a verdict: {', '.join(missing)}")
    bad = sorted(k for k, x in seen.items() if x == "not_satisfied")
    if bad:
        return _chk("review", "fail", f"not satisfied: {', '.join(bad)}")
    return _chk("review", "pass", f"{len(criteria)} criteria covered at {head[:8]}")


def check_supply_chain(root, files, policy):
    sc = policy["supply_chain"]
    changed = sorted(p for p in files if any(fnmatch.fnmatch(p.split("/")[-1], m) or fnmatch.fnmatch(p, m) for m in sc["manifests"]))
    if not changed:
        return _chk("supply-chain", "pass", "no dependency manifests changed")
    note = f"manifests changed: {', '.join(changed)}"
    cmd = sc["scanner_cmd"].strip()
    if not cmd:
        level = {"warn": "warn", "fail": "fail", "ignore": "skipped"}[sc["on_missing_scanner"]]
        return _chk("supply-chain", level, f"{note}; no scanner_cmd configured, run the supply-chain-triage skill")
    try:
        r = subprocess.run(shlex.split(cmd), cwd=str(root), capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        return _chk("supply-chain", "fail", f"{note}; scanner failed to run: {e}")
    return _chk("supply-chain", "pass" if r.returncode == 0 else "fail", f"{note}; scanner exit {r.returncode}")


def run(root, policy, staged=False, base=None, task=None):
    tid = task or tasklib.current(root)
    state = None
    if tid:
        try:
            state = tasklib.load(root, tid)
        except tasklib.TaskError:
            pass
    files = diff_added(root, staged=staged, base=base or (None if staged else resolve_base(root, state)))
    checks = []

    added = sum(len(v) for v in files.values())
    lim = policy["gate"]["max_added_lines"]
    checks.append(_chk("size", "warn" if added > lim else "pass", f"{added} added lines (limit {lim})"))

    leaks = [f"{p} ({rule} line {n})" for p, lines in files.items() for rule, n in scan_secrets("\n".join(lines))]
    checks.append(_chk("secrets", "fail" if leaks else "pass", "; ".join(leaks) or "no credential patterns in added lines"))

    prot = [p for p in files if _is_protected(p, policy["gate"]["protected_paths"])]
    checks.append(_chk("protected-paths", "fail" if prot else "pass", ", ".join(prot) or "none touched"))

    illegal = [p for p in files if _is_protected(p, ILLEGAL)]
    checks.append(_chk("illegal-files", "fail" if illegal else "pass", ", ".join(illegal) or "none"))

    checks.append(check_supply_chain(root, files, policy))
    if not staged:
        checks.append(check_review(root, tid, policy))
    worst = max((RANK[c["status"]] for c in checks), default=0)
    return {"task": tid, "files": len(files), "added_lines": added, "checks": checks,
            "result": ["pass", "warn", "fail"][worst]}
