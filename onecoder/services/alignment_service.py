"""Alignment Service - domain logic for spec-to-code verification."""

from typing import Dict, Any, Optional
from pathlib import Path

from onecoder.domain.entities import Sprint, Task
from onecoder.domain.value_objects import AlignmentScore


class AlignmentService:
    """Domain service for checking alignment between specifications and code."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root

    def calculate_alignment_score(self, sprint: Sprint, task: Optional[Task] = None) -> AlignmentScore:
        """Calculate alignment score (0-100) based on sprint/task state."""
        score = 0

        # Factor 1: Sprint has bounded context defined (20 points)
        if sprint.bounded_context:
            score += 20

        # Factor 2: Sprint has domain model defined (20 points)
        # (Check if metadata exists - using bounded_context as proxy)
        if sprint.bounded_context:
            score += 20

        # Factor 3: Tasks have specs listed (30 points total, 10 per spec up to 30)
        tasks_to_check = [task] if task else sprint.tasks
        total_specs = sum(len(t.specs) for t in tasks_to_check)
        score += min(total_specs * 10, 30)

        # Factor 4: Tasks have commits (30 points total, 10 per commit up to 30)
        total_commits = sum(len(t.commits) for t in tasks_to_check)
        score += min(total_commits * 10, 30)

        return AlignmentScore(min(score, 100))

    def is_sprint_aligned(self, sprint: Sprint) -> bool:
        """Check if sprint meets alignment threshold (90%)."""
        score = self.calculate_alignment_score(sprint)
        return score.is_aligned

    def generate_alignment_report(self, sprint: Sprint) -> Dict[str, Any]:
        """Generate detailed alignment report."""
        total_tasks = len(sprint.tasks)
        tasks_with_specs = sum(1 for t in sprint.tasks if t.specs)
        tasks_with_commits = sum(1 for t in sprint.tasks if t.commits)
        completed_tasks = sum(1 for t in sprint.tasks if t.status.value == "done")

        return {
            "sprint_id": sprint.sprint_id,
            "total_tasks": total_tasks,
            "tasks_with_specs": tasks_with_specs,
            "tasks_with_commits": tasks_with_commits,
            "completed_tasks": completed_tasks,
            "progress": sprint.get_progress(),
            "alignment_score": self.calculate_alignment_score(sprint).value,
            "is_aligned": self.is_sprint_aligned(sprint),
        }

    def suggest_improvements(self, sprint: Sprint) -> list[str]:
        """Suggest improvements to increase alignment."""
        suggestions = []

        if not sprint.bounded_context:
            suggestions.append("Define bounded context in sprint metadata")

        tasks_without_specs = [t.task_id for t in sprint.tasks if not t.specs]
        if tasks_without_specs:
            suggestions.append(f"Add specs to tasks: {', '.join(tasks_without_specs[:3])}")

        return suggestions

    def generate_unified_plan(self, sprint_id: str, context: str = "task") -> str:
        """Generate planning guidance (legacy method for compatibility)."""
        return f"Planning guidance for {sprint_id} ({context} context)"
