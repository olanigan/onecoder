import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class IssueManager:
    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or self._find_project_root()
        self.issues_dir = self.repo_root / ".issues"
        self._ensure_dir()

    def _find_project_root(self) -> Path:
        """Find the project root directory (containing .git)."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path.cwd()  # Fallback to current directory

    def _ensure_dir(self):
        self.issues_dir.mkdir(parents=True, exist_ok=True)

    def get_next_id(self) -> str:
        """Find the next incremental issue ID (e.g. 017)."""
        max_id = 0
        for item in self.issues_dir.iterdir():
            if item.is_file() and item.suffix == ".md":
                match = re.match(r"^(\d{3})-", item.name)
                if match:
                    max_id = max(max_id, int(match.group(1)))
        return f"{max_id + 1:03d}"

    def create_from_telemetry(
        self, telemetry_data: Dict[str, Any], title: Optional[str] = None
    ) -> Path:
        """Generate a markdown issue file from a single telemetry entry."""
        issue_id = self.get_next_id()

        # Clean title for filename
        raw_title = title or telemetry_data.get("message", "unhandled-failure")
        clean_title = re.sub(r"[^a-z0-9]+", "-", raw_title.lower()).strip("-")
        filename = f"{issue_id}-{clean_title}.md"

        issue_path = self.issues_dir / filename

        content = self._generate_markdown(issue_id, telemetry_data, raw_title)

        with open(issue_path, "w") as f:
            f.write(content)

        return issue_path

    def create_issue(self, title: str, description: Optional[str] = None) -> Path:
        """Manually create a governance issue."""
        issue_id = self.get_next_id()
        clean_title = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        filename = f"{issue_id}-{clean_title}.md"
        issue_path = self.issues_dir / filename

        now = datetime.now().strftime("%Y-%m-%d")
        template = f"""# Issue: {title}

## Status
🔴 **Open** - Discovered on {now}

## Severity
**Medium** - Manually created issue

## Description
{description or "No description provided."}

## Root Cause Analysis
**Layer**: CLI Implementation (Manual)

## Sprint Context
- **Date**: {now}

## Next Steps
1. [ ] Investigate and fix
2. [ ] Close issue via `onecoder issue resolve {issue_id}`
"""
        with open(issue_path, "w") as f:
            f.write(template)

        return issue_path

    def _generate_markdown(
        self, issue_id: str, data: Dict[str, Any], title: str
    ) -> str:
        now = datetime.fromisoformat(
            data.get("timestamp", datetime.now().isoformat())
        ).strftime("%Y-%m-%d")

        template = f"""# Issue: {title}

## Status
🔴 **Open** - Discovered on {now}

## Severity
**Medium** - Automatically captured failure

## Description
{data.get("message", "No description provided.")}

## Steps to Reproduce
Automatically captured during CLI execution:
```bash
onecoder {" ".join(data.get("context", {}).get("command_args", []))}
```

## Actual Behavior
Error Type: `{data.get("error_type")}`
Message: `{data.get("message")}`

Stack Trace:
```python
{data.get("stack_trace", "No stack trace available.")}
```

## Root Cause Analysis
**Layer**: CLI Implementation (Auto-captured)

## Sprint Context
- **Discovered in**: {data.get("context", {}).get("sprint_id", "Unknown Sprint")}
- **Task**: {data.get("context", {}).get("task_id", "Unknown Task")}
- **User**: {data.get("user", "unknown")}
- **Date**: {now}

## Next Steps
1. [ ] Investigate root cause from stack trace
2. [ ] Implement fix and validation
3. [ ] Close issue via `onecoder issue resolve {issue_id}`
"""
        return template

    def get_all_issues(self) -> List[Dict[str, Any]]:
        """Parse all markdown issues in the .issues directory."""
        issues_list = []
        for item in self.issues_dir.iterdir():
            if item.is_file() and item.suffix == ".md":
                try:
                    content = item.read_text()
                    issue_data = self._parse_issue(item.stem, content)
                    if issue_data:
                        issues_list.append(issue_data)
                except Exception as e:
                    print(f"Failed to parse issue {item.name}: {e}")
        return issues_list

    def _parse_issue(self, filename: str, content: str) -> Optional[Dict[str, Any]]:
        # Filename format: ID-title
        match = re.match(r"^(\d{3})-(.+)$", filename)
        if not match:
            return None

        issue_id = match.group(1)
        raw_title_slug = match.group(2)

        # Regex extraction
        title_match = re.search(r"^# Issue: (.+)$", content, re.MULTILINE)
        status_match = re.search(
            r"## Status\n.*(Open|Resolved|Ignored).*",
            content,
            re.MULTILINE | re.IGNORECASE,
        )
        severity_match = re.search(r"## Severity\n\*\*(.+)\*\*", content, re.MULTILINE)
        desc_match = re.search(r"## Description\n(.+?)\n##", content, re.DOTALL)

        # Metadata extraction (sprint, task)
        sprint_match = re.search(r"- \*\*Discovered in\*\*: (.+)", content)
        task_match = re.search(r"- \*\*Task\*\*: (.+)", content)

        return {
            "id": issue_id,
            "title": title_match.group(1).strip() if title_match else raw_title_slug,
            "description": desc_match.group(1).strip() if desc_match else "",
            "status": status_match.group(1).lower() if status_match else "open",
            "severity": severity_match.group(1).lower() if severity_match else "medium",
            "sprintId": sprint_match.group(1).strip() if sprint_match else None,
            "metadata": {
                "source": "cli",
                "taskId": task_match.group(1).strip() if task_match else None,
            },
            "resolution": {},  # Populate if resolved logic added
        }

    def update_status(
        self,
        issue_id: str,
        status: str,
        resolution_meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update the status of a specific issue."""
        # Find file
        issue_file = None
        for item in self.issues_dir.iterdir():
            if item.is_file() and item.name.startswith(f"{issue_id}-"):
                issue_file = item
                break

        if not issue_file:
            return False

        content = issue_file.read_text()
        now = datetime.now().strftime("%Y-%m-%d")

        # Update Status Section
        status_line = (
            f"🟢 **{status.title()}** - Resolved on {now}"
            if status == "resolved"
            else f"🔴 **{status.title()}**"
        )
        content = re.sub(r"## Status\n.*", f"## Status\n{status_line}", content)

        # Add/Update Resolution Section if provided
        if resolution_meta and status == "resolved":
            res_md = f"""
## Resolution
- **Resolved By**: {resolution_meta.get("user", "unknown")}
- **Date**: {now}
- **Commit**: `{resolution_meta.get("commit_sha")}`
- **PR**: {resolution_meta.get("pr_url", "N/A")}
- **Fix Task**: {resolution_meta.get("fix_task_id", "N/A")}
"""
            if "## Resolution" in content:
                # Replace existing
                content = re.sub(
                    r"## Resolution\n.+?(?=\n##|$)",
                    res_md.strip(),
                    content,
                    flags=re.DOTALL,
                )
            else:
                # Append before Next Steps or at end
                if "## Next Steps" in content:
                    content = content.replace(
                        "## Next Steps", f"{res_md}\n## Next Steps"
                    )
                else:
                    content += f"\n{res_md}"

        with open(issue_file, "w") as f:
            f.write(content)

        return True
