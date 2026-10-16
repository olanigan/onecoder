"""CLI command implementations for project, sprint, issue, workstation, and radar tracking."""

import json
import sys
from pathlib import Path
from typing import Any

from .store import get_track_store
from .. import gitutil as g


def _get_root():
    return g.repo_root(Path.cwd()) or Path.cwd()


def _get_backend(a):
    if getattr(a, "remote", False):
        return "remote"
    if getattr(a, "local", False):
        return "local"
    return getattr(a, "backend", None)


def _store(a):
    root = _get_root()
    backend = _get_backend(a)
    return get_track_store(root=root, backend=backend)


# ------------------ Sprints ------------------

def cmd_sprint(a):
    store = _store(a)
    action = getattr(a, "action", "list")

    if action == "list":
        data = store.list_sprints(project=getattr(a, "project", None))
        if getattr(a, "json", False):
            print(json.dumps(data, indent=2))
            return 0
        sprints = data.get("sprints", [])
        if not sprints:
            print("No sprints found.")
            return 0
        print(f"{'ID':<32} {'PROJECT':<16} {'STATUS':<12} {'NAME'}")
        print("-" * 80)
        for s in sprints:
            print(f"{s['id']:<32} {s.get('project', ''):<16} {s.get('status', 'planned'):<12} {s.get('name', '')}")
        return 0

    elif action == "new":
        if not a.name:
            print("onecoder sprint new: error: name is required", file=sys.stderr)
            return 2
        proj = a.project or _get_root().name
        sp = store.create_sprint(
            project=proj,
            name=a.name,
            status=a.status or "planned",
            starts_at=a.starts_at,
            ends_at=a.ends_at,
            id=a.id
        )
        if getattr(a, "json", False):
            print(json.dumps(sp, indent=2))
        else:
            print(f"Created sprint: {sp['id']} [{sp['status']}] '{sp['name']}' (project: {sp['project']})")
        return 0

    elif action in ("update", "close"):
        target_id = a.id or getattr(a, "name", None)
        if not target_id:
            print(f"onecoder sprint {action}: error: id is required", file=sys.stderr)
            return 2
        a.id = target_id
        status = "completed" if action == "close" else getattr(a, "status", None)
        sp_name = a.name if (getattr(a, "name", None) and a.name != a.id) else None
        sp = store.update_sprint(
            id=a.id,
            name=sp_name,
            status=status,
            starts_at=getattr(a, "starts_at", None),
            ends_at=getattr(a, "ends_at", None)
        )
        if getattr(a, "json", False):
            print(json.dumps(sp, indent=2))
        else:
            print(f"Updated sprint: {sp['id']} [{sp.get('status')}] '{sp.get('name')}'")
        return 0


# ------------------ Issues ------------------

def cmd_issue(a):
    store = _store(a)
    action = getattr(a, "action", "list")

    if action == "list":
        data = store.list_issues(
            project=getattr(a, "project", None),
            sprint=getattr(a, "sprint", None),
            status=getattr(a, "status", None)
        )
        if getattr(a, "json", False):
            print(json.dumps(data, indent=2))
            return 0
        issues = data.get("issues", [])
        if not issues:
            print("No issues found.")
            return 0
        print(f"{'ID':<18} {'SPRINT':<24} {'STATUS':<12} {'TITLE'}")
        print("-" * 80)
        for iss in issues:
            print(f"{iss['id']:<18} {iss.get('sprint') or '-':<24} {iss.get('status', 'open'):<12} {iss.get('title', '')}")
        return 0

    elif action == "new":
        if not a.title:
            print("onecoder issue new: error: title is required", file=sys.stderr)
            return 2
        proj = a.project or _get_root().name
        labels = [l.strip() for l in a.labels.split(",")] if getattr(a, "labels", None) else []
        iss = store.create_issue(
            project=proj,
            title=a.title,
            sprint=getattr(a, "sprint", None),
            status=getattr(a, "status", "open") or "open",
            labels=labels,
            id=getattr(a, "id", None)
        )
        if getattr(a, "json", False):
            print(json.dumps(iss, indent=2))
        else:
            print(f"Created issue: {iss['id']} [{iss['status']}] '{iss['title']}' (project: {iss['project']})")
        return 0

    elif action in ("update", "close"):
        target_id = a.id or getattr(a, "title", None)
        if not target_id:
            print(f"onecoder issue {action}: error: id is required", file=sys.stderr)
            return 2
        a.id = target_id
        status = "closed" if action == "close" else getattr(a, "status", None)
        iss_title = a.title if (getattr(a, "title", None) and a.title != a.id) else None
        labels = [l.strip() for l in a.labels.split(",")] if getattr(a, "labels", None) else None
        iss = store.update_issue(
            id=a.id,
            title=iss_title,
            sprint=getattr(a, "sprint", None),
            status=status,
            labels=labels
        )
        if getattr(a, "json", False):
            print(json.dumps(iss, indent=2))
        else:
            print(f"Updated issue: {iss['id']} [{iss.get('status')}] '{iss.get('title')}'")
        return 0


# ------------------ Projects ------------------

def cmd_project(a):
    store = _store(a)
    action = getattr(a, "action", "list")

    if action == "list":
        data = store.list_projects(
            category=getattr(a, "category", None),
            status=getattr(a, "status", None),
            tag=getattr(a, "tag", None)
        )
        if getattr(a, "json", False):
            print(json.dumps(data, indent=2))
            return 0
        projects = data.get("projects", [])
        if not projects:
            print("No projects registered.")
            return 0
        print(f"{'ID':<24} {'CATEGORY':<20} {'STATUS':<10} {'PATH'}")
        print("-" * 80)
        for p in projects:
            print(f"{p['id']:<24} {p.get('category') or 'infrastructure':<20} {p.get('status', 'active'):<10} {p.get('path') or '-'}")
        return 0

    elif action == "register":
        proj_id = a.project or _get_root().name
        res = store.register_project_path(project=proj_id, path=getattr(a, "path", None), repo_url=getattr(a, "repo_url", None))
        if getattr(a, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print(f"Registered project {proj_id} on workstation {res['workstation']} at: {res['path']}")
        return 0

    elif action == "update":
        tags = [t.strip() for t in a.tags.split(",")] if getattr(a, "tags", None) else None
        p = store.update_project(
            id=a.id,
            name=getattr(a, "name", None),
            category=getattr(a, "category", None),
            status=getattr(a, "status", None),
            tags=tags,
            repo_url=getattr(a, "repo_url", None),
            path=getattr(a, "path", None)
        )
        if getattr(a, "json", False):
            print(json.dumps(p, indent=2))
        else:
            print(f"Updated project {p['id']}: status={p.get('status')} category={p.get('category')}")
        return 0

    elif action == "locate":
        loc = store.get_project_location(project=a.project)
        if getattr(a, "json", False):
            print(json.dumps(loc, indent=2))
        else:
            print(f"Project: {loc['project']}")
            print(f"Repo URL: {loc.get('repo_url') or '-'}")
            print(f"Local Path: {loc.get('local_path') or '-'}")
            ws_paths = loc.get("workstation_paths", {})
            if ws_paths:
                print("All Workstations:")
                for ws, p in ws_paths.items():
                    print(f"  - {ws}: {p}")
        return 0


# ------------------ Workstations & Radar ------------------

def cmd_station(a):
    store = _store(a)
    action = getattr(a, "action", "list")

    if action == "list":
        data = store.list_workstations()
        if getattr(a, "json", False):
            print(json.dumps(data, indent=2))
            return 0
        wss = data.get("workstations", [])
        print(f"{'WORKSTATION ID':<28} {'OS':<10} {'STATUS':<10} {'LAST ACTIVE'}")
        print("-" * 75)
        for w in wss:
            print(f"{w['workstation_id']:<28} {w.get('os_type', 'unknown'):<10} {w.get('status', 'active'):<10} {w.get('last_active_at', '-')}")
        return 0

    elif action == "onboard":
        res = store.onboard_workstation(root_dir=getattr(a, "root_dir", None), workstation_id=getattr(a, "station_id", None))
        if getattr(a, "json", False):
            print(json.dumps(res, indent=2))
        else:
            ws_info = res.get("workstation", {})
            ws_id = ws_info.get("workstation_id") if isinstance(ws_info, dict) else ws_info
            print(f"Workstation onboarded: {ws_id}")
            scanned = res.get("scanned_paths", [])
            print(f"Mapped {len(scanned)} project path(s).")
            for item in scanned:
                print(f"  - {item['project']} -> {item['path']}")
        return 0

    elif action == "validate":
        res = store.validate_workstations(workstation=getattr(a, "station", None))
        if getattr(a, "json", False):
            print(json.dumps(res, indent=2))
        else:
            for w in res.get("workstations", []):
                mark = "* (current)" if w.get("is_current") else ""
                print(f"{w['workstation_id']} {mark}: status={w.get('status')} projects={w.get('registered_projects_count', 0)}")
        return 0


def cmd_radar(a):
    store = _store(a)
    data = store.get_station_radar()
    if getattr(a, "json", False):
        print(json.dumps(data, indent=2))
        return 0

    print("=== CROSS-STATION RADAR ===")
    for w in data.get("workstations", []):
        act = w.get("activity_status", "unknown").upper()
        ev = w.get("latest_event")
        summary = f"({ev['event_type']}: {ev['summary']})" if ev else "No recent event"
        print(f"[{act:<7}] {w['workstation_id']} -> {summary}")

    conflicts = data.get("conflicts", [])
    if conflicts:
        print("\n⚠️ CONFLICT WARNINGS:")
        for c in conflicts:
            print(f"  - Project {c['project_id']}: active on multiple stations ({', '.join(c.get('workstations', []))})")
    else:
        print("\nNo cross-station conflicts detected.")
    return 0


def cmd_conflicts(a):
    store = _store(a)
    proj = a.project or _get_root().name
    res = store.check_station_conflicts(project=proj)
    if getattr(a, "json", False):
        print(json.dumps(res, indent=2))
        return 0 if not res.get("conflict_detected") else 1

    if res.get("conflict_detected"):
        print(f"⚠️ Conflict detected on project '{proj}': {res.get('details')}")
        return 1
    else:
        print(f"✓ No conflicts detected on project '{proj}'.")
        return 0


# ------------------ Events, Progress, Sessions ------------------

def cmd_pulse(a):
    store = _store(a)
    proj = a.project or _get_root().name
    ev = store.emit_work_event(
        summary=a.summary,
        project=proj,
        event_type=getattr(a, "type", "pulse") or "pulse"
    )
    if getattr(a, "json", False):
        print(json.dumps(ev, indent=2))
    else:
        print(f"pulse emitted: [{ev.get('event_type')}] '{ev.get('summary')}' (project={ev.get('project')}, branch={ev.get('git_branch')}, dirty={ev.get('dirty_files_count')})")
    return 0


def cmd_progress(a):
    store = _store(a)
    action = getattr(a, "action", "query")

    if action == "log":
        if not a.note:
            print("onecoder progress log: error: note is required", file=sys.stderr)
            return 2
        proj = a.project or _get_root().name
        res = store.log_progress(
            project=proj,
            note=a.note,
            sprint=getattr(a, "sprint", None),
            issue=getattr(a, "issue", None)
        )
        if getattr(a, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print(f"Progress logged for project {proj}: '{res.get('note')}'")
        return 0

    elif action in ("query", "list"):
        data = store.query_progress(
            project=getattr(a, "project", None),
            sprint=getattr(a, "sprint", None),
            issue=getattr(a, "issue", None),
            since=getattr(a, "since", None)
        )
        if getattr(a, "json", False):
            print(json.dumps(data, indent=2))
            return 0
        entries = data.get("progress", [])
        if not entries:
            print("No progress entries found.")
            return 0
        for e in entries:
            ws = e.get("workstation", "")
            br = e.get("git_branch") or "-"
            ts = e.get("created_at", "")
            print(f"[{ts}] {ws} ({br}):")
            print(f"  {e.get('note', '')}\n")
        return 0


def cmd_session(a):
    store = _store(a)
    proj = a.project or _get_root().name
    res = store.log_session(
        project=proj,
        task=a.task,
        summary=a.summary,
        sessions_dir=getattr(a, "dir", "sessions") or "sessions",
        issue=getattr(a, "issue", None),
        sprint=getattr(a, "sprint", None)
    )
    if getattr(a, "json", False):
        print(json.dumps(res, indent=2))
    else:
        print(f"Session written to: {res['session_file']}")
        print(f"Progress recorded for project: {proj}")
    return 0


def cmd_mcp(a):
    from ..mcp import run_stdio_server
    backend = _get_backend(a)
    run_stdio_server(backend=backend, root=_get_root())
    return 0
