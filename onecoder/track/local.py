"""LocalTrackStore: Zero-dependency SQLite-backed tracking engine."""

import json
import os
import sqlite3
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
    def __init__(self, db_path: Optional[Path] = None, root: Optional[Path] = None):
        self.root = root or Path.cwd()
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".onecoder" / "track.db"
        _ensure_dir(self.db_path.parent)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    category TEXT,
                    status TEXT DEFAULT 'active',
                    tags TEXT,
                    repo_url TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS project_paths (
                    project_id TEXT,
                    workstation TEXT,
                    path TEXT,
                    repo_url TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (project_id, workstation)
                );

                CREATE TABLE IF NOT EXISTS sprints (
                    id TEXT PRIMARY KEY,
                    project TEXT,
                    name TEXT,
                    status TEXT DEFAULT 'planned',
                    starts_at TEXT,
                    ends_at TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS issues (
                    id TEXT PRIMARY KEY,
                    project TEXT,
                    sprint TEXT,
                    title TEXT,
                    status TEXT DEFAULT 'open',
                    labels TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS workstations (
                    workstation_id TEXT PRIMARY KEY,
                    hostname TEXT,
                    local_hostname TEXT,
                    os_type TEXT,
                    status TEXT DEFAULT 'active',
                    last_active_at TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workstation TEXT,
                    project TEXT,
                    event_type TEXT DEFAULT 'pulse',
                    summary TEXT,
                    git_branch TEXT,
                    git_commit TEXT,
                    dirty_files_count INTEGER DEFAULT 0,
                    dirty_files TEXT,
                    metadata TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT,
                    issue TEXT,
                    sprint TEXT,
                    note TEXT,
                    workstation TEXT,
                    git_branch TEXT,
                    git_commit TEXT,
                    created_at TEXT
                );
            """)

    # ------------------ Projects ------------------

    def list_projects(self, category: Optional[str] = None, status: Optional[str] = None, tag: Optional[str] = None) -> Dict[str, Any]:
        ws = get_workstation_id()
        query = "SELECT * FROM projects WHERE 1=1"
        params: List[Any] = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id ASC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            projects = []
            for r in rows:
                tags = json.loads(r["tags"]) if r["tags"] else []
                if tag and tag not in tags:
                    continue
                # Get mapped path for this workstation
                prow = conn.execute("SELECT path, repo_url FROM project_paths WHERE project_id = ? AND workstation = ?", (r["id"], ws)).fetchone()
                p = dict(r)
                p["tags"] = tags
                p["path"] = prow["path"] if prow else None
                if prow and prow["repo_url"]:
                    p["repo_url"] = prow["repo_url"]
                projects.append(p)
            return {"projects": projects}

    def update_project(self, id: str, name: Optional[str] = None, category: Optional[str] = None,
                       status: Optional[str] = None, tags: Optional[Any] = None, repo_url: Optional[str] = None,
                       path: Optional[str] = None, workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        now = _now_iso()
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM projects WHERE id = ?", (id,)).fetchone()
            if cur:
                tags_str = json.dumps(tags) if tags is not None else cur["tags"]
                conn.execute("""
                    UPDATE projects SET
                        name = COALESCE(?, name),
                        category = COALESCE(?, category),
                        status = COALESCE(?, status),
                        tags = ?,
                        repo_url = COALESCE(?, repo_url),
                        updated_at = ?
                    WHERE id = ?
                """, (name, category, status, tags_str, repo_url, now, id))
            else:
                tags_str = json.dumps(tags) if tags is not None else json.dumps([])
                conn.execute("""
                    INSERT INTO projects (id, name, category, status, tags, repo_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (id, name or id, category or "infrastructure", status or "active", tags_str, repo_url or "", now, now))

            if path is not None:
                conn.execute("""
                    INSERT INTO project_paths (project_id, workstation, path, repo_url, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, workstation) DO UPDATE SET
                        path = excluded.path,
                        repo_url = COALESCE(excluded.repo_url, project_paths.repo_url),
                        updated_at = excluded.updated_at
                """, (id, ws, str(path), repo_url or "", now))

            updated = conn.execute("SELECT * FROM projects WHERE id = ?", (id,)).fetchone()
            res = dict(updated)
            res["tags"] = json.loads(res["tags"]) if res["tags"] else []
            return res

    def register_project_path(self, project: str, path: Optional[str] = None, repo_url: Optional[str] = None,
                              workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        loc = Path(path or self.root).resolve()
        now = _now_iso()
        with self._get_conn() as conn:
            # Ensure project exists
            cur = conn.execute("SELECT * FROM projects WHERE id = ?", (project,)).fetchone()
            if not cur:
                conn.execute("""
                    INSERT INTO projects (id, name, category, status, tags, repo_url, created_at, updated_at)
                    VALUES (?, ?, 'infrastructure', 'active', '[]', ?, ?, ?)
                """, (project, project, repo_url or "", now, now))
            elif repo_url:
                conn.execute("UPDATE projects SET repo_url = ?, updated_at = ? WHERE id = ?", (repo_url, now, project))

            conn.execute("""
                INSERT INTO project_paths (project_id, workstation, path, repo_url, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, workstation) DO UPDATE SET
                    path = excluded.path,
                    repo_url = COALESCE(excluded.repo_url, project_paths.repo_url),
                    updated_at = excluded.updated_at
            """, (project, ws, str(loc), repo_url or "", now))

        return {"registered": True, "project": project, "workstation": ws, "path": str(loc), "repo_url": repo_url}

    def get_project_location(self, project: str, workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        with self._get_conn() as conn:
            proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project,)).fetchone()
            paths = conn.execute("SELECT workstation, path, repo_url FROM project_paths WHERE project_id = ?", (project,)).fetchall()
            ws_map = {r["workstation"]: r["path"] for r in paths}
            local_path = ws_map.get(ws)
            return {
                "project": project,
                "repo_url": proj["repo_url"] if proj else None,
                "local_path": local_path,
                "workstation_paths": ws_map,
            }

    # ------------------ Workstations ------------------

    def onboard_workstation(self, root_dir: Optional[str] = None, workstation_id: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation_id or get_workstation_id()
        now = _now_iso()
        import platform
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO workstations (workstation_id, hostname, local_hostname, os_type, status, last_active_at, created_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(workstation_id) DO UPDATE SET
                    last_active_at = excluded.last_active_at,
                    status = 'active'
            """, (ws, os.environ.get("HOSTNAME", ws), ws, platform.system(), now, now))

            # Scan root_dir for project paths
            scanned = []
            target_root = Path(root_dir or self.root).resolve()
            if target_root.exists() and target_root.is_dir():
                projects = conn.execute("SELECT id, name FROM projects").fetchall()
                for p in projects:
                    pid, pname = p["id"], p["name"]
                    candidates = [
                        target_root / pname,
                        target_root / pid,
                        target_root / "apps" / pname,
                        target_root / "tools" / pname,
                    ]
                    for cand in candidates:
                        if cand.exists() and cand.is_dir():
                            repo_url = None
                            git_config = cand / ".git" / "config"
                            if git_config.exists():
                                try:
                                    txt = git_config.read_text()
                                    for line in txt.splitlines():
                                        if "url =" in line:
                                            repo_url = line.split("=", 1)[1].strip()
                                            break
                                except Exception:
                                    pass
                            conn.execute("""
                                INSERT INTO project_paths (project_id, workstation, path, repo_url, updated_at)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(project_id, workstation) DO UPDATE SET
                                    path = excluded.path,
                                    repo_url = COALESCE(excluded.repo_url, project_paths.repo_url),
                                    updated_at = excluded.updated_at
                            """, (pid, ws, str(cand), repo_url or "", now))
                            scanned.append({"project": pid, "path": str(cand), "repo_url": repo_url})
                            break

            ws_row = conn.execute("SELECT * FROM workstations WHERE workstation_id = ?", (ws,)).fetchone()
            return {"workstation": dict(ws_row), "scanned_paths": scanned}

    def list_workstations(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM workstations ORDER BY last_active_at DESC").fetchall()
            return {"workstations": [dict(r) for r in rows]}

    def validate_workstations(self, workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        with self._get_conn() as conn:
            query = "SELECT * FROM workstations WHERE 1=1"
            params = []
            if workstation:
                query += " AND workstation_id = ?"
                params.append(workstation)
            rows = conn.execute(query, params).fetchall()
            validated = []
            for r in rows:
                item = dict(r)
                paths = conn.execute("SELECT project_id, path FROM project_paths WHERE workstation = ?", (r["workstation_id"],)).fetchall()
                item["registered_projects_count"] = len(paths)
                item["is_current"] = (r["workstation_id"] == ws)
                validated.append(item)
            return {"workstations": validated}

    # ------------------ Sprints ------------------

    def create_sprint(self, project: str, name: str, status: str = "planned",
                      starts_at: Optional[str] = None, ends_at: Optional[str] = None,
                      id: Optional[str] = None) -> Dict[str, Any]:
        sprint_id = id or f"sprint-{slugify(name)}-{int(time.time())}"
        now = _now_iso()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO sprints (id, project, name, status, starts_at, ends_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sprint_id, project, name, status, starts_at or now, ends_at or "", now, now))
            row = conn.execute("SELECT * FROM sprints WHERE id = ?", (sprint_id,)).fetchone()
            return dict(row)

    def update_sprint(self, id: str, name: Optional[str] = None, status: Optional[str] = None,
                      starts_at: Optional[str] = None, ends_at: Optional[str] = None) -> Dict[str, Any]:
        now = _now_iso()
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE sprints SET
                    name = COALESCE(?, name),
                    status = COALESCE(?, status),
                    starts_at = COALESCE(?, starts_at),
                    ends_at = COALESCE(?, ends_at),
                    updated_at = ?
                WHERE id = ?
            """, (name, status, starts_at, ends_at, now, id))
            row = conn.execute("SELECT * FROM sprints WHERE id = ?", (id,)).fetchone()
            if not row:
                raise ValueError(f"sprint {id} not found")
            return dict(row)

    def list_sprints(self, project: Optional[str] = None) -> Dict[str, Any]:
        with self._get_conn() as conn:
            query = "SELECT * FROM sprints WHERE 1=1"
            params = []
            if project:
                query += " AND project = ?"
                params.append(project)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return {"sprints": [dict(r) for r in rows]}

    # ------------------ Issues ------------------

    def create_issue(self, project: str, title: str, sprint: Optional[str] = None,
                     status: str = "open", labels: Optional[List[str]] = None,
                     id: Optional[str] = None) -> Dict[str, Any]:
        now = _now_iso()
        issue_id = id or f"issue-{int(time.time()*1000) % 1000000}"
        labels_json = json.dumps(labels or [])
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO issues (id, project, sprint, title, status, labels, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (issue_id, project, sprint or None, title, status, labels_json, now, now))
            row = conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
            res = dict(row)
            res["labels"] = json.loads(res["labels"]) if res["labels"] else []
            return res

    def update_issue(self, id: str, title: Optional[str] = None, sprint: Optional[str] = None,
                     status: Optional[str] = None, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        now = _now_iso()
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM issues WHERE id = ?", (id,)).fetchone()
            if not cur:
                raise ValueError(f"issue {id} not found")
            labels_str = json.dumps(labels) if labels is not None else cur["labels"]
            conn.execute("""
                UPDATE issues SET
                    title = COALESCE(?, title),
                    sprint = COALESCE(?, sprint),
                    status = COALESCE(?, status),
                    labels = ?,
                    updated_at = ?
                WHERE id = ?
            """, (title, sprint, status, labels_str, now, id))
            row = conn.execute("SELECT * FROM issues WHERE id = ?", (id,)).fetchone()
            res = dict(row)
            res["labels"] = json.loads(res["labels"]) if res["labels"] else []
            return res

    def list_issues(self, project: Optional[str] = None, sprint: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
        with self._get_conn() as conn:
            query = "SELECT * FROM issues WHERE 1=1"
            params = []
            if project:
                query += " AND project = ?"
                params.append(project)
            if sprint:
                query += " AND sprint = ?"
                params.append(sprint)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            out = []
            for r in rows:
                item = dict(r)
                item["labels"] = json.loads(item["labels"]) if item["labels"] else []
                out.append(item)
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

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO events (workstation, project, event_type, summary, git_branch, git_commit, dirty_files_count, dirty_files, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ws, project or None, event_type, summary, git_info["branch"], git_info["commit"], count, json.dumps(files), json.dumps(metadata or {}), now))

            # Touch workstation
            conn.execute("""
                INSERT INTO workstations (workstation_id, hostname, local_hostname, os_type, status, last_active_at, created_at)
                VALUES (?, ?, ?, 'Darwin', 'active', ?, ?)
                ON CONFLICT(workstation_id) DO UPDATE SET
                    last_active_at = excluded.last_active_at,
                    status = 'active'
            """, (ws, ws, ws, now, now))

            last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            row = conn.execute("SELECT * FROM events WHERE id = ?", (last_id,)).fetchone()
            res = dict(row)
            res["dirty_files"] = json.loads(res["dirty_files"]) if res["dirty_files"] else []
            res["metadata"] = json.loads(res["metadata"]) if res["metadata"] else {}
            return res

    def get_station_radar(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            ws_rows = conn.execute("SELECT * FROM workstations ORDER BY last_active_at DESC").fetchall()
            workstations = []
            now_ts = time.time()
            for w in ws_rows:
                item = dict(w)
                last_active = item.get("last_active_at")
                if last_active:
                    try:
                        # parse iso
                        dt = datetime.fromisoformat(last_active)
                        delta_sec = now_ts - dt.timestamp()
                        if delta_sec < 1800:
                            item["activity_status"] = "active"
                        elif delta_sec < 86400:
                            item["activity_status"] = "idle"
                        else:
                            item["activity_status"] = "offline"
                    except Exception:
                        item["activity_status"] = "unknown"
                else:
                    item["activity_status"] = "unknown"

                # Latest event
                last_ev = conn.execute("SELECT * FROM events WHERE workstation = ? ORDER BY created_at DESC LIMIT 1", (w["workstation_id"],)).fetchone()
                if last_ev:
                    ev_dict = dict(last_ev)
                    ev_dict["dirty_files"] = json.loads(ev_dict["dirty_files"]) if ev_dict["dirty_files"] else []
                    ev_dict["metadata"] = json.loads(ev_dict["metadata"]) if ev_dict["metadata"] else {}
                    item["latest_event"] = ev_dict
                else:
                    item["latest_event"] = None
                workstations.append(item)

            # Check conflicts: any project touched by >1 workstation in last 2 hours
            cutoff = datetime.fromtimestamp(now_ts - 7200, timezone.utc).isoformat()
            recent_events = conn.execute("SELECT DISTINCT project, workstation FROM events WHERE project IS NOT NULL AND created_at >= ?", (cutoff,)).fetchall()
            proj_stations: Dict[str, List[str]] = {}
            for r in recent_events:
                proj_stations.setdefault(r["project"], []).append(r["workstation"])

            conflicts = []
            for p, stations in proj_stations.items():
                if len(set(stations)) > 1:
                    conflicts.append({"project_id": p, "workstations": stations, "reason": "multiple workstations active in last 2 hours"})

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
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO progress (project, issue, sprint, note, workstation, git_branch, git_commit, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (project, issue or None, sprint or None, note, ws, git_info["branch"], git_info["commit"], now))
            last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            row = conn.execute("SELECT * FROM progress WHERE id = ?", (last_id,)).fetchone()
            return dict(row)

    def query_progress(self, project: Optional[str] = None, sprint: Optional[str] = None,
                       issue: Optional[str] = None, since: Optional[str] = None) -> Dict[str, Any]:
        with self._get_conn() as conn:
            query = "SELECT * FROM progress WHERE 1=1"
            params = []
            if project:
                query += " AND project = ?"
                params.append(project)
            if sprint:
                query += " AND sprint = ?"
                params.append(sprint)
            if issue:
                query += " AND issue = ?"
                params.append(issue)
            if since:
                query += " AND created_at >= ?"
                params.append(since)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return {"progress": [dict(r) for r in rows]}

    def log_session(self, project: str, task: str, summary: str, sessions_dir: str = "sessions",
                    issue: Optional[str] = None, sprint: Optional[str] = None, root: Optional[Path] = None) -> Dict[str, Any]:
        rt = root or self.root
        git_info = get_git_info(rt)
        git_status = get_git_status_details(rt)
        state_str = "dirty" if git_status["is_dirty"] else "clean"

        now = datetime.now()
        stamp = now.strftime("%Y%m%d-%H%M")
        sdir = (rt / sessions_dir).resolve()
        _ensure_dir(sdir)

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

        # Record progress entry
        progress_note = f"[session] {task}\n\nfile: {file_path}\n\n{summary}"
        prog = self.log_progress(project, progress_note, sprint=sprint, issue=issue, root=rt)
        return {"session_file": str(file_path), "progress": prog}
