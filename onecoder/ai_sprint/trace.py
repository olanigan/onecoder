import subprocess
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from .commit import parse_trailers


def get_sprint_tasks(sprint_id: str, project_root: Optional[Path] = None) -> List[str]:
    """Load valid task IDs from sprint.json."""
    if not project_root:
        project_root = Path.cwd()
    sprint_json = project_root / ".sprint" / sprint_id / "sprint.json"
    if not sprint_json.exists():
        return []
    try:
        with open(sprint_json, "r") as f:
            data = json.load(f)
            return [t["id"] for t in data.get("tasks", [])]
    except Exception:
        return []


def get_git_history(
    limit: int = 100, cwd: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Fetch git history with hashes and full messages."""
    cmd = ["git", "log", "-n", str(limit), "--format=%H%n%B%n--COMMIT-END--"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, cwd=cwd or Path.cwd()
        )
        commits = []
        raw_commits = result.stdout.split("--COMMIT-END--")
        for raw in raw_commits:
            if not raw.strip():
                continue
            lines = raw.strip().split("\n")
            if not lines:
                continue
            commit_hash = lines[0]
            message = "\n".join(lines[1:])
            commits.append({"hash": commit_hash, "message": message})
        return commits
    except subprocess.CalledProcessError:
        return []


def get_commit_files(commit_hash: str, cwd: Optional[Path] = None) -> List[str]:
    """Get list of files changed in a commit."""
    cmd = ["git", "show", "--name-only", "--format=", commit_hash]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, cwd=cwd or Path.cwd()
        )
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        return []


def trace_specifications(project_root: Path, limit: int = 100) -> Dict[str, Any]:
    """Traverse history and build a traceability map."""
    commits = get_git_history(limit, project_root)
    trace_map: Dict[str, Any] = {
        "specs": {},  # Map SPEC-ID -> List of commits/tasks
        "sprints": {},  # Map Sprint-ID -> List of tasks/commits
        "tasks": {},  # Map Task-Id -> List of commits
        "audit": [],  # List of Procedural Integrity flags
    }

    for commit in commits:
        trailers = parse_trailers(commit["hash"], cwd=project_root)
        if not trailers:
            continue

        sprint_id = trailers.get("Sprint-Id")
        task_ids = trailers.get("Task-Id", "").split(",")
        task_ids = [t.strip() for t in task_ids if t.strip()]
        spec_ids = trailers.get("Spec-Id", "").split(",")
        spec_ids = [s.strip() for s in spec_ids if s.strip()]

        files_changed = get_commit_files(commit["hash"], project_root)
        has_impl_changes = any(
            not (
                f.startswith(".sprint/")
                or f in ["TODO.md", "RETRO.md", "README.md", "sprint.json"]
            )
            for f in files_changed
        )

        commit_info = {
            "hash": commit["hash"][:7],
            "message": commit["message"].split("\n")[0],
            "sprint_id": sprint_id,
            "task_ids": task_ids,
            "spec_ids": spec_ids,
            "has_impl_changes": has_impl_changes,
            "files_count": len(files_changed),
        }

        # Procedural Integrity Detection: documentation-only commit for a technical task (heuristic)
        is_done = trailers.get("Status") == "done"
        if is_done and not has_impl_changes:
            # Check if it's a documentation-only commit
            # We skip flagging if the message explicitly says 'docs' or 'chore'
            msg_lower = commit["message"].lower()
            if not any(
                x in msg_lower for x in ["docs", "chore", "governance", "retro"]
            ):
                trace_map["audit"].append(
                    {
                        "type": "Procedural Integrity Violation: Documentation-only completion",
                        "id": ",".join(task_ids) or sprint_id,
                        "commit": commit_info["hash"],
                        "message": commit_info["message"],
                    }
                )

        # Index by Spec
        for spec_id in spec_ids:
            if spec_id not in trace_map["specs"]:
                trace_map["specs"][spec_id] = {
                    "commits": [],
                    "tasks": set(),
                    "sprints": set(),
                }
            trace_map["specs"][spec_id]["commits"].append(commit_info)
            for tid in task_ids:
                trace_map["specs"][spec_id]["tasks"].add(tid)
            if sprint_id:
                trace_map["specs"][spec_id]["sprints"].add(sprint_id)

        # Index by Sprint
        if sprint_id:
            if sprint_id not in trace_map["sprints"]:
                trace_map["sprints"][sprint_id] = {
                    "tasks": {},
                    "commits": [],
                    "valid_tasks": get_sprint_tasks(sprint_id, project_root),
                }

            trace_map["sprints"][sprint_id]["commits"].append(commit_info)

            # Procedural Integrity Detection: Fake Task ID
            valid_tasks = trace_map["sprints"][sprint_id]["valid_tasks"]
            for tid in task_ids:
                if valid_tasks and tid not in valid_tasks:
                    trace_map["audit"].append(
                        {
                            "type": "Procedural Integrity Violation: Fake Task ID",
                            "id": tid,
                            "commit": commit_info["hash"],
                            "message": f"Task ID '{tid}' not found in {sprint_id}/sprint.json",
                        }
                    )

            for tid in task_ids:
                if tid not in trace_map["sprints"][sprint_id]["tasks"]:
                    trace_map["sprints"][sprint_id]["tasks"][tid] = []
                trace_map["sprints"][sprint_id]["tasks"][tid].append(commit_info)

        # Index by Task
        for tid in task_ids:
            if tid not in trace_map["tasks"]:
                trace_map["tasks"][tid] = []
            trace_map["tasks"][tid].append(commit_info)

    # Convert sets to lists for JSON serialization
    for spec in trace_map["specs"].values():
        spec["tasks"] = list(spec["tasks"])
        spec["sprints"] = list(spec["sprints"])

    return trace_map
