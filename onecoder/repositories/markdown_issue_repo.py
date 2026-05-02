"""Markdown implementation of IssueRepository."""

import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from onecoder.domain.entities import Issue
from . import IssueRepository


class MarkdownIssueRepository(IssueRepository):
    """Persist Issues as markdown files in .issues/ directory."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.issues_dir = repo_root / ".issues"
        self.issues_dir.mkdir(parents=True, exist_ok=True)

    def _get_next_id(self) -> str:
        """Find next incremental issue ID."""
        max_id = 0
        for item in self.issues_dir.iterdir():
            if item.is_file() and item.suffix == ".md":
                match = re.match(r"^(\d{3})-", item.name)
                if match:
                    max_id = max(max_id, int(match.group(1)))
        return f"{max_id + 1:03d}"

    def _issue_file_path(self, issue_id: str) -> Path:
        """Find markdown file for issue ID."""
        for item in self.issues_dir.iterdir():
            if item.is_file() and item.name.startswith(f"{issue_id}-"):
                return item
        # Return default path
        return self.issues_dir / f"{issue_id}-unhandled.md"

    def find_by_id(self, issue_id: str) -> Optional[Issue]:
        """Find issue by ID."""
        file_path = self._issue_file_path(issue_id)
        if not file_path.exists():
            return None
        return self._parse_issue_file(file_path)

    def save(self, issue: Issue) -> None:
        """Save issue to markdown file."""
        # Find existing file or create new
        file_path = self._issue_file_path(issue.issue_id)

        if not file_path.exists():
            # New issue
            clean_title = re.sub(r"[^a-z0-9]+", "-", issue.title.lower()).strip("-")
            filename = f"{issue.issue_id}-{clean_title}.md"
            file_path = self.issues_dir / filename

        content = self._issue_to_markdown(issue)
        file_path.write_text(content)

    def delete(self, issue_id: str) -> bool:
        """Delete issue file. Returns True if deleted."""
        file_path = self._issue_file_path(issue_id)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def list_all(self) -> List[Issue]:
        """List all issues."""
        issues = []
        for item in self.issues_dir.iterdir():
            if item.is_file() and item.suffix == ".md":
                issue = self._parse_issue_file(item)
                if issue:
                    issues.append(issue)
        return issues

    def find_by_status(self, status: str) -> List[Issue]:
        """Find issues by status."""
        all_issues = self.list_all()
        return [i for i in all_issues if i.status == status]

    def _parse_issue_file(self, file_path: Path) -> Optional[Issue]:
        """Parse issue from markdown file."""
        try:
            content = file_path.read_text()

            # Extract data using regex
            title_match = re.search(r"^# Issue: (.+)$", content, re.MULTILINE)
            status_match = re.search(
                r"## Status\n.*?(Open|Resolved|Ignored).*?",
                content,
                re.MULTILINE | re.IGNORECASE,
            )
            severity_match = re.search(r"## Severity\n\*\*(.+)\*\*", content, re.MULTILINE)
            desc_match = re.search(r"## Description\n(.+?)\n##", content, re.DOTALL)

            # Extract issue_id from filename
            filename = file_path.stem
            match = re.match(r"^(\d{3})-(.+)$", filename)
            issue_id = match.group(1) if match else "000"
            title = title_match.group(1).strip() if title_match else filename

            # Parse metadata
            sprint_match = re.search(r"- \*\*Discovered in\*\*: (.+)", content)
            task_match = re.search(r"- \*\*Task\*\*: (.+)", content)
            created_match = re.search(r"Discovered on (\d{4}-\d{2}-\d{2})", content)

            created_at = datetime.now()
            if created_match:
                try:
                    created_at = datetime.strptime(created_match.group(1), "%Y-%m-%d")
                except Exception:
                    pass

            return Issue(
                issue_id=issue_id,
                title=title,
                description=desc_match.group(1).strip() if desc_match else "",
                status=status_match.group(1).lower() if status_match else "open",
                severity=severity_match.group(1).lower() if severity_match else "medium",
                sprint_id=sprint_match.group(1).strip() if sprint_match else None,
                task_id=task_match.group(1).strip() if task_match else None,
                created_at=created_at,
            )
        except Exception:
            return None

    def _issue_to_markdown(self, issue: Issue) -> str:
        """Convert Issue entity to markdown."""
        now = issue.created_at.strftime("%Y-%m-%d")
        status_text = (
            f"🟢 **Resolved** - Resolved on {now}"
            if issue.status == "resolved"
            else f"🔴 **{issue.status.title()}** - Discovered on {now}"
        )

        return f"""# Issue: {issue.title}

## Status
{status_text}

## Severity
**{issue.severity.title()}** - {"Manually created" if not issue.sprint_id else "Automatically captured"}

## Description
{issue.description}

## Root Cause Analysis
**Layer**: CLI Implementation

## Sprint Context
- **Discovered in**: {issue.sprint_id or "Unknown Sprint"}
- **Task**: {issue.task_id or "Unknown Task"}
- **User**: unknown
- **Date**: {issue.created_at.strftime("%Y-%m-%d")}

## Next Steps
1. [ ] Investigate and fix
2. [ ] Close issue via `onecoder issue resolve {issue.issue_id}`
"""
