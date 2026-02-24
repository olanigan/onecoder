import click
import re
from datetime import datetime
from pathlib import Path
from ..issues import IssueManager

@click.group()
def issue():
    """Manage local governance issues."""
    pass

@issue.command(name="create")
@click.option("--title", help="Manual title for the issue")
def issue_create(title):
    """Create a new governance issue."""
    from rich.console import Console
    console = Console()
    manager = IssueManager()
    
    if not title:
        title = click.prompt("Issue title")
        
    issue_path = manager.create_issue(title)
    console.print(f"[bold green]✓ Issue created:[/bold green] {issue_path.name}")

@issue.command(name="resolve")
@click.argument("issue_id")
@click.option("--message", "-m", help="Resolution message")
@click.option("--pr", help="Pull Request URL")
def issue_resolve(issue_id, message, pr):
    """Mark an issue as resolved."""
    from rich.console import Console
    import subprocess

    console = Console()
    manager = IssueManager()

    resolution_meta = {"resolved_at": datetime.now().isoformat(), "pr_url": pr}

    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        resolution_meta["commit_sha"] = commit
    except Exception:
        resolution_meta["commit_sha"] = "unknown"

    success = manager.update_status(issue_id, "resolved", resolution_meta)

    if success:
        console.print(f"[bold green]✓ Issue {issue_id} marked as resolved.[/bold green]")
    else:
        console.print(f"[bold red]Error:[/bold red] Issue {issue_id} not found.")

@issue.command(name="list")
def issue_list():
    """List all local governance issues."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    manager = IssueManager()
    issues_dir = manager.issues_dir
    if not issues_dir.exists():
        console.print("[yellow]No .issues directory found.[/yellow]")
        return

    table = Table(title="Local Governance Issues")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="magenta")

    for item in sorted(issues_dir.iterdir()):
        if item.is_file() and item.suffix == ".md" and item.name != "README.md":
            match = re.match(r"^(\d{3})-(.+)\.md$", item.name)
            if match:
                issue_id = match.group(1)
                issue_title = match.group(2).replace("-", " ").capitalize()

                content = item.read_text()
                if any(x in content for x in ["Resolved", "🟢 Resolved", "🟢 **Resolved**"]):
                    status = "[green]Resolved[/green]"
                else:
                    status = "[red]Open[/red]"
                table.add_row(issue_id, issue_title, status)

    console.print(table)