"""YAML implementation of SprintRepository."""

import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from onecoder.domain.entities import Sprint, Task, Issue
from onecoder.domain.value_objects import TaskStatus, SprintPhase, DomainModel
from . import SprintRepository


class YamlSprintRepository(SprintRepository):
    """Persist Sprint aggregates as YAML files."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _sprint_yaml_path(self, sprint_id: str) -> Path:
        """Find YAML file for sprint (tries sprint.yaml first, then sprint.json)."""
        yaml_path = self.base_dir / sprint_id / "sprint.yaml"
        if yaml_path.exists():
            return yaml_path
        # Fallback to parent directory search
        for d in self.base_dir.iterdir():
            if d.is_dir() and sprint_id in d.name:
                yaml_file = d / "sprint.yaml"
                if yaml_file.exists():
                    return yaml_file
                json_file = d / "sprint.json"
                if json_file.exists():
                    return json_file
        return yaml_path  # Default path even if doesn't exist

    def find_by_id(self, sprint_id: str) -> Optional[Sprint]:
        """Find sprint by ID."""
        yaml_path = self._sprint_yaml_path(sprint_id)
        if not yaml_path.exists():
            return None
        return self._load_from_file(yaml_path)

    def find_by_name(self, name: str) -> Optional[Sprint]:
        """Find sprint by name."""
        for d in self.base_dir.iterdir():
            if d.is_dir():
                yaml_file = d / "sprint.yaml"
                if yaml_file.exists():
                    data = yaml.safe_load(yaml_file.read_text())
                    if data and data.get("name") == name:
                        return self._dict_to_sprint(data)
        return None

    def save(self, sprint: Sprint) -> None:
        """Save sprint to YAML."""
        sprint_dir = self.base_dir / sprint.name
        sprint_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = sprint_dir / "sprint.yaml"

        data = self._sprint_to_dict(sprint)
        # Use custom dumper to avoid aliases
        class NoAliasDumper(yaml.SafeDumper):
            def ignore_aliases(self, data):
                return True

        with open(yaml_path, "w") as f:
            yaml.dump(data, f, Dumper=NoAliasDumper, sort_keys=False, default_flow_style=False)

    def delete(self, sprint_id: str) -> bool:
        """Delete sprint directory."""
        yaml_path = self._sprint_yaml_path(sprint_id)
        if yaml_path.exists():
            import shutil
            shutil.rmtree(yaml_path.parent, ignore_errors=True)
            return True
        return False

    def list_all(self) -> List[Sprint]:
        """List all sprints."""
        sprints = []
        for d in self.base_dir.iterdir():
            if d.is_dir():
                yaml_file = d / "sprint.yaml"
                if yaml_file.exists():
                    sprint = self._load_from_file(yaml_file)
                    if sprint:
                        sprints.append(sprint)
        return sprints

    def exists(self, sprint_id: str) -> bool:
        """Check if sprint exists."""
        return self._sprint_yaml_path(sprint_id).exists()

    def _load_from_file(self, file_path: Path) -> Optional[Sprint]:
        """Load sprint from YAML/JSON file."""
        try:
            if file_path.suffix == ".json":
                import json
                data = json.loads(file_path.read_text())
            else:
                data = yaml.safe_load(file_path.read_text())
            return self._dict_to_sprint(data)
        except Exception:
            return None

    def _dict_to_sprint(self, data: Dict[str, Any]) -> Sprint:
        """Convert dictionary to Sprint aggregate."""
        # Parse tasks
        tasks = []
        for t_data in data.get("tasks", []):
            task = Task(
                task_id=t_data.get("id", ""),
                title=t_data.get("title", ""),
                status=TaskStatus(t_data.get("status", "todo")),
                priority=t_data.get("priority", "medium"),
                task_type=t_data.get("type", "implementation"),
                description=t_data.get("description"),
                started_at=self._parse_datetime(t_data.get("startedAt")),
                completed_at=self._parse_datetime(t_data.get("completedAt")),
                first_commit_at=self._parse_datetime(t_data.get("firstCommitAt")),
                specs=t_data.get("specs", []),
                commits=t_data.get("commits", []),
                blocked_by=t_data.get("blockedBy", []),
            )
            tasks.append(task)

        # Parse metadata
        metadata = data.get("metadata", {})
        domain_model_data = metadata.get("domainModel", {})

        domain_model = None
        if domain_model_data:
            domain_model = DomainModel(
                aggregate_root=domain_model_data.get("aggregateRoot", ""),
                entities=tuple(domain_model_data.get("entities", [])),
                value_objects=tuple(domain_model_data.get("valueObjects", [])),
                ubiquitous_language=tuple(domain_model_data.get("ubiquitousLanguage", [])),
            )

        # Create Sprint aggregate root
        sprint = Sprint(
            sprint_id=data.get("sprintId", ""),
            name=data.get("name", ""),
            title=data.get("title"),
            phase=SprintPhase(data.get("status", {}).get("phase", "init")),
            state=data.get("status", {}).get("state", "active"),
            created_at=self._parse_datetime(metadata.get("createdAt")) or datetime.now(),
            updated_at=self._parse_datetime(metadata.get("updatedAt")),
            created_by=metadata.get("createdBy"),
            parent_component=metadata.get("parentComponent"),
            git_branch=metadata.get("gitBranch"),
            bounded_context=metadata.get("boundedContext"),
            labels=metadata.get("labels", []),
            primary_goal=data.get("goals", {}).get("primary"),
            secondary_goals=data.get("goals", {}).get("secondary", []),
            specs_implements=data.get("specifications", {}).get("implements", []),
            specs_validates=data.get("specifications", {}).get("validates", []),
            specs_blocks=data.get("specifications", {}).get("blocks", []),
        )

        # Add tasks to sprint
        for task in tasks:
            sprint._tasks.append(task)  # Direct append (bypassing invariant for loading)

        return sprint

    def _sprint_to_dict(self, sprint: Sprint) -> Dict[str, Any]:
        """Convert Sprint aggregate to dictionary for YAML serialization."""
        return {
            "$schema": "https://onecoder.dev/schemas/sprint.json",
            "version": "1.0.0",
            "sprintId": sprint.sprint_id,
            "name": sprint.name,
            "title": sprint.title,
            "status": {
                "phase": sprint.phase.value,
                "state": sprint.state,
                "message": None,
            },
            "metadata": {
                "createdAt": self._format_datetime(sprint.created_at),
                "updatedAt": self._format_datetime(sprint.updated_at) or self._format_datetime(datetime.now()),
                "createdBy": sprint.created_by,
                "parentComponent": sprint.parent_component,
                "boundedContext": sprint.bounded_context,
                "gitBranch": sprint.git_branch,
                "labels": sprint.labels,
            },
            "goals": {
                "primary": sprint.primary_goal,
                "secondary": sprint.secondary_goals,
            },
            "tasks": [
                {
                    "id": t.task_id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status.value,
                    "type": t.task_type,
                    "priority": t.priority,
                    "startedAt": self._format_datetime(t.started_at),
                    "completedAt": self._format_datetime(t.completed_at),
                    "firstCommitAt": self._format_datetime(t.first_commit_at),
                    "specs": t.specs,
                    "commits": t.commits,
                    "blockedBy": t.blocked_by,
                }
                for t in sprint.tasks
            ],
            "git": {
                "branch": sprint.git_branch,
                "lastCommit": None,
                "hasUncommittedChanges": False,
            },
            "hooks": {
                "onInit": [],
                "onTaskStart": [],
                "onTaskComplete": [],
                "onSprintClose": [],
            },
            "retro": {"summary": "", "actionItems": []},
            "artifacts": {"readme": None, "retro": None, "media": []},
        }

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime from string."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return None

    def _format_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        """Format datetime to ISO string."""
        if not dt:
            return None
        return dt.isoformat()
