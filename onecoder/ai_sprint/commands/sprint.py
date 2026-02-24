import click
import re
import json
import subprocess
from pathlib import Path
from .common import (
    console,
    PROJECT_ROOT,
    SPRINT_DIR,
    SprintStateManager,
    auto_detect_sprint_id,
)
import datetime
import shutil


def create_sprint_structure(
    target_dir: Path, name: str, exist_ok: bool = False, is_tech_debt: bool = False
):
    target_dir.mkdir(parents=True, exist_ok=exist_ok)
    (target_dir / "planning").mkdir(exist_ok=True)
    (target_dir / "logs").mkdir(exist_ok=True)
    (target_dir / "context").mkdir(exist_ok=True)
    (target_dir / "media").mkdir(exist_ok=True)

    readme_file = target_dir / "README.md"
    if not readme_file.exists():
        with open(readme_file, "w") as f:
            title = (
                f"Tech Debt Remediation: {name}" if is_tech_debt else f"Sprint: {name}"
            )
            goal = (
                "Reduce cyclomatic complexity and improve codebase health."
                if is_tech_debt
                else "Describe the goal of this sprint."
            )
            f.write(f"# {title}\n\n## Goal\n{goal}\n")

    todo_file = target_dir / "TODO.md"
    if not todo_file.exists():
        with open(todo_file, "w") as f:
            content = "# Sprint TODO\n\n## High Priority\n"
            if is_tech_debt:
                content += "- [ ] Baseline Debt Scan (onecoder tldr complexity)\n"
                content += "- [ ] Identify high-complexity functions (>10)\n"
                content += "- [ ] Refactor target components\n"
            else:
                content += "- [ ] \n"
            content += "\n## Backlog\n- [ ] \n"
            f.write(content)

    retro_file = target_dir / "RETRO.md"
    if not retro_file.exists():
        with open(retro_file, "w") as f:
            f.write(
                "# Retrospective\n\n"
                "## Went Well\n\n"
                "## To Improve\n\n"
                "## Action Items\n\n"
                "## Tech Debt Analytics\n"
                "<!-- Complexity Delta and TTR/TTU stats will be referenced here -->\n"
            )


@click.command()
@click.argument("name", required=False)
@click.option("--name", "name_option", help="Name of the sprint directory")
@click.option(
    "--branch/--no-branch",
    default=True,
    help="Automatically create and switch to a git branch",
)
@click.option("--component", help="Component scope for this sprint")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "--ztd", is_flag=True, help="Zero Tech Debt mode: skip review confirmation"
)
def init(name, name_option, branch, component, yes, ztd):
    """Initialize a new sprint directory structure."""
    if not name:
        name = name_option
    if not name:
        name = click.prompt("Sprint Name")

    if (
        not yes
        and not ztd
        and not click.confirm("Have you reviewed the pending .issues/ and backlog?")
    ):
        console.print("[bold yellow]Aborted.[/bold yellow]")
        return

    # Git Config Check
    try:
        subprocess.run(["git", "config", "user.name"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        console.print(
            "[yellow]Warning: Git user.name not configured. Commits may fail.[/yellow]"
        )

    match = re.match(r"^(\d{3})-", name)
    if match:
        next_num = int(match.group(1))
    else:
        max_num = 0
        if SPRINT_DIR.exists():
            for item in SPRINT_DIR.iterdir():
                if item.is_dir():
                    match_dir = re.match(r"^(\d{3})-", item.name)
                    if match_dir:
                        num = int(match_dir.group(1))
                        if num > max_num:
                            max_num = num
        next_num = max_num + 1
        name = f"{next_num:03d}-{name}"

    target_dir = SPRINT_DIR / name
    if target_dir.exists():
        console.print(
            f"[bold red]Error:[/bold red] Directory {target_dir} already exists."
        )
        return

    try:
        is_tech_debt = False
        if next_num % 3 == 0 and not yes:
            if click.confirm(
                f"[bold yellow]Sprint {next_num} is a Tech Debt Remediation cycle.[/bold yellow] Flag as tech debt?"
            ):
                is_tech_debt = True
        elif next_num % 3 == 0:
            is_tech_debt = True

        create_sprint_structure(target_dir, name, is_tech_debt=is_tech_debt)
        state_manager = SprintStateManager(target_dir)
        initial_state = state_manager.create_initial_state(name, name, component)

        if is_tech_debt:
            initial_state.setdefault("metadata", {})["labels"].append("tech-debt")
            initial_state["goals"]["primary"] = (
                "Tech Debt Remediation & Codebase Health"
            )
            initial_state["tasks"].append(
                {
                    "id": "task-001",
                    "title": "Baseline Debt Scan (onecoder tldr complexity)",
                    "status": "todo",
                    "type": "analysis",
                }
            )

        state_manager.save(initial_state)
        console.print(
            f"[bold green]Success:[/bold green] Initialized sprint at [cyan]{target_dir}[/cyan]"
        )

        if branch:
            branch_name = f"sprint/{name}"
            subprocess.run(
                ["git", "checkout", "-b", branch_name], check=True, capture_output=True
            )
            console.print(
                f"[bold green]Success:[/bold green] Created branch [cyan]{branch_name}[/cyan]"
            )

        # Gitignore check
        gitignore_path = PROJECT_ROOT / ".gitignore"
        defaults = [
            ".env",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            ".DS_Store",
            "dist/",
            "build/",
        ]
        added = []
        if not gitignore_path.exists():
            with open(gitignore_path, "w") as f:
                f.write("\n".join(defaults) + "\n")
            console.print("[dim]Created .gitignore with defaults.[/dim]")
        else:
            current_ignore = gitignore_path.read_text()
            with open(gitignore_path, "a") as f:
                if not current_ignore.endswith("\n"):
                    f.write("\n")
                for d in defaults:
                    if d not in current_ignore:
                        f.write(f"{d}\n")
                        added.append(d)
            if added:
                console.print(f"[dim]Updated .gitignore with: {', '.join(added)}[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Failed to initialize: {e}")
        return

    console.print("\n[cyan]Running sprint preflight check...[/cyan]")
    from ..preflight import SprintPreflight

    preflight = SprintPreflight(target_dir, PROJECT_ROOT)
    score, results = preflight.run_all()

    for res in results:
        status_icon = (
            "✅"
            if res.get("status") == "passed"
            else ("❌" if res.get("status") == "failed" else "⚠️")
        )
        color = (
            "green"
            if res.get("status") == "passed"
            else ("red" if res.get("status") == "failed" else "yellow")
        )
        message = res.get("message", "No details provided.")
        console.print(
            f"  {status_icon} [{color}]{res.get('name', 'Unknown')}[/{color}]: {message}"
        )

    if score >= 75:
        console.print(
            f"\n[bold green]Preflight Passed![/bold green] Score: {score}/100"
        )
    else:
        console.print(f"\n[bold red]Preflight Failed![/bold red] Score: {score}/100")

    # Inject Governance Prompt
    from ..guidance import GuidanceEngine
    from rich.panel import Panel

    engine = GuidanceEngine(PROJECT_ROOT)
    prompt = engine.generate_init_prompt(name)
    console.print(
        Panel(
            prompt, title="[bold red]AGENT INSTRUCTIONS[/bold red]", border_style="red"
        )
    )


@click.command()
@click.argument("name")
def update(name):
    """Update an existing sprint with missing templates."""
    target_dir = SPRINT_DIR / name
    if not target_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Sprint {name} does not exist.")
        return
    try:
        create_sprint_structure(target_dir, name, exist_ok=True)
        console.print(
            f"[bold green]Success:[/bold green] Updated sprint at {target_dir}"
        )
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Failed to update: {e}")


@click.command()
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
def status(json_output):
    """Show the current status of the sprint."""
    if not SPRINT_DIR.exists():
        if json_output:
            console.print(
                json.dumps({"error": "No .sprint directory found", "sprints": []})
            )
        else:
            console.print("[yellow]No .sprint directory found.[/yellow]")
        return

    sprints = []
    for item in sorted(SPRINT_DIR.iterdir()):
        if item.is_dir():
            status_file = item / ".status"
            state = "Active"
            if status_file.exists():
                with open(status_file, "r") as f:
                    state = f.read().strip()
            sprints.append({"name": item.name, "status": state, "path": str(item)})

    if json_output:
        console.print(json.dumps({"sprints": sprints}, indent=2))
        return

    from rich.table import Table

    table = Table(title="Available Sprints")
    table.add_column("Sprint Name", style="cyan")
    table.add_column("Status", style="magenta")

    for sprint in sprints:
        color = "green" if sprint["status"] == "Active" else "dim white"
        table.add_row(sprint["name"], f"[{color}]{sprint['status']}[/{color}]")
    console.print(table)


@click.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--name", help="Display name for the media artifact")
def capture(file_path, name):
    """Capture and attach media (screenshot, clip) to the active sprint."""
    sprint_id = auto_detect_sprint_id()
    if not sprint_id:
        console.print(
            "[bold red]Error:[/bold red] No active sprint detected. Run from a sprint directory or use --sprint."
        )
        return

    sprint_dir = SPRINT_DIR / sprint_id
    media_dir = sprint_dir / "media"
    media_dir.mkdir(exist_ok=True)

    src = Path(file_path)
    dest = media_dir / src.name

    if dest.exists():
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        dest = media_dir / f"{src.stem}_{timestamp}{src.suffix}"

    shutil.copy2(src, dest)

    # Update sprint state
    sm = SprintStateManager(sprint_dir)
    state = sm.load()

    media_entry = {
        "name": name or src.name,
        "path": f"media/{dest.name}",
        "captured_at": str(datetime.datetime.now()),
        "original_source": str(src.absolute()),
    }

    state.setdefault("artifacts", {}).setdefault("media", []).append(media_entry)
    sm.save(state)

    console.print(
        f"[bold green]✓ Captured:[/bold green] {src.name} -> {dest.relative_to(PROJECT_ROOT)}"
    )


@click.command()
@click.argument("name", required=False)
def migrate(name):
    """Migrate sprint state from JSON to YAML."""
    sprint_id = name or auto_detect_sprint_id()
    if not sprint_id:
        console.print("[bold red]Error:[/bold red] No sprint detected.")
        return

    sprint_dir = SPRINT_DIR / sprint_id
    if not sprint_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Sprint {sprint_id} not found.")
        return

    json_file = sprint_dir / "sprint.json"
    yaml_file = sprint_dir / "sprint.yaml"

    if not json_file.exists():
        if yaml_file.exists():
            console.print(
                f"[green]Sprint {sprint_id} is already migrated to YAML.[/green]"
            )
        else:
            console.print("[red]No state file found.[/red]")
        return

    console.print(f"[cyan]Migrating Sprint {sprint_id} to YAML...[/cyan]")

    # Force load JSON
    try:
        with open(json_file) as f:
            state = json.load(f)
    except Exception as e:
        console.print(f"[bold red]Error loading JSON:[/bold red] {e}")
        return

    # Use State Manager to save as YAML (relying on its internal logic or forcing it)
    sm = SprintStateManager(sprint_dir)
    # We manually set state file to yaml to force save path
    sm.state_file = yaml_file

    try:
        sm.save(state)
        console.print(f"[green]✓ Saved {yaml_file}[/green]")

        # Archive JSON instead of deleting immediately for safety
        archive_dir = sprint_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        shutil.move(
            str(json_file),
            str(
                archive_dir
                / f"sprint.json.bak.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            ),
        )
        console.print(f"[dim]Archived sprint.json to {archive_dir}[/dim]")

    except Exception as e:
        console.print(f"[bold red]Migration Failed:[/bold red] {e}")
        # If save failed, don't delete JSON
