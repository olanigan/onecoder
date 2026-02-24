"""Submodule integrity checks for sprint-cli."""

import subprocess
from pathlib import Path
from typing import List, Tuple


def get_submodules(project_root: Path) -> List[Tuple[str, str]]:
    """Get list of submodules with their paths and URLs.

    Returns:
        List of tuples (submodule_path, submodule_url)
    """
    try:
        result = subprocess.run(
            ["git", "config", "--file", ".gitmodules", "--get-regexp", "path"],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root,
        )

        submodules = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Format: submodule.{name}.path {path}
            parts = line.split()
            if len(parts) >= 2:
                submodule_path = parts[1]
                submodules.append(submodule_path)

        return submodules
    except subprocess.CalledProcessError:
        return []


def check_submodule_pushed(submodule_path: str, project_root: Path) -> bool:
    """Check if the current HEAD of a submodule exists on its remote.

    Args:
        submodule_path: Relative path to the submodule
        project_root: Root directory of the project

    Returns:
        True if the current commit exists on remote, False otherwise
    """
    submodule_dir = project_root / submodule_path

    if not submodule_dir.exists():
        return True  # Submodule not initialized, skip check

    # Check if submodule is actually initialized (has .git)
    if not (submodule_dir / ".git").exists():
        return True  # Submodule not initialized, skip check

    try:
        # Get current HEAD commit
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=submodule_dir,
        )
        current_commit = head_result.stdout.strip()

        # Check if this commit exists on the remote by searching the SHA in ls-remote output.
        # This is the most reliable way as it doesn't depend on local remote refs.
        ls_remote_result = subprocess.run(
            ["git", "ls-remote", "origin"],
            capture_output=True,
            text=True,
            check=False,
            cwd=submodule_dir,
        )

        if (
            ls_remote_result.returncode == 0
            and current_commit in ls_remote_result.stdout
        ):
            return True

        # Alternative check: try to verify the commit exists on remote
        # by checking if we can fetch it (this is more reliable)
        verify_result = subprocess.run(
            ["git", "branch", "-r", "--contains", current_commit],
            capture_output=True,
            text=True,
            cwd=submodule_dir,
        )

        # If any remote branch contains this commit, it's pushed
        return bool(verify_result.stdout.strip())

    except subprocess.CalledProcessError:
        # If we can't determine, assume it's not pushed (fail-safe)
        return False


def get_unpushed_submodules(project_root: Path) -> List[Tuple[str, str]]:
    """Get list of submodules with unpushed commits.

    Returns:
        List of tuples (submodule_path, current_commit_hash)
    """
    submodules = get_submodules(project_root)
    unpushed = []

    for submodule_path in submodules:
        if not check_submodule_pushed(submodule_path, project_root):
            # Get the current commit hash for reporting
            submodule_dir = project_root / submodule_path
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=submodule_dir,
                )
                commit_hash = result.stdout.strip()
                unpushed.append((submodule_path, commit_hash))
            except subprocess.CalledProcessError:
                unpushed.append((submodule_path, "unknown"))

    return unpushed


def push_submodule(submodule_path: str, project_root: Path) -> bool:
    """Push the current branch of a submodule to its remote.

    Args:
        submodule_path: Relative path to the submodule
        project_root: Root directory of the project

    Returns:
        True if the push was successful, False otherwise
    """
    submodule_dir = project_root / submodule_path
    try:
        # We assume pushing to 'origin' on the current branch
        # git push origin HEAD pushes the current branch to its remote tracking branch
        subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=submodule_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False
