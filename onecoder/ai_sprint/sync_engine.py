import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def sync_artifacts(sprint_dir: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    """Sync artifact files from sprint directory."""
    artifacts = state.setdefault("artifacts", {})
    for artifact in ["README.md", "RETRO.md", "WALKTHROUGH.md", "FEATURES.md"]:
        if (sprint_dir / artifact).exists():
            key = artifact.lower().replace(".md", "")
            artifacts[key] = artifact

    media_dir = sprint_dir / "media"
    if media_dir.exists():
        media_items = []
        for f in media_dir.glob("*"):
            if f.is_file():
                suffix = f.suffix.lower()
                media_type = (
                    "screenshot"
                    if suffix in [".png", ".jpg", ".jpeg", ".svg", ".gif"]
                    else ("log" if suffix in [".log", ".txt"] else "document")
                )
                media_items.append(
                    {"type": media_type, "path": f.name, "description": ""}
                )
        artifacts["media"] = media_items
    state["artifacts"] = artifacts
    return sync_retro_content(sprint_dir, state)


def sync_retro_content(sprint_dir: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    """Parse RETRO.md and update sprint.json retro object."""
    retro_file = sprint_dir / "RETRO.md"
    if not retro_file.exists():
        return state
    content = retro_file.read_text()
    retro_data = {"summary": "", "actionItems": []}

    summary_match = re.search(
        r"^##\s+(?:Executive\s+)?Summary\s*$(.*?)(?=^##|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if summary_match:
        retro_data["summary"] = summary_match.group(1).strip()

    action_items_match = re.search(
        r"^##\s+Action Items\s*$(.*?)(?=^##|\Z)", content, re.MULTILINE | re.DOTALL
    )
    if action_items_match:
        items = re.findall(r"-\s*\[(\s|x)\]\s*(.+)", action_items_match.group(1))
        retro_data["actionItems"] = [it[1].strip() for it in items]

    if retro_data["summary"] or retro_data["actionItems"]:
        state["retro"] = retro_data
    return state


def sync_tasks_from_todo(sprint_dir: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    """Sync tasks from TODO.md, respecting persistent IDs."""
    todo_file = sprint_dir / "TODO.md"
    if not todo_file.exists():
        return state

    content = todo_file.read_text()
    lines = content.split("\n")
    new_lines = []

    tasks = []

    # 1. Index existing tasks by ID for metadata preservation
    existing_tasks_by_id = {
        t.get("id"): t for t in state.get("tasks", []) if t.get("id")
    }

    # Track used IDs to generate new ones safely
    used_ids = set(existing_tasks_by_id.keys())

    # Helper to find next available ID
    def get_next_id():
        counter = 1
        while True:
            # Pad to 3 digits (task-001)
            candidate = f"task-{counter:03d}"
            if candidate not in used_ids:
                return candidate
            counter += 1

    tasks_modified = False

    for line in lines:
        # Match task line: - [x] Title <!-- id: task-XXX -->
        # We look for the marker and the rest of the text
        match = re.match(r"-\s*\[(x|/|\s)\]\s*(.+)", line)
        if match:
            marker, full_text = match.group(1), match.group(2).strip()

            # Robust ID detection: find ANY task-XXX pattern, whether in parens or HTML comments
            id_match = re.search(r"<!--\s*id:\s*(task-\d+)\s*-->", full_text)
            if not id_match:
                id_match = re.search(r"\(+(task-\d+)\)+\s*", full_text)

            task_id = None
            task_title = full_text

            if id_match:
                task_id = id_match.group(1)
                # DEEP CLEAN: Strip ALL redundant ID tags from the title to prevent infinite growth
                task_title = re.sub(r"<!--\s*id:\s*task-\d+\s*-->", "", task_title)
                task_title = re.sub(r"\(+task-\d+\)+\s*", "", task_title)
                task_title = task_title.strip()
            else:
                # No ID found? Generate one.
                task_id = get_next_id()
                used_ids.add(task_id)
                # We need to append the ID to the line in TODO.md
                tasks_modified = True

            existing = existing_tasks_by_id.get(task_id, {})

            # Update status
            status = (
                "done"
                if marker == "x"
                else ("in-progress" if marker == "/" else "todo")
            )

            # Preserve metadata
            started_at = existing.get("startedAt")
            if marker == "/" and not started_at:
                started_at = datetime.now().isoformat()

            completed_at = existing.get("completedAt")
            if marker == "x" and not completed_at:
                completed_at = datetime.now().isoformat()

            first_commit_at = existing.get("firstCommitAt")

            tasks.append(
                {
                    "id": task_id,
                    "title": task_title,
                    "status": status,
                    "type": existing.get("type", "implementation"),
                    "priority": existing.get("priority", "medium"),
                    "startedAt": started_at,
                    "firstCommitAt": first_commit_at,
                    "completedAt": completed_at,
                }
            )

            # Reconstruct line with normalized ID format
            new_line = f"- [{marker}] {task_title} <!-- id: {task_id} -->"
            if new_line != line:
                tasks_modified = True
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    state["tasks"] = tasks

    # Idempotency check: Only write if content meaningfully changed
    if tasks_modified:
        new_content = "\n".join(new_lines)
        if new_content != content:
            todo_file.write_text(new_content)

    return state
