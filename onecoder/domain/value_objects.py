"""Value Objects - immutable objects without identity."""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class TaskStatus:
    """Value Object: Task status (immutable)."""
    value: str

    def __post_init__(self):
        valid = ["backlog", "todo", "in-progress", "in_progress", 
                  "review", "done", "completed", "blocked", "migrated"]
        if self.value not in valid:
            raise ValueError(f"Invalid TaskStatus: {self.value}")

    def __eq__(self, other):
        if isinstance(other, TaskStatus):
            return self.value == other.value
        return self.value == other

    def __repr__(self):
        return f"TaskStatus('{self.value}')"


@dataclass(frozen=True)
class SprintPhase:
    """Value Object: Sprint phase (immutable)."""
    value: str

    def __post_init__(self):
        valid = ["init", "planning", "research", "implementation", 
                  "validation", "review", "closed"]
        if self.value not in valid:
            raise ValueError(f"Invalid SprintPhase: {self.value}")

    def __eq__(self, other):
        if isinstance(other, SprintPhase):
            return self.value == other.value
        return self.value == other

    def __repr__(self):
        return f"SprintPhase('{self.value}')"


@dataclass(frozen=True)
class AlignmentScore:
    """Value Object: Alignment score between 0 and 100 (immutable)."""
    value: int

    def __post_init__(self):
        if not 0 <= self.value <= 100:
            raise ValueError(f"AlignmentScore must be 0-100, got {self.value}")

    @property
    def is_aligned(self) -> bool:
        """Check if alignment meets threshold (90%)."""
        return self.value >= 90

    def __repr__(self):
        return f"AlignmentScore({self.value})"


@dataclass(frozen=True)
class SprintMetadata:
    """Value Object: Sprint metadata (immutable)."""
    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    parent_component: Optional[str] = None
    git_branch: Optional[str] = None
    bounded_context: Optional[str] = None
    labels: tuple = ()  # Immutable tuple instead of list

    def with_updated(self, **kwargs) -> "SprintMetadata":
        """Create new instance with updated fields (immutability)."""
        data = {
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "parent_component": self.parent_component,
            "git_branch": self.git_branch,
            "bounded_context": self.bounded_context,
            "labels": self.labels,
        }
        data.update(kwargs)
        return SprintMetadata(**data)


@dataclass(frozen=True)
class DomainModel:
    """Value Object: DDD domain model metadata (immutable)."""
    aggregate_root: str
    entities: tuple = ()  # Immutable
    value_objects: tuple = ()  # Immutable
    ubiquitous_language: tuple = ()  # Immutable

    def __repr__(self):
        return f"DomainModel(root={self.aggregate_root}, entities={len(self.entities)})"
