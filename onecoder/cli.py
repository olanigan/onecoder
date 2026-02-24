import click
import sys
import logging
import importlib.metadata
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path.cwd() / ".env"
load_dotenv(env_path)

from .commands.guide import guide
from .commands.doctor import doctor
from .commands.issue import issue

from .logger import configure_logging

logger = logging.getLogger(__name__)

def get_version():
    return "0.0.9"

@click.group()
@click.version_option(version=get_version(), prog_name="onecoder")
@click.option("--verbose", is_flag=True, help="Enable verbose logging.")
def cli(verbose):
    """OneCoder: Local-first sprint management for coding agents."""
    configure_logging(verbose=verbose)

def main():
    """Main entry point."""
    try:
        cli()
    except Exception as e:
        if isinstance(
            e,
            (
                click.exceptions.Exit,
                click.exceptions.Abort,
                click.exceptions.ClickException,
            ),
        ):
            raise e
        raise e

# --- Core commands ---
cli.add_command(guide)
cli.add_command(doctor)
cli.add_command(issue)

# --- Sprint group ---
try:
    from .ai_sprint.cli import main as sprint_main
    cli.add_command(sprint_main, name="sprint")
except ImportError:
    @cli.group(name="sprint")
    def sprint_group():
        """Sprint management commands."""
        pass
    cli.add_command(sprint_group)

if __name__ == "__main__":
    cli()