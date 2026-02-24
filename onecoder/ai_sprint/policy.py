import yaml
from pathlib import Path
from typing import List, Dict, Any


class PolicyEngine:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.policy = self._load_policy()

    def _load_policy(self) -> Dict[str, Any]:
        """Load governance.yaml from project root."""
        policy_path = self.project_root / "governance.yaml"
        if not policy_path.exists():
            return {}
        try:
            with open(policy_path, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def get_closure_policy(self) -> Dict[str, Any]:
        return self.policy.get("policies", {}).get("closure_policy", {})

    def get_visual_policy(self) -> Dict[str, Any]:
        return self.policy.get("policies", {}).get("visual_documentation", {})

    def get_verification_rules(self) -> Dict[str, Any]:
        """Get component verification rules from closure policy."""
        return self.get_closure_policy().get("verification_rules", {})

    def evaluate_closure(self, sprint_dir: Path) -> List[str]:
        """Evaluate closure rules against a specific sprint."""
        violations = []
        rules = self.get_closure_policy()

        if not rules:
            return violations  # No rules, no violations

        # Rule 1: Required Files
        for filename in rules.get("required_sprint_files", []):
            if not (sprint_dir / filename).exists():
                violations.append(f"Missing required artifact: {filename}")

        # Rule 2: Allowed Files (Banned patterns)
        # Check recursively in sprint dir
        banned = rules.get("banned_files", [])
        if banned:
            for item in sprint_dir.rglob("*"):
                if item.name in banned:
                    violations.append(f"Found banned file: {item.name}")

        # Rule 3: Retro Length
        min_len = rules.get("min_retro_length", 0)
        retro = sprint_dir / "RETRO.md"
        if min_len > 0 and retro.exists():
            if retro.stat().st_size < min_len:
                violations.append(
                    f"RETRO.md is too short (< {min_len} bytes). Please add detail."
                )

        # Rule 4: Visual Documentation (SPEC-GOV-004)
        visual_policy = self.get_visual_policy()
        if visual_policy.get("auto_generate_on_close"):
            media_dir = sprint_dir / "media"
            if not media_dir.exists():
                violations.append(
                    "Missing required 'media/' directory for visual documentation."
                )
            else:
                # Check for standard asset types
                # Map from policy names to expected filenames
                expected_assets = {
                    "flowcharts": "flowchart.png",
                    "architecture_diagrams": "architecture.png",
                    "summary_visuals": "summary.png",
                }
                for asset_type in visual_policy.get("asset_types", []):
                    filename = expected_assets.get(asset_type)
                    if filename:
                        file_path = media_dir / filename
                        if not file_path.exists():
                            msg = f"Missing required visual asset: {filename} ({asset_type})"
                            if (media_dir / "visual_generation_prompts.md").exists():
                                msg += " (Prompts available in 'media/visual_generation_prompts.md')"
                            violations.append(msg)
                        elif file_path.stat().st_size < 100:
                            violations.append(
                                f"Visual asset {filename} appears to be a placeholder (size < 100 bytes)."
                            )

        # Rule 5: Zero Debt (SPEC-GOV-012)
        if rules.get("require_zero_debt"):
            # We check if a 'debt_status' exists in the sprint state or run a quick check
            # For now, evaluate_closure reports that verification is required
            # The actual execution happens in the CLI
            verification_file = sprint_dir / ".verification_results.json"
            if not verification_file.exists():
                violations.append(
                    "Zero-Debt verification has not been run. Run 'sprint verify' first."
                )
            else:
                try:
                    import json

                    with open(verification_file, "r") as f:
                        results = json.load(f)
                    if (
                        results.get("errors", 0) > 0
                        or results.get("lint_violations", 0) > 0
                    ):
                        violations.append(
                            f"Zero-Debt violation: {results.get('errors')} errors, {results.get('lint_violations')} lint issues."
                        )
                except Exception:
                    violations.append("Could not parse verification results.")

        return violations
