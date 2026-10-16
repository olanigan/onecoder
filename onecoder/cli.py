"""onecoder CLI entry point. Harness-agnostic governance, quality gates, and tracking."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import adapt, detect, gate, preflight, task as tasklib, policy as pol
from . import gitutil as g
from .log import event
from .track import cli as track_cli
from .track.store import get_track_store


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

    # Optional issue enrichment
    if getattr(a, "issue", None):
        try:
            store = get_track_store(root=root)
            issues_data = store.list_issues(project=root.name)
            issue = next((i for i in issues_data.get("issues", []) if i["id"] == a.issue), None)
            if issue:
                brief_path = tasklib.task_path(root, a.id) / "brief.md"
                content = f"""---
id: {a.id}
issue: {issue['id']}
kind: ship
---
# {a.id}: {issue['title']}

## Goal
{issue['title']}

## Acceptance criteria
<!-- One line each, ids AC-1.. The reviewer must give a verdict with evidence for every one. -->
- [ ] AC-1: <observable, checkable statement>
"""
                brief_path.write_text(content)
        except Exception:
            pass

    # Optional auto-pulse
    if policy.get("track", {}).get("auto_pulse_on_task"):
        try:
            store = get_track_store(root=root)
            store.emit_work_event(f"Started task {a.id}", project=root.name, event_type="session_start", root=root)
        except Exception:
            pass

    event(root, "task.new", task=a.id, mode=mode, isolation=iso)
    print(f"task {st['id']}: mode={mode} isolation={iso} branch={st['branch']}")
    print(f"workdir : {st['workdir']}")
    print(f"brief   : {tasklib.task_path(root, a.id) / 'brief.md'}  (fill in acceptance criteria)")
    return 0


def cmd_preflight(a):
    root = _root()
    policy = pol.load(root)

    # Optional conflict preflight check
    if policy.get("track", {}).get("auto_check_conflicts"):
        try:
            store = get_track_store(root=root)
            c = store.check_station_conflicts(project=root.name)
            if c.get("conflict_detected"):
                print(f"onecoder preflight: WARN cross-station conflict detected on {root.name}: {c.get('details')}", file=sys.stderr)
        except Exception:
            pass

    try:
        rep = preflight.run(root, policy, staged=a.staged, base=a.base, task=a.task)
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
        root = _root()
        policy = pol.load(root)
        if policy.get("track", {}).get("auto_pulse_on_task"):
            try:
                store = get_track_store(root=root)
                store.emit_work_event(f"Completed task {a.task or tasklib.current(root) or 'task'}", project=root.name, event_type="checkpoint", root=root)
            except Exception:
                pass
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

    # Doctor check for tracking store
    try:
        store = get_track_store(root=root)
        backend_name = "remote" if hasattr(store, "secret") and store.secret else "local"
        print(f"track    : ok (backend={backend_name})")
    except Exception as e:
        print(f"track    : warning ({e})")

    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="onecoder")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # Core governance commands
    s = sub.add_parser("detect"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_detect)
    s = sub.add_parser("mode"); s.set_defaults(fn=cmd_mode)
    s = sub.add_parser("task")
    s.add_argument("action", choices=["new", "list", "current"]); s.add_argument("id", nargs="?")
    s.add_argument("--mode", choices=["human-driver", "yolo"]); s.add_argument("--isolation", choices=["none", "branch", "worktree"])
    s.add_argument("--issue", help="Associate task with an issue id")
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

    # Tracking & Agile commands
    def _add_mode_flags(parser):
        parser.add_argument("--local", action="store_true", help="Force local SQLite storage")
        parser.add_argument("--remote", action="store_true", help="Force Cloudflare remote storage")
        parser.add_argument("--json", action="store_true", help="Output JSON")

    # Sprint
    s = sub.add_parser("sprint", help="Sprint lifecycle management")
    s.add_argument("action", nargs="?", default="list", choices=["list", "new", "update", "close"])
    s.add_argument("name", nargs="?", help="Sprint name for 'new'")
    s.add_argument("--id", help="Sprint ID")
    s.add_argument("--project", "-p", help="Project ID")
    s.add_argument("--status", choices=["planned", "active", "completed"])
    s.add_argument("--starts-at", help="Start date (ISO)")
    s.add_argument("--ends-at", help="End date (ISO)")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_sprint)

    # Issue
    s = sub.add_parser("issue", help="Issue and story management")
    s.add_argument("action", nargs="?", default="list", choices=["list", "new", "update", "close"])
    s.add_argument("title", nargs="?", help="Issue title for 'new'")
    s.add_argument("--id", help="Issue ID")
    s.add_argument("--project", "-p", help="Project ID")
    s.add_argument("--sprint", "-s", help="Sprint ID")
    s.add_argument("--status", choices=["open", "in_progress", "closed"])
    s.add_argument("--labels", "-l", help="Comma-separated labels")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_issue)

    # Project
    s = sub.add_parser("project", help="Tracked project catalog")
    s.add_argument("action", nargs="?", default="list", choices=["list", "register", "update", "locate"])
    s.add_argument("project", nargs="?", help="Project ID")
    s.add_argument("--id", help="Project ID for update")
    s.add_argument("--name", help="Display name")
    s.add_argument("--category", choices=["monetized_app", "productized_template", "working_prototype", "experiment", "infrastructure"])
    s.add_argument("--status", choices=["active", "archived", "paused"])
    s.add_argument("--tags", help="Comma-separated tags")
    s.add_argument("--tag", help="Filter by tag")
    s.add_argument("--path", help="Local filesystem path")
    s.add_argument("--repo-url", help="GitHub repository URL")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_project)

    # Station
    s = sub.add_parser("station", help="Cross-workstation management")
    s.add_argument("action", nargs="?", default="list", choices=["list", "onboard", "validate"])
    s.add_argument("--root-dir", help="Root directory to scan for onboarding")
    s.add_argument("--station-id", help="Workstation ID")
    s.add_argument("--station", help="Target workstation for validate")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_station)

    # Radar & Conflicts
    s = sub.add_parser("radar", help="Cross-workstation activity radar")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_radar)

    s = sub.add_parser("conflicts", help="Check for cross-station conflicts on project")
    s.add_argument("--project", "-p", help="Project ID")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_conflicts)

    # Pulse
    s = sub.add_parser("pulse", help="Broadcast real-time work event")
    s.add_argument("summary", help="Event description")
    s.add_argument("--project", "-p", help="Project ID")
    s.add_argument("--type", "-t", choices=["pulse", "checkpoint", "session_start", "handoff", "error"], default="pulse")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_pulse)

    # Progress
    s = sub.add_parser("progress", help="Progress notes audit trail")
    s.add_argument("action", nargs="?", default="query", choices=["query", "log", "list"])
    s.add_argument("note", nargs="?", help="Progress note content")
    s.add_argument("--project", "-p", help="Project ID")
    s.add_argument("--sprint", "-s", help="Sprint ID")
    s.add_argument("--issue", "-i", help="Issue ID")
    s.add_argument("--since", help="ISO timestamp filter")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_progress)

    # Session
    s = sub.add_parser("session", help="Session markdown log & progress entry")
    s.add_argument("action", choices=["log"])
    s.add_argument("task", help="Short task title")
    s.add_argument("summary", help="Full markdown body of session log")
    s.add_argument("--project", "-p", help="Project ID")
    s.add_argument("--sprint", "-s", help="Sprint ID")
    s.add_argument("--issue", "-i", help="Issue ID")
    s.add_argument("--dir", "-d", default="sessions", help="Directory to write session file")
    _add_mode_flags(s)
    s.set_defaults(fn=track_cli.cmd_session)

    # MCP server command
    s = sub.add_parser("mcp", help="Run MCP stdio server")
    s.add_argument("--backend", choices=["auto", "local", "remote"], default="auto", help="Storage backend to use")
    s.set_defaults(fn=track_cli.cmd_mcp)

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
