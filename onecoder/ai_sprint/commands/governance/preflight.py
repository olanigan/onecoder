import click
import os
import sys
from ..common import console, SPRINT_DIR, PROJECT_ROOT, auto_detect_sprint_id
from ...preflight import SprintPreflight


@click.command()
@click.option("--fix", is_flag=True, help="Attempt to fix simple issues")
@click.option("--sprint-id", help="Sprint ID to preflight")
@click.option("--staged", is_flag=True, help="Only preflight staged files")
@click.option("--files", "-f", help="Files to preflight (comma-separated)")
def preflight(fix, sprint_id, staged, files):
    """Validate sprint readiness and governance adherence."""
    if os.environ.get("ONECODER_SKIP_PREFLIGHT") == "true":
        console.print(
            "[yellow]Bypassing preflight checks due to ONECODER_SKIP_PREFLIGHT=true[/yellow]"
        )
        return

    active_sprint = sprint_id or auto_detect_sprint_id()
    if not active_sprint:
        console.print("[bold red]Error:[/bold red] No active sprint detected.")
        return
    sprint_dir = SPRINT_DIR / active_sprint
    preflight_engine = SprintPreflight(sprint_dir, PROJECT_ROOT)

    file_list = [f.strip() for f in files.split(",") if f.strip()] if files else None

    score, results = preflight_engine.run_all(staged=staged, files=file_list)
    for res in results:
        status_icon = (
            "✅"
            if res["status"] == "passed"
            else ("❌" if res["status"] == "failed" else "⚠️")
        )
        color = (
            "green"
            if res["status"] == "passed"
            else ("red" if res["status"] == "failed" else "yellow")
        )
        console.print(
            f"  {status_icon} [{color}]{res['name']}[/{color}]: {res['message']}"
        )
    has_failures = any(res["status"] == "failed" for res in results)
    if score < 75 or has_failures:
        sys.exit(1)
