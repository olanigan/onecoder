"""Sprint Governance Service - domain logic for sprint lifecycle rules."""

from typing import List, Dict, Any, Optional
from datetime import datetime

from onecoder.domain.entities import Sprint, Task, Issue
from onecoder.domain.value_objects import TaskStatus, SprintPhase


class SprintGovernanceService:
    """Domain service for enforcing sprint governance rules."""

    def can_start_task(self, sprint: Sprint, task_id_or_title: str) -> tuple[bool, str]:
        """Check if a task can be started. Returns (can_start, reason)."""
        task = sprint.get_task(task_id_or_title)
        if not task:
            return False, f"Task '{task_id_or_title}' not found"

        if task.status.value in ["done", "completed"]:
            return False, f"Task '{task.title}' is already completed"

        if task.status.value == "blocked":
            blocked_by = task.blocked_by
            if blocked_by:
                return False, f"Task is blocked by: {', '.join(blocked_by)}"

        # Check if another task is already in-progress
        active = sprint.active_tasks
        if active and active[0].task_id != task.task_id:
            return False, f"Another task '{active[0].title}' is already in-progress"

        return True, "OK"

    def can_complete_sprint(self, sprint: Sprint) -> tuple[bool, List[str]]:
        """Check if sprint can be closed. Returns (can_close, reasons)."""
        reasons = []

        # Check all tasks completed
        incomplete = [t for t in sprint.tasks if t.status.value not in ["done", "completed"]]
        if incomplete:
            reasons.append(f"{len(incomplete)} tasks still incomplete")

        # Check sprint has goals defined
        if not sprint.primary_goal:
            reasons.append("Primary goal not defined")

        # Check retro exists (optional)
        # (Would check if retro file exists)

        return len(reasons) == 0, reasons

    def validate_task_transition(self, task: Task, new_status: str) -> tuple[bool, str]:
        """Validate task status transition. Returns (valid, reason)."""
        current = task.status.value

        # Define valid transitions
        valid_transitions = {
            "todo": ["in-progress", "in_progress", "blocked"],
            "in-progress": ["review", "done", "completed", "blocked"],
            "in_progress": ["review", "done", "completed", "blocked"],
            "review": ["done", "completed", "in-progress"],
            "blocked": ["todo", "in-progress"],
            "done": [],
            "completed": [],
        }

        if new_status not in valid_transitions.get(current, []):
            return False, f"Invalid transition: {current} → {new_status}"

        return True, "OK"

    def enforce_invariant(self, sprint: Sprint) -> List[str]:
        """Check sprint invariants. Returns list of violations."""
        violations = []

        # Invariant 1: Sprint must have ID
        if not sprint.sprint_id:
            violations.append("Sprint must have an ID")

        # Invariant 2: Task IDs must be unique within sprint
        task_ids = [t.task_id for t in sprint.tasks]
        if len(task_ids) != len(set(task_ids)):
            violations.append("Duplicate task IDs found")

        # Invariant 3: Only one task can be in-progress at a time
        active = sprint.active_tasks
        if len(active) > 1:
            violations.append(f"Multiple tasks in-progress: {[t.task_id for t in active]}")

        return violations

    def get_sprint_health(self, sprint: Sprint) -> Dict[str, Any]:
        """Get sprint health metrics."""
        total = len(sprint.tasks)
        if total == 0:
            return {"health": "unknown", "progress": 0.0, "active_tasks": 0}

        done = sum(1 for t in sprint.tasks if t.status.value in ["done", "completed"])
        in_progress = len(sprint.active_tasks)
        blocked = sum(1 for t in sprint.tasks if t.status.value == "blocked")

        progress = sprint.get_progress()

        if progress >= 0.8:
            health = "good"
        elif progress >= 0.5:
            health = "warning"
        else:
            health = "critical"

        return {
            "health": health,
            "progress": progress,
            "total_tasks": total,
            "done_tasks": done,
            "active_tasks": in_progress,
            "blocked_tasks": blocked,
            "issues_count": len(sprint.issues),
        }

    def check_zero_debt_policy(self, sprint: Sprint) -> List[str]:
        """Check zero debt policy compliance."""
        violations = []

        # Check for tasks without specs
        tasks_without_specs = [t.task_id for t in sprint.tasks if not t.specs]
        if tasks_without_specs:
            violations.append(f"Tasks without specs: {len(tasks_without_specs)}")

        return violations
