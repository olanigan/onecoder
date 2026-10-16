"""LocalTrackStore: Zero-dependency CSV-backed tracking engine."""

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .workstation import get_workstation_id, get_git_info, get_git_status_details, slugify


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


class LocalTrackStore:
    PROJECT_FIELDS = ["id", "name", "category", "status", "tags", "repo_url", "path", "created_at", "updated_at"]
    SPRINT_FIELDS = ["id", "project", "name", "status", "starts_at", "ends_at", "created_at", "updated_at"]
    ISSUE_FIELDS = ["id", "project", "sprint", "title", "status", "labels", "created_at", "updated_at"]
    WORKSTATION_FIELDS = ["workstation_id", "hostname", "local_hostname", "os_type", "status", "last_active_at", "created_at"]
    EVENT_FIELDS = ["id", "workstation", "project", "event_type", "summary", "git_branch", "git_commit", "dirty_files_count", "dirty_files", "metadata", "created_at"]
    PROGRESS_FIELDS = ["id", "project", "issue", "sprint", "note", "workstation", "git_branch", "git_commit", "created_at"]

    def __init__(self, track_dir: Optional[Path] = None, root: Optional[Path] = None, policy: Optional[dict] = None):
        self.root = root or Path.cwd()
        if track_dir:
            self.track_dir = Path(track_dir)
        else:
            cfg_dir = (policy or {}).get("track", {}).get("csv_dir") if isinstance(policy, dict) else None
            if cfg_dir:
                self.track_dir = (self.root / cfg_dir).resolve()
            else:
                self.track_dir = (self.root / ".onecoder" / "track").resolve()
        _ensure_dir(self.track_dir)
        self._init_csvs()

    def _file(self, name: str) -> Path:
        return self.track_dir / f"{name}.csv"

    def _read_rows(self, name: str, fields: List[str]) -> List[Dict[str, Any]]:
        path = self._file(name)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]

    def _write_rows(self, name: str, fields: List[str], rows: List[Dict[str, Any]]):
        path = self._file(name)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for r in rows:
                clean = {k: r.get(k, "") for k in fields}
                writer.writerow(clean)
        tmp.replace(path)

    def _append_row(self, name: str, fields: List[str], row: Dict[str, Any]):
        path = self._file(name)
        file_exists = path.exists() and path.stat().st_size > 0
        with open(path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if not file_exists:
                writer.writeheader()
            clean = {k: row.get(k, "") for k in fields}
            writer.writerow(clean)

    def _init_csvs(self):
        for name, fields in [
            ("projects", self.PROJECT_FIELDS),
            ("sprints", self.SPRINT_FIELDS),
            ("issues", self.ISSUE_FIELDS),
            ("workstations", self.WORKSTATION_FIELDS),
            ("events", self.EVENT_FIELDS),
            ("progress", self.PROGRESS_FIELDS),
        ]:
            p = self._file(name)
            if not p.exists():
                with open(p, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fields)
                    writer.writeheader()

    # ------------------ Projects ------------------

    def list_projects(self, category: Optional[str] = None, status: Optional[str] = None, tag: Optional[str] = None) -> Dict[str, Any]:
        rows = self._read_rows("projects", self.PROJECT_FIELDS)
        projects = []
        for r in rows:
            if category and r.get("category") != category:
                continue
            if status and r.get("status") != status:
                continue
            tags = []
            if r.get("tags"):
                try:
                    tags = json.loads(r["tags"])
                except Exception:
                    tags = [t.strip() for t in r["tags"].split(",") if t.strip()]
            if tag and tag not in tags:
                continue
            item = dict(r)
            item["tags"] = tags
            projects.append(item)
        projects.sort(key=lambda x: x.get("id", ""))
        return {"projects": projects}

    def update_project(self, id: str, name: Optional[str] = None, category: Optional[str] = None,
                       status: Optional[str] = None, tags: Optional[Any] = None, repo_url: Optional[str] = None,
                       path: Optional[str] = None, workstation: Optional[str] = None) -> Dict[str, Any]:
        now = _now_iso()
        rows = self._read_rows("projects", self.PROJECT_FIELDS)
        found = False
        updated_item: Dict[str, Any] = {}

        for r in rows:
            if r["id"] == id:
                found = True
                if name is not None: r["name"] = name
                if category is not None: r["category"] = category
                if status is not None: r["status"] = status
                if tags is not None:
                    r["tags"] = json.dumps(tags) if isinstance(tags, (list, dict)) else str(tags)
                if repo_url is not None: r["repo_url"] = repo_url
                if path is not None: r["path"] = str(path)
                r["updated_at"] = now
                updated_item = dict(r)
                break

        if not found:
            tags_str = json.dumps(tags) if isinstance(tags, (list, dict)) else (str(tags) if tags is not None else "[]")
            new_proj = {
                "id": id,
                "name": name or id,
                "category": category or "infrastructure",
                "status": status or "active",
                "tags": tags_str,
                "repo_url": repo_url or "",
                "path": str(path) if path is not None else "",
                "created_at": now,
                "updated_at": now,
            }
            rows.append(new_proj)
            updated_item = new_proj

        self._write_rows("projects", self.PROJECT_FIELDS, rows)
        res = dict(updated_item)
        if res.get("tags"):
            try: res["tags"] = json.loads(res["tags"])
            except Exception: res["tags"] = []
        else:
            res["tags"] = []
        return res

    def register_project_path(self, project: str, path: Optional[str] = None, repo_url: Optional[str] = None,
                              workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        loc = Path(path or self.root).resolve()
        res = self.update_project(id=project, path=str(loc), repo_url=repo_url, workstation=ws)
        return {"registered": True, "project": project, "workstation": ws, "path": str(loc), "repo_url": repo_url or res.get("repo_url")}

    def get_project_location(self, project: str, workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        rows = self._read_rows("projects", self.PROJECT_FIELDS)
        match = next((r for r in rows if r["id"] == project), None)
        local_path = match.get("path") if match else None
        repo_url = match.get("repo_url") if match else None
        ws_paths = {ws: local_path} if local_path else {}
        return {
            "project": project,
            "repo_url": repo_url,
            "local_path": local_path,
            "workstation_paths": ws_paths,
        }

    # ------------------ Workstations ------------------

    def onboard_workstation(self, root_dir: Optional[str] = None, workstation_id: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation_id or get_workstation_id()
        now = _now_iso()
        import platform

        rows = self._read_rows("workstations", self.WORKSTATION_FIELDS)
        found = False
        ws_row = {}
        for r in rows:
            if r["workstation_id"] == ws:
                found = True
                r["last_active_at"] = now
                r["status"] = "active"
                ws_row = dict(r)
                break

        if not found:
            ws_row = {
                "workstation_id": ws,
                "hostname": os.environ.get("HOSTNAME", ws),
                "local_hostname": ws,
                "os_type": platform.system(),
                "status": "active",
                "last_active_at": now,
                "created_at": now,
            }
            rows.append(ws_row)

        self._write_rows("workstations", self.WORKSTATION_FIELDS, rows)

        # Scan root_dir and update project paths
        scanned = []
        target_root = Path(root_dir or self.root).resolve()
        if target_root.exists() and target_root.is_dir():
            projs = self._read_rows("projects", self.PROJECT_FIELDS)
            for p in projs:
                pid, pname = p["id"], p.get("name") or p["id"]
                candidates = [
                    target_root / pname,
                    target_root / pid,
                    target_root / "apps" / pname,
                    target_root / "tools" / pname,
                ]
                for cand in candidates:
                    if cand.exists() and cand.is_dir():
                        repo_url = None
                        git_cfg = cand / ".git" / "config"
                        if git_cfg.exists():
                            try:
                                for line in git_cfg.read_text().splitlines():
                                    if "url =" in line:
                                        repo_url = line.split("=", 1)[1].strip()
                                        break
                            except Exception:
                                pass
                        self.update_project(pid, path=str(cand), repo_url=repo_url)
                        scanned.append({"project": pid, "path": str(cand), "repo_url": repo_url})
                        break

        return {"workstation": ws_row, "scanned_paths": scanned}

    def list_workstations(self) -> Dict[str, Any]:
        rows = self._read_rows("workstations", self.WORKSTATION_FIELDS)
        rows.sort(key=lambda x: x.get("last_active_at", ""), reverse=True)
        return {"workstations": rows}

    def validate_workstations(self, workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        rows = self._read_rows("workstations", self.WORKSTATION_FIELDS)
        projects = self._read_rows("projects", self.PROJECT_FIELDS)
        validated = []
        for r in rows:
            if workstation and r["workstation_id"] != workstation:
                continue
            item = dict(r)
            item["registered_projects_count"] = sum(1 for p in projects if p.get("path"))
            item["is_current"] = (r["workstation_id"] == ws)
            validated.append(item)
        return {"workstations": validated}

    # ------------------ Sprints ------------------

    def create_sprint(self, project: str, name: str, status: str = "planned",
                      starts_at: Optional[str] = None, ends_at: Optional[str] = None,
                      id: Optional[str] = None) -> Dict[str, Any]:
        sprint_id = id or f"sprint-{slugify(name)}-{int(time.time())}"
        now = _now_iso()
        sprint = {
            "id": sprint_id,
            "project": project,
            "name": name,
            "status": status or "planned",
            "starts_at": starts_at or now,
            "ends_at": ends_at or "",
            "created_at": now,
            "updated_at": now,
        }
        self._append_row("sprints", self.SPRINT_FIELDS, sprint)
        return sprint

    def update_sprint(self, id: str, name: Optional[str] = None, status: Optional[str] = None,
                      starts_at: Optional[str] = None, ends_at: Optional[str] = None) -> Dict[str, Any]:
        rows = self._read_rows("sprints", self.SPRINT_FIELDS)
        match = None
        for r in rows:
            if r["id"] == id:
                if name is not None: r["name"] = name
                if status is not None: r["status"] = status
                if starts_at is not None: r["starts_at"] = starts_at
                if ends_at is not None: r["ends_at"] = ends_at
                r["updated_at"] = _now_iso()
                match = dict(r)
                break
        if not match:
            raise ValueError(f"sprint {id} not found")
        self._write_rows("sprints", self.SPRINT_FIELDS, rows)
        return match

    def list_sprints(self, project: Optional[str] = None) -> Dict[str, Any]:
        rows = self._read_rows("sprints", self.SPRINT_FIELDS)
        if project:
            rows = [r for r in rows if r.get("project") == project]
        rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"sprints": rows}

    # ------------------ Issues ------------------

    def create_issue(self, project: str, title: str, sprint: Optional[str] = None,
                     status: str = "open", labels: Optional[List[str]] = None,
                     id: Optional[str] = None) -> Dict[str, Any]:
        now = _now_iso()
        issue_id = id or f"issue-{int(time.time()*1000) % 1000000}"
        labels_str = json.dumps(labels or [])
        issue = {
            "id": issue_id,
            "project": project,
            "sprint": sprint or "",
            "title": title,
            "status": status or "open",
            "labels": labels_str,
            "created_at": now,
            "updated_at": now,
        }
        self._append_row("issues", self.ISSUE_FIELDS, issue)
        res = dict(issue)
        res["labels"] = labels or []
        return res

    def update_issue(self, id: str, title: Optional[str] = None, sprint: Optional[str] = None,
                     status: Optional[str] = None, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        rows = self._read_rows("issues", self.ISSUE_FIELDS)
        match = None
        for r in rows:
            if r["id"] == id:
                if title is not None: r["title"] = title
                if sprint is not None: r["sprint"] = sprint
                if status is not None: r["status"] = status
                if labels is not None: r["labels"] = json.dumps(labels)
                r["updated_at"] = _now_iso()
                match = dict(r)
                break
        if not match:
            raise ValueError(f"issue {id} not found")
        self._write_rows("issues", self.ISSUE_FIELDS, rows)
        res = dict(match)
        if res.get("labels"):
            try: res["labels"] = json.loads(res["labels"])
            except Exception: res["labels"] = []
        else:
            res["labels"] = []
        return res

    def list_issues(self, project: Optional[str] = None, sprint: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
        rows = self._read_rows("issues", self.ISSUE_FIELDS)
        out = []
        for r in rows:
            if project and r.get("project") != project:
                continue
            if sprint and r.get("sprint") != sprint:
                continue
            if status and r.get("status") != status:
                continue
            item = dict(r)
            if item.get("labels"):
                try: item["labels"] = json.loads(item["labels"])
                except Exception: item["labels"] = []
            else:
                item["labels"] = []
            out.append(item)
        out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"issues": out}

    # ------------------ Events & Radar ------------------

    def emit_work_event(self, summary: str, project: Optional[str] = None, event_type: str = "pulse",
                        dirty_files: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None,
                        workstation: Optional[str] = None, root: Optional[Path] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        rt = root or self.root
        git_info = get_git_info(rt)
        git_status = get_git_status_details(rt)
        now = _now_iso()

        files = dirty_files if dirty_files is not None else git_status["dirty_files"]
        count = len(files)

        existing_events = self._read_rows("events", self.EVENT_FIELDS)
        next_id = max([int(r["id"]) for r in existing_events if r.get("id", "").isdigit()] or [0]) + 1

        ev = {
            "id": str(next_id),
            "workstation": ws,
            "project": project or "",
            "event_type": event_type or "pulse",
            "summary": summary,
            "git_branch": git_info["branch"] or "",
            "git_commit": git_info["commit"] or "",
            "dirty_files_count": str(count),
            "dirty_files": json.dumps(files),
            "metadata": json.dumps(metadata or {}),
            "created_at": now,
        }
        self._append_row("events", self.EVENT_FIELDS, ev)

        # Update workstation
        self.onboard_workstation(workstation_id=ws)

        res = dict(ev)
        res["dirty_files"] = files
        res["metadata"] = metadata or {}
        res["dirty_files_count"] = count
        return res

    def get_station_radar(self) -> Dict[str, Any]:
        ws_rows = self._read_rows("workstations", self.WORKSTATION_FIELDS)
        events = self._read_rows("events", self.EVENT_FIELDS)
        events.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        now_ts = time.time()
        workstations = []
        for w in ws_rows:
            item = dict(w)
            last_active = item.get("last_active_at")
            if last_active:
                try:
                    dt = datetime.fromisoformat(last_active)
                    delta = now_ts - dt.timestamp()
                    if delta < 1800: item["activity_status"] = "active"
                    elif delta < 86400: item["activity_status"] = "idle"
                    else: item["activity_status"] = "offline"
                except Exception:
                    item["activity_status"] = "unknown"
            else:
                item["activity_status"] = "unknown"

            latest = next((e for e in events if e.get("workstation") == w["workstation_id"]), None)
            if latest:
                ev_dict = dict(latest)
                try: ev_dict["dirty_files"] = json.loads(ev_dict.get("dirty_files", "[]"))
                except Exception: ev_dict["dirty_files"] = []
                try: ev_dict["metadata"] = json.loads(ev_dict.get("metadata", "{}"))
                except Exception: ev_dict["metadata"] = {}
                item["latest_event"] = ev_dict
            else:
                item["latest_event"] = None
            workstations.append(item)

        # Detect conflicts across stations on any project in last 2 hours
        cutoff = datetime.fromtimestamp(now_ts - 7200, timezone.utc).isoformat()
        proj_stations: Dict[str, List[str]] = {}
        for e in events:
            p = e.get("project")
            if p and e.get("created_at", "") >= cutoff:
                proj_stations.setdefault(p, []).append(e.get("workstation", ""))

        conflicts = []
        for p, stations in proj_stations.items():
            if len(set(stations)) > 1:
                conflicts.append({"project_id": p, "workstations": list(set(stations)), "reason": "multiple workstations active in last 2 hours"})

        return {"workstations": workstations, "conflicts": conflicts}

    def check_station_conflicts(self, project: str) -> Dict[str, Any]:
        radar = self.get_station_radar()
        ws = get_workstation_id()
        matching = next((c for c in radar.get("conflicts", []) if c.get("project_id") == project), None)
        if matching:
            return {
                "conflict_detected": True,
                "current_workstation": ws,
                "project": project,
                "details": matching,
            }
        return {
            "conflict_detected": False,
            "current_workstation": ws,
            "project": project,
            "status": "No active cross-station conflicts detected on this project.",
        }

    # ------------------ Progress & Sessions ------------------

    def log_progress(self, project: str, note: str, sprint: Optional[str] = None,
                     issue: Optional[str] = None, workstation: Optional[str] = None, root: Optional[Path] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        rt = root or self.root
        git_info = get_git_info(rt)
        now = _now_iso()

        existing = self._read_rows("progress", self.PROGRESS_FIELDS)
        next_id = max([int(r["id"]) for r in existing if r.get("id", "").isdigit()] or [0]) + 1

        prog = {
            "id": str(next_id),
            "project": project,
            "issue": issue or "",
            "sprint": sprint or "",
            "note": note,
            "workstation": ws,
            "git_branch": git_info["branch"] or "",
            "git_commit": git_info["commit"] or "",
            "created_at": now,
        }
        self._append_row("progress", self.PROGRESS_FIELDS, prog)
        return prog

    def query_progress(self, project: Optional[str] = None, sprint: Optional[str] = None,
                       issue: Optional[str] = None, since: Optional[str] = None) -> Dict[str, Any]:
        rows = self._read_rows("progress", self.PROGRESS_FIELDS)
        out = []
        for r in rows:
            if project and r.get("project") != project:
                continue
            if sprint and r.get("sprint") != sprint:
                continue
            if issue and r.get("issue") != issue:
                continue
            if since and r.get("created_at", "") < since:
                continue
            out.append(r)
        out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"progress": out}

    def log_session(self, project: str, task: str, summary: str, sessions_dir: str = "sessions",
                    issue: Optional[str] = None, sprint: Optional[str] = None, root: Optional[Path] = None) -> Dict[str, Any]:
        rt = root or self.root
        git_info = get_git_info(rt)
        git_status = get_git_status_details(rt)
        state_str = "dirty" if git_status["is_dirty"] else "clean"

        now = datetime.now()
        stamp = now.strftime("%Y%m%d-%H%M")
        sdir = (rt / sessions_dir).resolve()
        sdir.mkdir(parents=True, exist_ok=True)

        filename = f"{stamp}-{slugify(task)}.md"
        file_path = sdir / filename

        escaped_task = task.replace('"', '\\"')
        content = f"""---
session: {project}
date: {now.strftime('%Y-%m-%d')}
task: "{escaped_task}"
branch: {git_info['branch'] or 'unknown'}
state: {state_str}
---

## {task}

{summary}

---
*Captured via onecoder log_session at {now.isoformat()}.*
"""
        file_path.write_text(content, encoding="utf-8")

        progress_note = f"[session] {task}\n\nfile: {file_path}\n\n{summary}"
        prog = self.log_progress(project, progress_note, sprint=sprint, issue=issue, root=rt)
        return {"session_file": str(file_path), "progress": prog}
