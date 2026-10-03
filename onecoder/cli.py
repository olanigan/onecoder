"""onecoder: harness-agnostic governance CLI. Run `onecoder doctor` first."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import adapt, detect, gate, preflight, task as tasklib, policy as pol
from . import gitutil as g
from .log import event


def _root(cwd=None):
    return g.repo_root(cwd or os.getcwd()) or Path(cwd or os.getcwd())


def resolve_mode(root, policy, env=None):
    """ONECODER_MODE > current task's recorded mode > policy default > detection. yolo off-sandbox is downgraded."""
    env = os.environ if env is None else env
    tid = tasklib.current(root, env)
    if not env.get("ONECODER_MODE") and tid:
        try:
            return tasklib.load(root, tid)["mode"]
        except tasklib.TaskError:
            pass
    return detect.profile(root, policy, env=dict(env))["recommend"]["mode"]


def cmd_detect(a):
    root = _root()
    prof = detect.profile(root, pol.load(root))
    if a.json:
        print(json.dumps(prof, indent=2))
        return 0
    r = prof["recommend"]
    print(f"sandbox   : {prof['sandbox']} {prof['sandbox_evidence']}")
    print(f"attended  : {prof['attended']} (from {prof['attended_from']})")
    print(f"git       : {prof['git']}")
    print(f"harness   : {', '.join(prof['harness_hints']) or 'none detected'}")
    print(f"mode      : {r['mode']}   <- {'; '.join(r['mode_reasons'])}")
    print(f"isolation : {r['isolation']}   <- {'; '.join(r['isolation_reasons'])}")
    return 0


def cmd_mode(a):
    root = _root()
    print(resolve_mode(root, pol.load(root)))
    return 0


def cmd_task(a):
    root = _root()
    policy = pol.load(root)
    if a.action == "list":
        for t in tasklib.list_tasks(root):
            print(f"{t['id']:<24} {t['mode']:<13} {t['isolation']:<9} {t['branch']}")
        return 0
    if a.action == "current":
        print(tasklib.current(root) or "")
        return 0
    prof = detect.profile(root, policy)
    mode = a.mode or prof["recommend"]["mode"]
    if mode == "yolo" and not prof["sandbox"] and not policy["modes"]["allow_yolo_on_host"]:
        print("onecoder: yolo requires a sandbox (or modes.allow_yolo_on_host = true)", file=sys.stderr)
        return 2
    iso = a.isolation or prof["recommend"]["isolation"]
    try:
        st = tasklib.new(root, a.id, mode, iso)
    except tasklib.TaskError as e:
        print(f"onecoder: {e}", file=sys.stderr)
        return 2
    event(root, "task.new", task=a.id, mode=mode, isolation=iso)
    print(f"task {st['id']}: mode={mode} isolation={iso} branch={st['branch']}")
    print(f"workdir : {st['workdir']}")
    print(f"brief   : {tasklib.task_path(root, a.id) / 'brief.md'}  (fill in acceptance criteria)")
    return 0


def cmd_preflight(a):
    root = _root()
    try:
        rep = preflight.run(root, pol.load(root), staged=a.staged, base=a.base, task=a.task)
    except Exception as e:  # fail closed
        print(f"onecoder preflight: ERROR {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        for c in rep["checks"]:
            print(f"[{c['status']:<7}] {c['check']:<16} {c['detail']}")
        print(f"result: {rep['result']}  (task={rep['task']}, {rep['files']} files, +{rep['added_lines']})")
    event(root, "preflight", task=rep["task"], result=rep["result"])
    return 1 if rep["result"] == "fail" or (a.strict and rep["result"] == "warn") else 0


def cmd_finish(a):
    a.staged, a.base, a.strict, a.json = False, None, True, False
    rc = cmd_preflight(a)
    if rc == 0:
        print("handoff: ready for human review. onecoder never pushes or merges; you merge.")
    return rc


def _hook_out(decision, reason):
    if decision == "allow":
        return None  # no opinion: leave the harness's own permission flow intact
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}


def cmd_hook(a):
    """Reads a harness tool-call payload on stdin. Any failure -> deny (fail closed)."""
    root = None
    try:
        payload = json.load(sys.stdin)
        root = _root(payload.get("cwd"))
        policy = pol.load(root)
        mode = resolve_mode(root, policy)
        verdict = gate.evaluate(payload, policy, root)
        decision, reason = gate.decide(verdict, mode)
        event(root, "gate", tool=payload.get("tool_name"), mode=mode, level=verdict["level"],
              rules=[r["rule"] for r in verdict["reasons"]], decision=decision)
    except Exception as e:
        decision, reason = "deny", f"onecoder gate error (failing closed): {e}"
        if root:
            event(root, "gate.error", error=str(e))
    out = _hook_out(decision, reason)
    if out:
        print(json.dumps(out))
    return 0


def cmd_gate(a):
    root = _root()
    policy = pol.load(root)
    payload = json.load(sys.stdin)
    v = gate.evaluate(payload, policy, root)
    d, r = gate.decide(v, resolve_mode(root, policy))
    print(json.dumps({"verdict": v, "decision": d, "reason": r}, indent=2))
    return 0 if d != "deny" else 1


def cmd_adapt(a):
    root = _root()
    if a.target == "claude":
        if not a.write:
            print(json.dumps(adapt.claude_snippet(), indent=2))
            return 0
        path, changed = adapt.write_claude(root, shared=a.shared)
    else:
        try:
            path, changed = adapt.write_git(root)
        except RuntimeError as e:
            print(f"onecoder: {e}", file=sys.stderr)
            return 2
    print(f"{'wrote' if changed else 'already installed:'} {path}")
    return 0


def cmd_doctor(a):
    root = _root()
    ok = True
    try:
        p = pol.load(root)
        print("policy   : ok")
    except pol.PolicyError as e:
        print(f"policy   : INVALID ({e}); hooks will fail closed")
        return 1
    prof = detect.profile(root, p)
    for t, have in prof["tools"].items():
        print(f"tool     : {t:<12} {'yes' if have else 'no'}")
    if not p["supply_chain"]["scanner_cmd"]:
        print("scanner  : none configured (supply_chain.scanner_cmd); manifest changes will report on_missing_scanner="
              + p["supply_chain"]["on_missing_scanner"])
    print(f"recommend: mode={prof['recommend']['mode']} isolation={prof['recommend']['isolation']}")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="onecoder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("detect"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_detect)
    s = sub.add_parser("mode"); s.set_defaults(fn=cmd_mode)
    s = sub.add_parser("task")
    s.add_argument("action", choices=["new", "list", "current"]); s.add_argument("id", nargs="?")
    s.add_argument("--mode", choices=["human-driver", "yolo"]); s.add_argument("--isolation", choices=["none", "branch", "worktree"])
    s.set_defaults(fn=cmd_task)
    s = sub.add_parser("preflight")
    s.add_argument("--staged", action="store_true"); s.add_argument("--base"); s.add_argument("--task")
    s.add_argument("--strict", action="store_true"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_preflight)
    s = sub.add_parser("finish"); s.add_argument("task", nargs="?"); s.set_defaults(fn=cmd_finish)
    s = sub.add_parser("hook"); s.add_argument("harness", choices=["claude"]); s.set_defaults(fn=cmd_hook)
    s = sub.add_parser("gate"); s.set_defaults(fn=cmd_gate)
    s = sub.add_parser("adapt"); s.add_argument("target", choices=["claude", "git"])
    s.add_argument("--write", action="store_true"); s.add_argument("--shared", action="store_true"); s.set_defaults(fn=cmd_adapt)
    s = sub.add_parser("doctor"); s.set_defaults(fn=cmd_doctor)
    a = ap.parse_args(argv)
    if a.cmd == "task" and a.action == "new" and not a.id:
        ap.error("task new requires an id")
    try:
        return a.fn(a)
    except pol.PolicyError as e:
        print(f"onecoder: invalid policy: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"onecoder: {e}", file=sys.stderr)
        return 2

