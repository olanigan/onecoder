"""Specification validation utilities for sprint-cli."""

import re
from pathlib import Path
from typing import List, Set


def extract_spec_ids_from_file(file_path: Path) -> Set[str]:
    """Extract all SPEC-XXX codes from a specification file.

    Args:
        file_path: Path to SPECIFICATION.md or governance.yaml

    Returns:
        Set of spec IDs found in the file
    """
    spec_ids = set()

    if not file_path.exists():
        return spec_ids

    with open(file_path) as f:
        content = f.read()
        # Match SPEC-{COMPONENT}-{SECTION}.{SUBSECTION} pattern
        # Examples: SPEC-CLI-001, SPEC-CLI-001.5, SPEC-CLI-001.5.1, SPEC-GOV-003
        # Patched: Allow OS-EXT prefix
        matches = re.findall(r"(?:SPEC|OS-EXT)-[A-Z]+-[0-9]+(?:\.[0-9]+)*", content)
        spec_ids.update(matches)

    return spec_ids


def validate_spec_ids(spec_ids: str, project_root: Path) -> tuple[bool, List[str]]:
    """Validate that spec IDs exist in SPECIFICATION.md or governance.yaml.

    Args:
        spec_ids: Comma-separated spec IDs (e.g., "SPEC-CLI-001.5.1,SPEC-GOV-003")
        project_root: Path to project root

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    if not spec_ids:
        return True, []

    # Parse spec IDs
    requested_specs = [s.strip() for s in spec_ids.split(",")]

    # Validate format
    # Patched: Allow OS-EXT prefix
    spec_pattern = re.compile(r"^(?:SPEC|OS-EXT)-[A-Z]+-[0-9]+(?:\.[0-9]+)*$")
    for spec in requested_specs:
        if not spec_pattern.match(spec):
            errors.append(
                f"Invalid spec ID format: {spec}. "
                f"Expected format: SPEC-{{COMPONENT}}-{{SECTION}}.{{SUBSECTION}}"
            )

    if errors:
        return False, errors

    # Extract all valid spec IDs from specification files
    spec_file = project_root / "SPECIFICATION.md"
    spec_yaml = project_root / "specification.yaml"  # Added YAML support
    gov_file = project_root / "governance.yaml"

    valid_specs = set()
    valid_specs.update(extract_spec_ids_from_file(spec_file))
    valid_specs.update(extract_spec_ids_from_file(spec_yaml))  # Added YAML support
    valid_specs.update(extract_spec_ids_from_file(gov_file))

    # Check if requested specs exist
    for spec in requested_specs:
        if spec not in valid_specs:
            errors.append(
                f"Spec ID not found: {spec}. "
                f"Please add it to SPECIFICATION.md or governance.yaml first."
            )

    return len(errors) == 0, errors


def get_all_spec_ids(project_root: Path) -> Set[str]:
    """Get all spec IDs defined in the project.

    Args:
        project_root: Path to project root

    Returns:
        Set of all spec IDs
    """
    spec_file = project_root / "SPECIFICATION.md"
    spec_yaml = project_root / "specification.yaml"  # Added YAML support
    gov_file = project_root / "governance.yaml"

    all_specs = set()
    all_specs.update(extract_spec_ids_from_file(spec_file))
    all_specs.update(extract_spec_ids_from_file(spec_yaml))  # Added YAML support
    all_specs.update(extract_spec_ids_from_file(gov_file))

    return all_specs
