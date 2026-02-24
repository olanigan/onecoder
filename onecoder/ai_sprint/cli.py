import click
from .commands import sprint, task, plan, governance, utility

@click.group()
@click.version_option(version="0.0.9")
def main():
    """ai-sprint: Standardize your development sprints."""
    pass

# Register core local-only commands
main.add_command(sprint.init)
main.add_command(sprint.status)
main.add_command(governance.preflight)
main.add_command(task.start)
main.add_command(task.finish)
main.add_command(plan.plan)
main.add_command(governance.commit)
main.add_command(governance.close)
main.add_command(utility.trace)

if __name__ == "__main__":
    main()