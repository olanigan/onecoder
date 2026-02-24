import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
from jsonschema import validate, ValidationError
from .sync_engine import sync_artifacts, sync_tasks_from_todo

SCHEMA_PATH = Path(__file__).parent / "schemas" / "sprint.schema.json"


class SprintStateManager:
    """Manage sprint.yaml state file."""

    def __init__(self, sprint_dir: Path):
        self.sprint_dir = sprint_dir
        self.backlog_dir = sprint_dir.parent / "backlog"
        self.yaml_file = sprint_dir / "sprint.yaml"
        self.json_file = sprint_dir / "sprint.json"

        # Prefer YAML if exists, else JSON, else default to YAML for new files
        if self.json_file.exists() and not self.yaml_file.exists():
            self.state_file = self.json_file
        else:
            self.state_file = self.yaml_file

        self._schema = self._load_schema()

    def _load_schema(self) -> Dict[str, Any]:
        if not SCHEMA_PATH.exists():
            return {}
        with open(SCHEMA_PATH) as f:
            return json.load(f)

    def load(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.yaml_file.exists():
            import yaml

            with open(self.yaml_file) as f:
                data = yaml.safe_load(f) or {}
        elif self.json_file.exists():
            with open(self.json_file) as f:
                data = json.load(f)

        if not data:
            return {}

        if self._schema:
            try:
                validate(instance=data, schema=self._schema)
            except ValidationError as e:
                raise ValueError(f"Invalid sprint state: {e.message}")
        return data

    def save(self, state: Dict[str, Any]) -> None:
        if self._schema:
            try:
                validate(instance=state, schema=self._schema)
            except ValidationError as e:
                raise ValueError(f"Invalid sprint state: {e.message}")

        # Check for meaningful changes before writing
        current_state = self.load()
        if current_state:
            # Create copies to avoid mutating originals during comparison
            s1 = current_state.copy()
            s2 = state.copy()

            # Remove metadata.updatedAt for comparison
            if "metadata" in s1:
                s1["metadata"] = {
                    k: v for k, v in s1["metadata"].items() if k != "updatedAt"
                }
            if "metadata" in s2:
                s2["metadata"] = {
                    k: v for k, v in s2["metadata"].items() if k != "updatedAt"
                }

            # If everything else is identical, skip the save to avoid git churn
            if s1 == s2:
                return

        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Always save to the determined state file format
        if self.state_file.suffix == ".yaml":
            import yaml

            # Custom dumper to handle clean block style if needed, but default safe_dump is fine for now
            # We explicitly avoid aliases to keep it clean
            class NoAliasDumper(yaml.SafeDumper):
                def ignore_aliases(self, data):
                    return True

            with open(self.state_file, "w") as f:
                yaml.dump(
                    state,
                    f,
                    Dumper=NoAliasDumper,
                    sort_keys=False,
                    default_flow_style=False,
                )
        else:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)

    def update(self, updates: Dict[str, Any]) -> None:
        state = self.load() or updates
        if state != updates:
            state = self._deep_merge(state, updates)
        self._update_metadata(state)
        self.save(state)

    def _deep_merge(
        self, base: Dict[str, Any], update: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = base.copy()
        for key, value in update.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _update_metadata(self, state: Dict[str, Any]) -> None:
        state.setdefault("metadata", {})["updatedAt"] = datetime.now().isoformat()

    def sync_from_files(self) -> None:
        state = self.load()
        if not state:
            return
        state = sync_artifacts(self.sprint_dir, state)
        # We still support sync from TODO for manual edits, but YAML is SSOT
        state = sync_tasks_from_todo(self.sprint_dir, state)
        self._update_metadata(state)
        self.save(state)
        self.sync_todo_from_state()

    def sync_todo_from_state(self) -> None:
        """Regenerate TODO.md from the current YAML state (SSOT)."""
        state = self.load()
        tasks = state.get("tasks", [])
        if not tasks:
            return

        todo_file = self.sprint_dir / "TODO.md"
        lines = ["# Tasks\n"]

        # High Priority / Active tasks
        active_tasks = [
            t
            for t in tasks
            if t.get("status") in ["in-progress", "started", "planning"]
        ]
        if active_tasks:
            lines.append("\n## High Priority\n")
            for t in active_tasks:
                marker = (
                    "[/]" if t.get("status") in ["in-progress", "started"] else "[ ]"
                )
                lines.append(
                    f"- {marker} {t.get('title')} <!-- id: {t.get('id')} -->\n"
                )

        # Implementation tasks
        impl_tasks = [
            t
            for t in tasks
            if t.get("status")
            not in ["in-progress", "started", "planning", "done", "completed"]
        ]
        if impl_tasks:
            lines.append("\n## Implementation\n")
            for t in impl_tasks:
                lines.append(f"- [ ] {t.get('title')} <!-- id: {t.get('id')} -->\n")

        # Completed tasks
        done_tasks = [t for t in tasks if t.get("status") in ["done", "completed"]]
        if done_tasks:
            lines.append("\n## Done\n")
            for t in done_tasks:
                lines.append(f"- [x] {t.get('title')} <!-- id: {t.get('id')} -->\n")

        new_content = "".join(lines)
        # Idempotency check: Only write if content meaningfully changed
        if todo_file.exists():
            if todo_file.read_text() == new_content:
                return

        todo_file.write_text(new_content)

    def create_initial_state(
        self, name: str, title: Optional[str] = None, component: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "$schema": "https://onecoder.dev/schemas/sprint.json",
            "version": "1.0.0",
            "sprintId": name,
            "name": name,
            "title": title or name,
            "status": {"phase": "init", "state": "active", "message": None},
            "metadata": {
                "createdAt": now,
                "updatedAt": now,
                "createdBy": None,
                "parentComponent": component,
                "gitBranch": None,
                "labels": [],
            },
            "goals": {"primary": None, "secondary": []},
            "tasks": [],
            # Mandatory Context Layers per SPEC-CORE-002
            "git": {"branch": None, "lastCommit": None, "hasUncommittedChanges": False},
            "hooks": {
                "onInit": [],
                "onTaskStart": [],
                "onTaskComplete": [],
                "onSprintClose": [],
            },
            "retro": {"summary": "", "actionItems": []},
        }

    def get_active_task(self) -> Optional[Dict[str, Any]]:
        state = self.load()
        for task in state.get("tasks", []):
            if task.get("status") in ["in_progress", "started", "in-progress"]:
                return task
        return None

    def mark_done(self, task_id_or_title: str) -> bool:
        return self._update_task_status(task_id_or_title, "done")

    def start_task(self, task_id_or_title: str) -> bool:
        return self._update_task_status(task_id_or_title, "in-progress")

    def _update_task_status(self, task_id_or_title: str, status: str) -> bool:
        """Update task status in YAML state (SSOT) and sync to TODO.md."""
        state = self.load()
        updated = False
        target_task = None
        for task in state.get("tasks", []):
            if (
                task.get("id") == task_id_or_title
                or task.get("title") == task_id_or_title
            ):
                target_task = task
                break

        # If not found in active tasks, check backlog
        if not target_task:
            backlog_tasks = self.get_backlog_tasks()
            for task in backlog_tasks:
                if (
                    task.get("id") == task_id_or_title
                    or task.get("title") == task_id_or_title
                ):
                    # Import task from backlog to active sprint
                    task["status"] = "planning"  # Initial status for imported task
                    state.setdefault("tasks", []).append(task)
                    target_task = task
                    updated = True
                    break

        if target_task:
            target_task["status"] = status
            if status == "in-progress" and not target_task.get("startedAt"):
                target_task["startedAt"] = datetime.now().isoformat()
            elif status == "done" and not target_task.get("completedAt"):
                target_task["completedAt"] = datetime.now().isoformat()
            updated = True

        if updated:
            self._update_metadata(state)
            self.save(state)
            self.sync_todo_from_state()
            return True
        return False

    def get_backlog_tasks(self) -> List[Dict[str, Any]]:
        """Extract tasks from .sprint/backlog/ files."""
        tasks: List[Dict[str, Any]] = []
        if not self.backlog_dir.exists():
            return tasks

        for backlog_file in self.backlog_dir.glob("*.md"):
            content = backlog_file.read_text()
            # Simple extractor for markdown task lists
            # Pattern: - [ ] Task Title (task-xxx)
            matches = re.finditer(r"-\s*\[\s\]\s*(.*?)\s*\((task-\d+)\)", content)
            for match in matches:
                tasks.append(
                    {
                        "id": match.group(2),
                        "title": match.group(1),
                        "status": "backlog",
                        "source": backlog_file.name,
                    }
                )
        return tasks

    def get_task_id_by_title(self, title: str) -> Optional[str]:
        state = self.load()
        if not state.get("tasks"):
            self.sync_from_files()
            state = self.load()
        for t in state.get("tasks", []):
            if t.get("title").strip().lower() == title.strip().lower():
                return t.get("id")
        return None

    def get_component(self) -> Optional[str]:
        return self.load().get("metadata", {}).get("parentComponent")

    def set_component(self, component: str) -> None:
        state = self.load()
        if not state:
            return
        state.setdefault("metadata", {})["parentComponent"] = component
        self._update_metadata(state)
        self.save(state)

    def record_task_event(self, task_id: str, event_type: str) -> bool:
        """Record a timestamped event for a task (e.g., first_commit). Returns True if state changed."""
        state = self.load()
        updated = False
        for task in state.get("tasks", []):
            if task.get("id") == task_id:
                if event_type == "first_commit" and not task.get("firstCommitAt"):
                    task["firstCommitAt"] = datetime.now().isoformat()
                    updated = True
                break
        if updated:
            self._update_metadata(state)
            self.save(state)
            return True
        return False
