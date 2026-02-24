import re
import subprocess
import os
from typing import Dict, List, Optional
from pathlib import Path


ALLOWED_TRAILERS = {
    "Sprint-Id": r"(?i)\d{3}-[a-z0-9.-]+",
    "Task-Id": r"task-\d+",
    "Status": r"(planning|in-progress|review|done)",
    "Validation": r"[\w:/._\s-]+",
    # Patched: Allow OS-EXT prefix
    "Spec-Id": r"(?:SPEC|OS-EXT)-[A-Z]+-\d{3}(\.\d+)*",
    "Component": r"[a-z0-9-]+",
    "Related-Issue": r"[\w-]+",
    "External-Id": r"[\w-]+",
    "External-Platform": r"(jira|linear|github)",
    "Decision-Reason": r".+",
}


def validate_trailers(trailers: Dict[str, str]) -> List[str]:
    """Validate trailer keys and values."""
    errors = []

    for key, value in trailers.items():
        if key not in ALLOWED_TRAILERS:
            errors.append(f"Unknown trailer key: {key}")
            continue

        pattern = ALLOWED_TRAILERS[key]
        if not re.match(pattern, value):
            errors.append(f"Invalid value for {key}: {value}")

    return errors


def create_commit_with_trailers(
    message: str,
    trailers: Dict[str, str],
    files: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
) -> bool:
    """Create a git commit with structured trailers.

    Builds the commit message with trailers in the body to ensure
    compatibility across git versions and avoid line wrapping issues.
    """
    # Build commit message with trailers in body
    commit_msg = message
    if trailers:
        commit_msg += "\n"  # Blank line before trailers
        for key, value in trailers.items():
            commit_msg += f"\n{key}: {value}"

    cmd = ["git", "commit", "-m", commit_msg]

    if files:
        cmd.extend(files)

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd or Path.cwd(),
        )
        return True
    except subprocess.CalledProcessError as e:
        # Print error for debugging
        print(f"Git commit failed: {e.stderr} {e.stdout}")
        return False


def auto_detect_sprint_id(cwd: Optional[Path] = None) -> Optional[str]:
    """Auto-detect sprint ID from environment, branch name or current directory."""
    # 0. Try Environment Variable first
    env_id = os.environ.get("ACTIVE_SPRINT_ID")
    if env_id:
        return env_id

    # 1. Try branch name first
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=cwd or Path.cwd(),
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            # Match sprint/018-something
            match = re.match(r"^sprint/(\d{3}-[a-z0-9.-]+)", branch)
            if match:
                return match.group(1)
    except Exception:
        pass

    # 2. Fallback to directory detection
    work_dir = cwd or Path.cwd()
    if work_dir.name.startswith(".sprint"):
        return None

    for parent in [work_dir] + list(work_dir.parents):
        if parent.name.startswith(".sprint"):
            continue

        sprint_dirs = parent / ".sprint"
        if sprint_dirs.exists():
            for sprint in sorted(sprint_dirs.iterdir(), reverse=True):
                if sprint.is_dir() and re.match(r"^\d{3}-", sprint.name):
                    return sprint.name

    return None


def parse_trailers(commit_hash: str, cwd: Optional[Path] = None) -> Dict[str, str]:
    """Parse trailers from a commit message."""
    try:
        # Get full commit message including body
        result = subprocess.run(
            ["git", "show", "-s", "--format=%B", commit_hash],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd or Path.cwd(),
        )
    except subprocess.CalledProcessError:
        return {}

    trailers = {}
    lines = result.stdout.strip().split("\n")

    # We look for Key: Value pairs, usually at the end of the message
    # A simple but effective regex for trailers
    trailer_pattern = re.compile(r"^([A-Z][a-zA-Z0-9-]+):\s+(.+)$")

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue

        match = trailer_pattern.match(line)
        if match:
            key, value = match.groups()
            # Only include allowed trailers or common ones
            if key in ALLOWED_TRAILERS:
                trailers[key] = value
        elif trailers:
            # If we found trailers but then a line that doesn't match,
            # we likely reached the end of the trailer block
            break

    # Also look for [Key: Value] in the first line (subject)
    if lines:
        subject = lines[0]
        # Match [Key: Value] where Key starts with capital letter and follows trailer naming
        subject_trailers = re.findall(r"\[([A-Z][a-zA-Z0-9-]+):\s*([^\]]+)\]", subject)
        for key, value in subject_trailers:
            if key in ALLOWED_TRAILERS:
                trailers[key] = value

    return trailers
