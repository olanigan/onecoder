import click
import os
import sys
import subprocess
from ..common import console, PROJECT_ROOT
from .utils import (
    _validate_commit_context,
    _stage_files_helper,
    _build_commit_trailers,
)
from ...commit import create_commit_with_trailers

@click.command()
@click.option("--message", "-m", required=True, help="Commit message")
@click.option("--task-id", help="Task identifier")
@click.option("--task", help="Alias for --task-id")
@click.option(
    "--status", help="Task status (planning, in-progress, review, done, completed)"
)
@click.option("--validation", help="Validation status or URI")
@click.option("--sprint-id", help="Override sprint ID")
@click.option("--spec-id", help="Specification ID(s)")
@click.option("--component", help="Component scope")
@click.option(
    "--files",
    "-f",
    multiple=True,
    help="Files to stage (can be repeated or comma-separated)",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.argument("files_args", nargs=-1, type=click.Path())
def commit(
    message,
    task_id,
    task,
    status,
    validation,
    sprint_id,
    spec_id,
    component,
    files,
    yes,
    files_args,
):
    """Create atomic commit with metadata trailers."""

    all_files = list(files_args)
    for f_opt in files:
        all_files.extend([f.strip() for f in f_opt.split(",") if f.strip()])

    if os.environ.get("ONECODER_SKIP_PREFLIGHT") == "true":
        console.print("[yellow]Bypassing governance checks due to ONECODER_SKIP_PREFLIGHT=true[/yellow]")
        if all_files:
            subprocess.run(["git", "add"] + all_files, cwd=PROJECT_ROOT, check=True)

    if task and not task_id:
        task_id = task
    if status == "completed":
        status = "done"

    if status and status not in ["planning", "in-progress", "review", "done"]:
        console.print(f"[bold red]Error:[/bold red] Invalid status: {status}")
        sys.exit(1)

    if not spec_id:
        from .utils import _prompt_for_spec_id
        spec_id = _prompt_for_spec_id(message)
        if not spec_id:
            console.print("[bold red]Governance Violation:[/bold red] --spec-id is mandatory.")
            sys.exit(1)

    if not _validate_commit_context(task_id, sprint_id, spec_id):
        sys.exit(1)

    # If yes is true and we have unstaged/untracked changes, they should be added
    task_id = _stage_files_helper(all_files, task_id=task_id, component=component, yes=yes)

    trailers, active_sprint_id = _build_commit_trailers(
        message, None, sprint_id, component, task_id, status, validation, spec_id
    )

    if create_commit_with_trailers(message, trailers, cwd=PROJECT_ROOT):
        console.print("[bold green]Success:[/bold green] Commit created.")
    else:
        sys.exit(1)