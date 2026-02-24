import click
import sys
import subprocess
from ..common import console, SPRINT_DIR, PROJECT_ROOT
from ...policy import PolicyEngine
from .utils import _validate_git_state, _apply_closure
from .verify import verify

@click.command()
@click.argument("name")
@click.option("--apply", is_flag=True, help="Execute the closure (Apply phase)")
@click.option(
    "--plan",
    is_flag=True,
    default=True,
    help="Only show what would be done (Plan phase, default)",
)
def close(name, apply, plan):
    """Close a sprint if criteria are met (Plan-Apply pattern)."""

    is_apply = apply
    target_dir = SPRINT_DIR / name
    if not target_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Sprint {name} does not exist.")
        sys.exit(1)

    console.print(f"[cyan]Evaluating governance policy for {name}...[/cyan]")
    policy_engine = PolicyEngine(PROJECT_ROOT)

    # 1. Closure Policy Loop
    closure_rules = policy_engine.get_closure_policy()
    while True:
        violations = policy_engine.evaluate_closure(target_dir)
        has_debt = any(
            "Zero-Debt" in v or "verification has not been run" in v for v in violations
        )

        if closure_rules.get("require_zero_debt") and is_apply and has_debt:
            console.print(f"[cyan]Verifying zero-debt status for {name}...[/cyan]")
            try:
                ctx = click.get_current_context()
                ctx.invoke(verify, sprint_id=name)
                violations = policy_engine.evaluate_closure(target_dir)  # Refresh
            except SystemExit as e:
                if e.code != 0:
                    console.print(
                        "[bold red]Cannot close: Zero-Debt verification failed.[/bold red]"
                    )
                    if not click.confirm("Retry verification after manual fix?"):
                        sys.exit(1)
                    continue
            except Exception as e:
                console.print(
                    f"[yellow]Warning:[/yellow] Verification could not be run: {e}"
                )

        if not violations:
            break

        console.print(
            "[bold red]Cannot close: Governance Policy Violations Detected![/bold red]"
        )
        for v in violations:
            console.print(f"  ❌ {v}")

        if plan:
            console.print(
                "\n[dim]Tip: Run with --apply to attempt automatic fixes.[/dim]"
            )
            sys.exit(1)

        console.print("\n[bold cyan]--- Interactive Fix ---[/bold cyan]")
        options = ["Retry", "Apply Auto-fixes", "Abort"]

        choice = click.prompt(
            "Selection",
            type=click.Choice([o.lower().replace(" ", "-") for o in options]),
            default="retry",
        )

        if choice == "apply-auto-fixes":
            is_apply = True
            continue
        elif choice == "retry":
            continue
        else:
            console.print("[red]Closure aborted.[/red]")
            sys.exit(1)

    if not is_apply:
        _validate_git_state(target_dir, name, is_apply=False)
        console.print("\n[bold cyan]--- Sprint Close PLAN ---[/bold cyan]")
        console.print("[dim]Governance: OK[/dim]")
        return

    _validate_git_state(target_dir, name, is_apply=True)
    _apply_closure(target_dir, name)