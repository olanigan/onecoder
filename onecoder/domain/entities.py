"""Domain Entities - objects with identity."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from .value_objects import TaskStatus, SprintPhase


@dataclass
class Task:
    """Entity: Task within a Sprint (identity = task_id)."""
    task_id: str
    title: str
    status: TaskStatus = field(default_factory=lambda: TaskStatus("todo"))
    priority: str = "medium"
    task_type: str = "implementation"
    description: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    first_commit_at: Optional[datetime] = None
    specs: List[str] = field(default_factory=list)
    commits: List[str] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)

    def start(self) -> None:
        """Mark task as in-progress."""
        self.status = TaskStatus("in-progress")
        if not self.started_at:
            self.started_at = datetime.now()

    def complete(self) -> None:
        """Mark task as done."""
        self.status = TaskStatus("done")
        if not self.completed_at:
            self.completed_at = datetime.now()

    def add_commit(self, commit_hash: str) -> None:
        """Record a git commit for this task."""
        if commit_hash not in self.commits:
            self.commits.append(commit_hash)
            if not self.first_commit_at:
                self.first_commit_at = datetime.now()


@dataclass
class Issue:
    """Entity: Issue with identity (issue_id)."""
    issue_id: str
    title: str
    description: str = ""
    status: str = "open"  # open, resolved, ignored
    severity: str = "medium"
    sprint_id: Optional[str] = None
    task_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolution: Dict[str, Any] = field(default_factory=dict)

    def resolve(self, resolution_meta: Optional[Dict[str, Any]] = None) -> None:
        """Mark issue as resolved."""
        self.status = "resolved"
        self.resolved_at = datetime.now()
        if resolution_meta:
            self.resolution = resolution_meta


@dataclass
class Sprint:
    """Aggregate Root: Sprint with identity (sprint_id)."""
    sprint_id: str
    name: str
    title: Optional[str] = None
    phase: SprintPhase = field(default_factory=lambda: SprintPhase("init"))
    state: str = "active"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    parent_component: Optional[str] = None
    git_branch: Optional[str] = None
    bounded_context: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    primary_goal: Optional[str] = None
    secondary_goals: List[str] = field(default_factory=list)
    _tasks: List[Task] = field(default_factory=list, repr=False)
    _issues: List[Issue] = field(default_factory=list, repr=False)
    specs_implements: List[str] = field(default_factory=list)
    specs_validates: List[str] = field(default_factory=list)
    specs_blocks: List[str] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a task to this sprint (enforce invariant: unique task_id)."""
        if any(t.task_id == task.task_id for t in self._tasks):
            raise ValueError(f"Task {task.task_id} already exists in sprint")
        self._tasks.append(task)
        self.updated_at = datetime.now()

    def get_task(self, task_id_or_title: str) -> Optional[Task]:
        """Find task by ID or title."""
        for task in self._tasks:
            if task.task_id == task_id_or_title or task.title == task_id_or_title:
                return task
        return None

    def start_task(self, task_id_or_title: str) -> bool:
        """Start a task by ID or title."""
        task = self.get_task(task_id_or_title)
        if task:
            task.start()
            self.updated_at = datetime.now()
            return True
        return False

    def complete_task(self, task_id_or_title: str) -> bool:
        """Complete a task by ID or title."""
        task = self.get_task(task_id_or_title)
        if task:
            task.complete()
            self.updated_at = datetime.now()
            return True
        return False

    def add_issue(self, issue: Issue) -> None:
        """Add an issue to this sprint."""
        if any(i.issue_id == issue.issue_id for i in self._issues):
            raise ValueError(f"Issue {issue.issue_id} already exists")
        self._issues.append(issue)
        self.updated_at = datetime.now()

    @property
    def tasks(self) -> List[Task]:
        """Get copy of tasks list."""
        return list(self._tasks)

    @property
    def issues(self) -> List[Issue]:
        """Get copy of issues list."""
        return list(self._issues)

    @property
    def active_tasks(self) -> List[Task]:
        """Get tasks that are in-progress."""
        return [t for t in self._tasks if t.status.value in ("in-progress", "started")]

    def get_progress(self) -> float:
        """Calculate sprint progress (0.0 to 1.0)."""
        if not self._tasks:
            return 0.0
        done_count = sum(1 for t in self._tasks if t.status.value == "done")
        return done_count / len(self._tasks)
