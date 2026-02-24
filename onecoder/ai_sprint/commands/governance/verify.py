import click
import json
import asyncio
import sys
from ..common import (
    console,
    PROJECT_ROOT,
    SPRINT_DIR,
    SprintStateManager,
    auto_detect_sprint_id,
)
from ...policy import PolicyEngine
from .utils import _run_check

@click.command()
@click.option("--sprint-id", help="Override sprint ID")
def verify(sprint_id):
    """Verify sprint for technical debt (Zero Errors/Lint)."""
    active_sprint = sprint_id or auto_detect_sprint_id()
    if not active_sprint:
        console.print("[bold red]Error:[/bold red] No active sprint detected.")
        sys.exit(1)

    async def run_verify():
        target_dir = SPRINT_DIR / active_sprint
        state_manager = SprintStateManager(target_dir)
        component = state_manager.get_component()
        if not component:
            console.print(
                "[bold red]Error:[/bold red] No component scope defined."
            )
            sys.exit(1)

        console.print(
            f"[cyan]Verifying component debt for [bold]{component}[/bold]...[/cyan]"
        )
        policy_engine = PolicyEngine(PROJECT_ROOT)
        comp_rules = policy_engine.get_verification_rules().get(component, [])

        tasks = []
        for check in comp_rules:
            cmd = check if isinstance(check, str) else check["cmd"]
            name = check if isinstance(check, str) else check["name"]
            tasks.append(_run_check(name, cmd, PROJECT_ROOT))

        results = {
            "errors": 0,
            "lint_violations": 0,
            "details": [],
        }
        
        if not tasks:
            console.print("[yellow]No verification rules found for this component.[/yellow]")
            return results

        check_results = await asyncio.gather(*tasks)

        for res in check_results:
            if res["returncode"] != 0:
                results["errors"] += 1
                console.print(f"  ❌ [bold red]{res['name']} failed[/bold red]")
            else:
                console.print(f"  ✅ [green]{res['name']} passed[/green]")

        with open(target_dir / ".verification_results.json", "w") as f:
            json.dump(results, f)

        return results

    results = asyncio.run(run_verify())
    if results["errors"] > 0:
        sys.exit(1)
    console.print("\n[bold green]✓ Verification Passed.[/bold green]")