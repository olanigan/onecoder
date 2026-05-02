"""Repositories module - persistence interfaces and implementations."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pathlib import Path

from onecoder.domain.entities import Sprint, Task, Issue
from onecoder.domain.value_objects import TaskStatus, SprintPhase


class SprintRepository(ABC):
    """Interface for Sprint persistence."""

    @abstractmethod
    def find_by_id(self, sprint_id: str) -> Optional[Sprint]:
        """Find sprint by ID."""
        pass

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Sprint]:
        """Find sprint by name."""
        pass

    @abstractmethod
    def save(self, sprint: Sprint) -> None:
        """Save sprint (create or update)."""
        pass

    @abstractmethod
    def delete(self, sprint_id: str) -> bool:
        """Delete sprint by ID. Returns True if deleted."""
        pass

    @abstractmethod
    def list_all(self) -> List[Sprint]:
        """List all sprints."""
        pass

    @abstractmethod
    def exists(self, sprint_id: str) -> bool:
        """Check if sprint exists."""
        pass


class IssueRepository(ABC):
    """Interface for Issue persistence."""

    @abstractmethod
    def find_by_id(self, issue_id: str) -> Optional[Issue]:
        """Find issue by ID."""
        pass

    @abstractmethod
    def save(self, issue: Issue) -> None:
        """Save issue (create or update)."""
        pass

    @abstractmethod
    def delete(self, issue_id: str) -> bool:
        """Delete issue by ID. Returns True if deleted."""
        pass

    @abstractmethod
    def list_all(self) -> List[Issue]:
        """List all issues."""
        pass

    @abstractmethod
    def find_by_status(self, status: str) -> List[Issue]:
        """Find issues by status."""
        pass


__all__ = ["SprintRepository", "IssueRepository"]
