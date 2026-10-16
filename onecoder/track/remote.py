"""RemoteTrackClient: Zero-dependency Cloudflare Edge D1 tracking client."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .workstation import get_workstation_id, get_git_info, get_git_status_details, slugify


class RemoteTrackError(Exception):
    pass


class RemoteTrackClient:
    def __init__(self, endpoint: Optional[str] = None, secret: Optional[str] = None, root: Optional[Path] = None):
        self.endpoint = (endpoint or os.environ.get("TRACK_API_ENDPOINT") or "https://apps.lanig.workers.dev").rstrip("/")
        self.secret = secret or os.environ.get("TRACK_PUSH_SECRET") or os.environ.get("ONECODER_TRACK_SECRET")
        self.root = root or Path.cwd()

    def _api(self, path: str, method: str = "GET", body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.secret:
            raise RemoteTrackError("TRACK_PUSH_SECRET or ONECODER_TRACK_SECRET is not set; remote calls require authentication")

        qs = ""
        if params:
            filtered = {k: str(v) for k, v in params.items() if v is not None}
            if filtered:
                qs = "?" + urllib.parse.urlencode(filtered)

        url = f"{self.endpoint}{path}{qs}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.secret}",
            "User-Agent": "onecoder/track-client",
        }

        data_bytes = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return {}
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RemoteTrackError(f"track API {e.code}: {err_body}") from e
        except urllib.error.URLError as e:
            raise RemoteTrackError(f"track API network error: {e.reason}") from e

    # ------------------ Projects ------------------

    def list_projects(self, category: Optional[str] = None, status: Optional[str] = None, tag: Optional[str] = None) -> Dict[str, Any]:
        return self._api("/api/track/projects", params={"category": category, "status": status, "tag": tag})

    def update_project(self, id: str, name: Optional[str] = None, category: Optional[str] = None,
                       status: Optional[str] = None, tags: Optional[Any] = None, repo_url: Optional[str] = None,
                       path: Optional[str] = None, workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        payload: Dict[str, Any] = {"workstation": ws}
        if name is not None: payload["name"] = name
        if category is not None: payload["category"] = category
        if status is not None: payload["status"] = status
        if tags is not None: payload["tags"] = tags
        if repo_url is not None: payload["repo_url"] = repo_url
        if path is not None: payload["path"] = str(path)
        return self._api(f"/api/track/projects/{id}", method="PATCH", body=payload)

    def register_project_path(self, project: str, path: Optional[str] = None, repo_url: Optional[str] = None,
                              workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        local_path = str(Path(path or self.root).resolve())
        return self._api(f"/api/track/projects/{project}/path", method="POST",
                         body={"workstation": ws, "path": local_path, "repo_url": repo_url})

    def get_project_location(self, project: str, workstation: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        return self._api(f"/api/track/projects/{project}/location", params={"workstation": ws})

    # ------------------ Workstations ------------------

    def onboard_workstation(self, root_dir: Optional[str] = None, workstation_id: Optional[str] = None) -> Dict[str, Any]:
        ws = workstation_id or get_workstation_id()
        import platform
        onboard_res = self._api("/api/track/workstations/onboard", method="POST", body={
            "workstation_id": ws,
            "hostname": os.environ.get("HOSTNAME", ws),
            "local_hostname": ws,
            "os_type": platform.system(),
        })

        # Scan root_dir and bind known projects
        target_root = Path(root_dir or self.root).resolve()
        scanned = []
        try:
            projects_data = self._api("/api/track/projects")
            projects = projects_data.get("projects", [])
            for proj in projects:
                pid, pname = proj["id"], proj.get("name", proj["id"])
                for cand in [target_root / pname, target_root / pid, target_root / "apps" / pname, target_root / "tools" / pname]:
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
                        self._api(f"/api/track/projects/{pid}/path", method="POST", body={"workstation": ws, "path": str(cand)})
                        if repo_url:
                            self._api(f"/api/track/projects/{pid}", method="PATCH", body={"repo_url": repo_url})
                        scanned.append({"project": pid, "path": str(cand), "repo_url": repo_url})
                        break
        except Exception:
            pass

        return {"workstation": onboard_res.get("workstation", ws), "scanned_paths": scanned}

    def list_workstations(self) -> Dict[str, Any]:
        return self._api("/api/track/workstations")

    def validate_workstations(self, workstation: Optional[str] = None) -> Dict[str, Any]:
        return self._api("/api/track/workstations/validate", params={"workstation": workstation})

    # ------------------ Sprints ------------------

    def create_sprint(self, project: str, name: str, status: str = "planned",
                      starts_at: Optional[str] = None, ends_at: Optional[str] = None,
                      id: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"project": project, "name": name, "status": status}
        if id: payload["id"] = id
        if starts_at: payload["starts_at"] = starts_at
        if ends_at: payload["ends_at"] = ends_at
        return self._api("/api/track/sprints", method="POST", body=payload)

    def update_sprint(self, id: str, name: Optional[str] = None, status: Optional[str] = None,
                      starts_at: Optional[str] = None, ends_at: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if name is not None: payload["name"] = name
        if status is not None: payload["status"] = status
        if starts_at is not None: payload["starts_at"] = starts_at
        if ends_at is not None: payload["ends_at"] = ends_at
        return self._api(f"/api/track/sprints/{id}", method="PATCH", body=payload)

    def list_sprints(self, project: Optional[str] = None) -> Dict[str, Any]:
        return self._api("/api/track/sprints", params={"project": project})

    # ------------------ Issues ------------------

    def create_issue(self, project: str, title: str, sprint: Optional[str] = None,
                     status: str = "open", labels: Optional[List[str]] = None,
                     id: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"project": project, "title": title, "status": status}
        if id: payload["id"] = id
        if sprint: payload["sprint"] = sprint
        if labels is not None: payload["labels"] = labels
        return self._api("/api/track/issues", method="POST", body=payload)

    def update_issue(self, id: str, title: Optional[str] = None, sprint: Optional[str] = None,
                     status: Optional[str] = None, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if title is not None: payload["title"] = title
        if sprint is not None: payload["sprint"] = sprint
        if status is not None: payload["status"] = status
        if labels is not None: payload["labels"] = labels
        return self._api(f"/api/track/issues/{id}", method="PATCH", body=payload)

    def list_issues(self, project: Optional[str] = None, sprint: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
        return self._api("/api/track/issues", params={"project": project, "sprint": sprint, "status": status})

    # ------------------ Events & Radar ------------------

    def emit_work_event(self, summary: str, project: Optional[str] = None, event_type: str = "pulse",
                        dirty_files: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None,
                        workstation: Optional[str] = None, root: Optional[Path] = None) -> Dict[str, Any]:
        ws = workstation or get_workstation_id()
        rt = root or self.root
        git_info = get_git_info(rt)
        git_status = get_git_status_details(rt)

        files = dirty_files if dirty_files is not None else git_status["dirty_files"]
        count = len(files)

        payload = {
            "workstation": ws,
            "project": project,
            "event_type": event_type,
            "summary": summary,
            "git_branch": git_info["branch"],
            "git_commit": git_info["commit"],
            "dirty_files_count": count,
            "dirty_files": files,
            "metadata": metadata or {},
        }
        return self._api("/api/track/events", method="POST", body=payload)

    def get_station_radar(self) -> Dict[str, Any]:
        return self._api("/api/track/radar")

    def check_station_conflicts(self, project: str) -> Dict[str, Any]:
        data = self._api("/api/track/radar")
        ws = get_workstation_id()
        conflicts = data.get("conflicts", [])
        matching = next((c for c in conflicts if c.get("project_id") == project), None)
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
        payload = {
            "project": project,
            "note": note,
            "sprint": sprint,
            "issue": issue,
            "workstation": ws,
            "git_branch": git_info["branch"],
            "git_commit": git_info["commit"],
        }
        return self._api("/api/track/progress", method="POST", body=payload)

    def query_progress(self, project: Optional[str] = None, sprint: Optional[str] = None,
                       issue: Optional[str] = None, since: Optional[str] = None) -> Dict[str, Any]:
        return self._api("/api/track/progress", params={"project": project, "sprint": sprint, "issue": issue, "since": since})

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
