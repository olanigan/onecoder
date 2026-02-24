import click
import datetime
from pathlib import Path
from typing import List, Dict
from .common import (
    console,
    PROJECT_ROOT,
    SPRINT_DIR,
    SprintStateManager,
    auto_detect_sprint_id,
)


def _validate_audit_task(
    task: Dict, sprint_commits: List[Dict], project_root: Path
) -> bool:
    from ..trace import get_commit_files

    for commit in sprint_commits:
        files = get_commit_files(commit["hash"], project_root)
        if any(f.startswith(".issues/") for f in files):
            return True
    return False


def _validate_artifact_task(
    task: Dict, sprint_commits: List[Dict], sprint_dir: Path, project_root: Path
) -> bool:
    from ..trace import get_commit_files

    sprint_rel_path = sprint_dir.relative_to(project_root)
    for commit in sprint_commits:
        files = get_commit_files(commit["hash"], project_root)
        if any(f.startswith(str(sprint_rel_path)) for f in files):
            return True
    return False


@click.command()
@click.argument("task_name")
@click.option(
    "--branch/--no-branch", default=True, help="Create/switch to a sprint branch"
)
@click.option(
    "--type",
    type=click.Choice(["implementation", "audit", "docs", "planning"]),
    help="Task type",
)
@click.pass_context
def start(ctx, task_name, branch, type):
    """Start working on a specific task."""
    console.print(f"[bold blue]Starting task:[/bold blue] {task_name}")
    active_sprint = auto_detect_sprint_id()
    if not active_sprint:
        console.print("[yellow]Warning:[/yellow] No active sprint detected.")
    else:
        sprint_dir = SPRINT_DIR / active_sprint
        if sprint_dir.exists():
            state_manager = SprintStateManager(sprint_dir)
            if not type:
                type = click.prompt(
                    "Task type",
                    type=click.Choice(["implementation", "audit", "docs", "planning"]),
                    default="implementation",
                )
            state = state_manager.load()
            for task in state.get("tasks", []):
                if task.get("id") == task_name or task.get("title") == task_name:
                    task["status"] = "in-progress"
                    task["type"] = type
                    if not task.get("startedAt"):
                        task["startedAt"] = datetime.datetime.now().isoformat()
                    break
            state_manager.save(state)
            state_manager.start_task(task_name)
    timestamp = datetime.datetime.now().isoformat()
    timestamp = datetime.datetime.now().isoformat()
    console.print(f"Recorded start time: {timestamp}")

    # Inject Governance Prompt
    from ..guidance import GuidanceEngine
    from rich.panel import Panel

    engine = GuidanceEngine(PROJECT_ROOT)
    prompt = engine.generate_start_prompt(task_name)
    console.print(
        Panel(
            prompt, title="[bold red]AGENT INSTRUCTIONS[/bold red]", border_style="red"
        )
    )


@click.command(name="continue")
@click.argument("task_name")
@click.option(
    "--branch/--no-branch", default=True, help="Create/switch to a sprint branch"
)
@click.option(
    "--type",
    type=click.Choice(["implementation", "audit", "docs", "planning"]),
    help="Task type",
)
@click.pass_context
def continue_(ctx, task_name, branch, type):
    """Continue working on a specific task (alias for start)."""
    ctx.invoke(start, task_name=task_name, branch=branch, type=type)


@click.command()
@click.argument("task_name", required=False)
@click.option("--message", "-m", help="Commit message")
@click.option("--validation", "-v", help="Validation proof (URI, path, or description)")
@click.option(
    "--spec-id", help="Specification ID to link to (auto-detected if not provided)"
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
def finish(task_name, message, validation, spec_id, yes):
    """Finish the current task and commit changes with validation."""

    if not task_name:
        if yes:
            console.print(
                "[bold red]Error:[/bold red] Task name is required when using --yes"
            )
            import sys

            sys.exit(1)
        task_name = click.prompt("Finished Task Name/ID")

    if not validation:
        if yes:
            console.print(
                "[bold red]Error:[/bold red] Validation proof is required when using --yes"
            )
            import sys

            sys.exit(1)
        validation = click.prompt("Validation Proof")

    if not message:
        default_msg = f"feat: finish task {task_name}"
        if yes:
            message = default_msg
        else:
            message = click.prompt("Commit Message", default=default_msg)

    # Auto-select spec_id for task completion if not provided
    if not spec_id:
        spec_id = "SPEC-GOV-012"  # Default to task completion spec

    console.print(f"[bold green]Finishing task:[/bold green] {task_name}")
    active_sprint_id = auto_detect_sprint_id()
    resolved_task_id = task_name
    if active_sprint_id:
        state_manager = SprintStateManager(SPRINT_DIR / active_sprint_id)
        if state_manager.mark_done(task_name):
            console.print("Task marked as [bold green]done[/bold green]")
            id_lookup = state_manager.get_task_id_by_title(task_name)
            if id_lookup:
                resolved_task_id = id_lookup

    from .governance import commit

    ctx = click.get_current_context()
    ctx.invoke(
        commit,
        message=message,
        task_id=resolved_task_id,
        status="done",
        validation=validation,
        spec_id=spec_id,
    )
