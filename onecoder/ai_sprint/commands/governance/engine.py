import subprocess
import re
from pathlib import Path
from typing import List, Dict, Any
from ..common import SprintStateManager


class CommitStateEngine:
    """Intelligent engine to determine implementation integrity and commit scope."""

    def __init__(self, project_root: Path, sprint_dir: Path):
        self.project_root = project_root
        self.sprint_dir = sprint_dir
        self.metadata_files = [
            "sprint.yaml",
            "sprint.json",
            "TODO.md",
            "RETRO.md",
            "README.md",
            "WALKTHROUGH.md",
            ".gitignore",
            ".gitmodules",
        ]

    def get_changed_files(self) -> List[str]:
        """Get list of current changes (staged + unstaged)."""
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )
        files = []
        for line in res.stdout.split("\n"):
            if not line.strip():
                continue
            # Porcelain format: XY path or XY "path"
            path = line[3:].strip().strip('"')

            # Rule 1: Ignore anything in the .sprint directory
            if ".sprint/" in path or path.startswith("sprint/"):
                continue

            # Rule 2: Ignore root metadata files
            if any(Path(path).name == m for m in self.metadata_files):
                continue

            files.append(path)
        return list(set(files))

    def analyze(self, sprint_id: str, fixed_task_id: str = None) -> Dict[str, Any]:
        """Analyze changes and map to tasks. Returns a plan or a single task result."""
        changed_files = self.get_changed_files()
        if not changed_files:
            return {"status": "no_changes", "files": []}

        state_manager = SprintStateManager(self.sprint_dir / sprint_id)
        state = state_manager.load()
        tasks = state.get("tasks", [])

        # Filter for active/todo tasks
        potential_tasks = [
            t for t in tasks if t.get("status") not in ["done", "completed"]
        ]

        if fixed_task_id:
            return {
                "status": "proceed",
                "task_id": fixed_task_id,
                "files": changed_files,
            }

        if not potential_tasks:
            return {"status": "no_active_tasks", "files": changed_files}

        # If only one potential task exists, map everything to it
        if len(potential_tasks) == 1:
            return {
                "status": "proceed",
                "task_id": potential_tasks[0]["id"],
                "files": changed_files,
            }

        # Multi-task detection logic
        mapping = {}
        for f in changed_files:
            matched_tasks = []
            for t in potential_tasks:
                # Heuristic 1: Exact ID match in file path
                if t["id"] in f:
                    matched_tasks.append(t["id"])
                    continue

                # Heuristic 2: Substring/Keyword match
                title_words = [
                    w.lower()
                    for w in re.findall(r"\w+", t.get("title", "").lower())
                    if len(w) >= 4
                ]
                file_path_lower = f.lower()

                for word in title_words:
                    if word in file_path_lower:
                        matched_tasks.append(t["id"])
                        break

            if len(matched_tasks) == 1:
                mapping.setdefault(matched_tasks[0], []).append(f)
            else:
                mapping.setdefault("unmapped", []).append(f)

        # Decision Logic:
        active_task_ids = [k for k in mapping.keys() if k != "unmapped"]

        if len(active_task_ids) == 1 and not mapping.get("unmapped"):
            return {
                "status": "proceed",
                "task_id": active_task_ids[0],
                "files": changed_files,
            }

        return {
            "status": "plan_required",
            "mapping": mapping,
            "potential_tasks": {t["id"]: t["title"] for t in potential_tasks},
        }
