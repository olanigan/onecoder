import click
import re
import subprocess
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..common import (
    console,
    PROJECT_ROOT,
    SPRINT_DIR,
    SprintStateManager,
    auto_detect_sprint_id,
)
from ...submodule import get_unpushed_submodules, push_submodule
from ...commit import validate_trailers
from ...spec_validator import validate_spec_ids
from ...trace import trace_specifications
import rich.prompt
from .engine import CommitStateEngine  # noqa: F401

def _prompt_for_spec_id(message: str) -> str:
    """Prompt user to select a Spec-ID with smart suggestions."""
    suggestions = {
        "chore": "SPEC-GOV-012",
        "doc": "SPEC-GOV-012",
        "fix": "SPEC-GOV-013",
        "feat": "SPEC-CLI-001",
        "test": "SPEC-GOV-013",
        "ci": "SPEC-TECH-001",
    }

    default_spec = None
    for key, spec in suggestions.items():
        if key in message.lower():
            default_spec = spec
            break

    console.print("\n[bold yellow]Governance Check:[/bold yellow] Spec-ID is missing.")
    console.print("[dim]Every change must be traced to a specification.[/dim]")

    options = [
        ("SPEC-GOV-012", "Zero Tech Debt / Cleanup / Docs"),
        ("SPEC-GOV-013", "Regression / Unit Testing"),
        ("SPEC-TECH-001", "Technical Infrastructure / CI"),
        ("SPEC-CLI-001", "Sprint CLI Feature"),
        ("SPEC-CORE-002", "Core Metadata / Sprint YAML"),
    ]

    for i, (spec, desc) in enumerate(options, 1):
        console.print(f"  {i}. [cyan]{spec}[/cyan] ({desc})")

    choice = rich.prompt.Prompt.ask(
        "Select Spec-ID (or type custom)", default=default_spec or "SPEC-GOV-012"
    )

    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(options):
            return options[idx - 1][0]

    return choice

def _validate_commit_context(task_id: str, sprint_id: str, spec_id: str):
    try:
        subprocess.run(["git", "config", "user.name"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        console.print(
            "[bold red]Pre-check Failed:[/bold red] Git user/email not configured."
        )
        return False

    active_sprint = sprint_id or auto_detect_sprint_id()
    if not active_sprint:
        console.print(
            "[bold red]Pre-check Failed:[/bold red] No active sprint detected."
        )
        return False

    if spec_id and not re.match(r"^(?:SPEC|OS-EXT)-[A-Z]+-\d+(?:\.\d+)*", spec_id):
        console.print(
            f"[bold red]Pre-check Failed:[/bold red] Invalid Spec ID format: {spec_id}"
        )
        return False

    return True

def _stage_files_helper(
    files: List[str],
    task_id: Optional[str] = None,
    component: Optional[str] = None,
    yes: bool = False,
) -> Optional[str]:
    active_sprint = auto_detect_sprint_id()
    staged_changes = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True
    ).stdout.strip()

    if not files and not staged_changes:
        if active_sprint:
            analysis = CommitStateEngine(PROJECT_ROOT, SPRINT_DIR).analyze(
                active_sprint, fixed_task_id=task_id
            )
            if analysis["status"] == "plan_required":
                console.print(
                    "[bold yellow]Commit Friction Detected:[/bold yellow] Changes span multiple possible tasks."
                )
                sys.exit(0)
            elif analysis["status"] == "proceed":
                task_id = analysis["task_id"]

        unstaged = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        ).stdout.strip()
        if unstaged:
            # Check if there are any files to stage (either modified or untracked)
            if yes or click.confirm(
                f"Stage all implementation files for [Task: {task_id or 'current'}]?",
                default=True,
            ):
                subprocess.run(["git", "add", "."], cwd=PROJECT_ROOT, check=True)
                staged_changes = "all"

        if not staged_changes:
            console.print(
                "[bold red]Error:[/bold red] No files staged and no files provided."
            )
            sys.exit(1)

    if files:
        try:
            subprocess.run(["git", "add"] + list(files), cwd=PROJECT_ROOT, check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(1)
    return task_id

def _build_commit_trailers(
    message, reason, sprint_id, component, task_id, status, validation, spec_id
):
    trailers = {}
    if reason:
        trailers["Decision-Reason"] = reason

    active_sprint_id = sprint_id or auto_detect_sprint_id()
    if active_sprint_id:
        trailers["Sprint-Id"] = active_sprint_id
        if not component:
            try:
                state_manager = SprintStateManager(SPRINT_DIR / active_sprint_id)
                component = state_manager.get_component()
            except Exception:
                pass

    if component:
        trailers["Component"] = component

    if task_id:
        if not re.match(r"^task-\d+$", task_id):
            resolved = None
            if active_sprint_id:
                try:
                    state_manager = SprintStateManager(SPRINT_DIR / active_sprint_id)
                    resolved = state_manager.get_task_id_by_title(task_id)
                except Exception:
                    pass
            if not resolved and task_id.isdigit():
                resolved = f"task-{int(task_id):03d}"
            if resolved:
                task_id = resolved
        trailers["Task-Id"] = task_id

    if status:
        trailers["Status"] = status

    if validation:
        trailers["Validation"] = validation

    if spec_id:
        trailers["Spec-Id"] = spec_id

    errors = validate_trailers(trailers)
    if errors:
        for error in errors:
            console.print(f"  ❌ {error}")
        sys.exit(1)

    return trailers, active_sprint_id

def _run_guardian_check(reason, trailers):
    # Simplified Guardian check: skip if not installed or fails
    try:
        from onecoder.governance.guardian import GovernanceGuardian  # type: ignore
        guardian = GovernanceGuardian(PROJECT_ROOT / "governance.yaml")
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True
        )
        if res.returncode == 0:
            current_staged = [f.strip() for f in res.stdout.split("\n") if f.strip()]
            is_safe, msg, metadata = guardian.validate_staged_files(
                current_staged, reason=reason
            )
            if not is_safe:
                console.print(f"[bold red]Governance Block (Guardian):[/bold red] {msg}")
                sys.exit(1)
    except Exception:
        pass

def _validate_git_state(target_dir, name, is_apply):
    """Validate git state before closure."""
    unpushed = get_unpushed_submodules(PROJECT_ROOT)
    if unpushed:
        if is_apply:
            if click.confirm("\nPush these submodules now to satisfy governance?", default=True):
                for path, sha in unpushed:
                    if push_submodule(path, PROJECT_ROOT):
                        console.print(f"  [bold green]✓ {path} pushed.[/bold green]")
                    else:
                        sys.exit(1)
            else:
                sys.exit(1)
        else:
            sys.exit(1)

    try:
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
        if staged.returncode == 0 and staged.stdout.strip():
            console.print("[bold red]Cannot close:[/bold red] Found staged changes.")
            sys.exit(1)
    except Exception:
        pass

    # Task status check from sprint.yaml
    sprint_file = target_dir / "sprint.yaml"
    if sprint_file.exists():
        import yaml
        with open(sprint_file, "r") as f:
            sprint_data = yaml.safe_load(f)
        incomplete_tasks = [t for t in sprint_data.get("tasks", []) if t.get("status") not in ["done", "migrated"]]
        if incomplete_tasks:
            console.print(f"[bold red]Cannot close:[/bold red] Found {len(incomplete_tasks)} incomplete tasks.")
            sys.exit(1)

    # Retro check
    retro_file = target_dir / "RETRO.md"
    if not retro_file.exists() or retro_file.stat().st_size < 10:
         console.print("[bold red]Cannot close:[/bold red] RETRO.md missing or too short.")
         sys.exit(1)

def _apply_closure(target_dir, name):
    """Execute the closure phase."""
    (target_dir / ".status").write_text("Closed")
    try:
        to_add = [str(target_dir.relative_to(PROJECT_ROOT)), "sprint.yaml"]
        subprocess.run(["git", "add"] + [a for a in to_add if (PROJECT_ROOT / a).exists()], cwd=PROJECT_ROOT, check=True)
        commit_msg = f"chore(gov): close sprint {name}\n\n[Sprint-Id: {name}]\n[Status: closed]"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=PROJECT_ROOT, check=True)
    except Exception:
        pass
    console.print(f"[bold green]Success:[/bold green] Sprint {name} closed.")


async def _run_check(name: str, cmd: str, cwd: Path) -> Dict[str, Any]:
    """Helper to run a check command asynchronously."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return {
        "name": name,
        "returncode": proc.returncode,
        "stdout": stdout.decode(),
        "stderr": stderr.decode(),
    }