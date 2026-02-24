import os
from pathlib import Path
from .commands.common import console

try:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


def is_google_ide() -> bool:
    """Check if running in a Google IDE (Antigravity or Gemini CLI) with native image generation."""
    # Check for Antigravity or Gemini CLI environment indicators
    # These IDEs have native generate_image tool available
    indicators = [
        "GEMINI_CLI",
        "ANTIGRAVITY",
        "ANTIGRAVITY_AGENT",
        "ANTIGRAVITY_CLI_ALIAS",
    ]
    return any(os.getenv(i) == "true" or os.getenv(i) == "1" for i in indicators)


def generate_visual_assets(sprint_dir: Path, sprint_name: str) -> None:
    """Generate flowcharts, architecture diagrams, and summary visuals.

    Uses native image generation in Google IDEs (Antigravity, Gemini CLI),
    or falls back to Gemini API if GEMINI_API_KEY is set.
    If both fail or are unavailable, generates a PROMPTS file for the agent/user to fulfill.
    """
    media_dir = sprint_dir / "media"
    media_dir.mkdir(exist_ok=True)

    try:
        _generate_native_or_api(sprint_dir, sprint_name, media_dir)
    except Exception as e:
        console.print(f"[yellow]Visual generation note:[/yellow] {e}")
        # Note: We do NOT generate placeholders anymore.
        # The user/agent must fulfill the prompts in visual_generation_prompts.md


def _generate_native_or_api(
    sprint_dir: Path, sprint_name: str, media_dir: Path
) -> None:
    # Read sprint context
    readme = sprint_dir / "README.md"
    todo = sprint_dir / "TODO.md"

    goal = ""
    if readme.exists():
        with open(readme) as f:
            goal = f.read()

    tasks = ""
    if todo.exists():
        with open(todo) as f:
            tasks = f.read()

    # Check for existing assets
    expected_assets = ["flowchart.png", "architecture.png", "summary.png"]
    missing_assets = [a for a in expected_assets if not (media_dir / a).exists()]

    if not missing_assets:
        # All assets exist, nothing to do
        return

    # Generate the prompts file if it doesn't exist
    prompt_file = media_dir / "visual_generation_prompts.md"
    if not prompt_file.exists():
        with open(prompt_file, "w") as f:
            f.write(f"""# Visual Asset Generation Prompts for Sprint {sprint_name}

## Flowchart (flowchart.png)
Create a hand-drawn whiteboard flowchart showing the sprint workflow and task dependencies.

Sprint: {sprint_name}
Goal: {goal}
Tasks: {tasks}

Style: Whiteboard style, clean black marker on white board, technical annotations.

## Architecture Diagram (architecture.png)
Create a hand-drawn whiteboard architecture diagram showing the components and relationships.

Sprint: {sprint_name}
Context: {goal}

Style: Whiteboard architecture style, technical boxes and arrows, professional sketch on white board.

## Summary Visual (summary.png)
Create a hand-drawn whiteboard summary of this sprint accomplishments and learnings.

Sprint: {sprint_name}
Goal: {goal}

Style: Whiteboard summary style, visually clear, engineer's handwriting.

---
Note: In Google IDEs (Antigravity, Gemini CLI), use the native generate_image tool with these prompts.
Save images to: {media_dir.absolute()}
""")

    # Check if we're in a Google IDE with native image generation
    if is_google_ide():
        # In Antigravity/Gemini CLI, the agent SHOULD use native generate_image tool manually/agentically
        # We assume the agent will see the prompts file or the error message and act on it.
        # We raise specific error to guide the agent.
        raise RuntimeError(
            f"Visual generation prompts saved to {prompt_file}. "
            "In Google IDEs, the agent should use native generate_image tool using these prompts."
        )

    # Check for API key for non-Google IDEs
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set and not running in Google IDE. "
            f"Please fulfill the prompts in {prompt_file} manually or with an agent."
        )

    if not GEMINI_AVAILABLE:
        raise RuntimeError(
            "google-genai package not installed. Run: pip install google-genai"
        )

    # Use Gemini API for visual generation
    client = genai.Client(api_key=api_key)

    # Only generate what's missing
    if "flowchart.png" in missing_assets:
        flowchart_prompt = f"""Create a clean, professional flowchart diagram showing the sprint workflow and task dependencies.

Sprint: {sprint_name}
Goal: {goal}
Tasks: {tasks}

Style: Minimal, clear, with arrows showing task flow and dependencies. Use a light background."""

        console.print("[cyan]Generating flowchart...[/cyan]")
        generate_image(client, flowchart_prompt, media_dir / "flowchart.png")

    if "architecture.png" in missing_assets:
        arch_prompt = f"""Create a system architecture diagram showing the components and relationships for this sprint.

Sprint: {sprint_name}
Context: {goal}

Style: Clean boxes and arrows, professional, technical diagram style."""

        console.print("[cyan]Generating architecture diagram...[/cyan]")
        generate_image(client, arch_prompt, media_dir / "architecture.png")

    if "summary.png" in missing_assets:
        summary_prompt = f"""Create a visual summary of this sprint showing key metrics, accomplishments, and learnings.

Sprint: {sprint_name}
Goal: {goal}

Style: Infographic style, visually appealing, easy to scan."""

        console.print("[cyan]Generating summary visual...[/cyan]")
        generate_image(client, summary_prompt, media_dir / "summary.png")


def generate_image(
    client, prompt: str, output_path: Path, model: str = "gemini-2.5-flash-image"
) -> None:
    """Generate a single image using Gemini."""
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_generation_config=types.ImageGenerationConfig(aspect_ratio="16:9"),
        ),
    )

    # Save the generated image
    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data"):
                with open(output_path, "wb") as f:
                    f.write(part.inline_data.data)
                break
