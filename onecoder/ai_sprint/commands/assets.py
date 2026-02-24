import click
import os
from .. import state
from . import common


@click.command(name="generate-assets")
@click.option("--sprint-id", help="Target sprint ID (defaults to valid local sprint).")
@click.option(
    "--dry-run", is_flag=True, help="Generate prompts only, do not call Image API."
)
@click.pass_context
def generate_assets(ctx, sprint_id, dry_run):
    """Generate visual assets for sprint closure."""
    project_root = common.PROJECT_ROOT

    # Resolve Sprint ID
    if not sprint_id:
        sprint_id = common.auto_detect_sprint_id()
        if not sprint_id:
            click.secho(
                "No active sprint found. Pass --sprint-id explicitly.", fg="red"
            )
            ctx.exit(1)

    sprint_dir = project_root / ".sprint" / sprint_id
    if not sprint_dir.exists():
        click.secho(f"Sprint directory not found: {sprint_dir}", fg="red")
        ctx.exit(1)

    media_dir = sprint_dir / "media"
    media_dir.mkdir(exist_ok=True)

    click.echo(f"🎨 Generating assets for sprint: {sprint_id}")

    # 1. Detect Changes (Mock for now, simply reading README/TODO)
    # Ideally this would use `git diff` against the sprint start commit.
    sprint_readme = sprint_dir / "README.md"
    (
        sprint_readme.read_text() if sprint_readme.exists() else "No README content."
    )

    # 2. Generate Prompts via LLM (Mock/Placeholder logic for V1)
    # In a real implementation this would call `dspy` with proper context.
    # We will use the `VisualGenerator` logic if available, or fallback to heuristics.

    prompts = {
        "whiteboard": f"Hand-drawn whiteboard diagram of: {sprint_id}. High contrast, marker style.",
        "flowchart": f"Professional flowchart for: {sprint_id}. Clean lines, modern tech aesthetic.",
        "concept": f"Futuristic cyberpunk concept art representing: {sprint_id}.",
    }

    prompt_file = media_dir / "visual_generation_prompts.md"

    prompt_content = "# Visual Generation Prompts\n\n"
    for style, prompt in prompts.items():
        prompt_content += f"## {style.title()}\n`{prompt}`\n\n"

    prompt_file.write_text(prompt_content)
    click.secho(f"✅ Generated prompts: {prompt_file}", fg="green")

    if dry_run:
        return

    # 3. Call Image Generation (if API Key present)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        click.secho(
            "⚠️ GEMINI_API_KEY not found. Skipping image generation.", fg="yellow"
        )
        return

    click.echo("🚀 Triggering Image Generation...", nl=True)
    # TODO: Connect to OneCoder's native generation tool or external API.
    # For MVW, we prioritize the prompt generation.
    click.secho(
        "Image generation is currently being integrated. Please use the Antigravity `generate_image` tool with the prompts above!",
        fg="blue",
    )
