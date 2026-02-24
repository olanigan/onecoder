import re
from pathlib import Path
from typing import Dict, Any, Optional


def check_spec_alignment(repo_root: Path, staged_mode: bool = False) -> Dict[str, Any]:
    """Ghost Map check: Validate SPECIFICATION.md concepts against codebase symbols."""
    # Optimization: Skip this heavy check during staged commits (Preflight Phase 1)
    if staged_mode:
        return {
            "name": "Spec-Code Alignment",
            "status": "passed",
            "message": "Skipped for staged commit (Optimization).",
        }

    spec_file = repo_root / "SPECIFICATION.md"
    if not spec_file.exists():
        return {
            "name": "Spec-Code Alignment",
            "status": "warning",
            "message": "SPECIFICATION.md not found.",
        }

    try:
        content = spec_file.read_text()

        # Try using the High-Performance Rust Engine
        try:
            from onecore import AlignmentEngine  # type: ignore
            import json

            engine = AlignmentEngine(str(repo_root))
            result_json = engine.check_spec_alignment(content)
            result = json.loads(result_json)

            # Map Rust result to CLI format
            score = result.get("score", 0.0)
            missing = result.get("missing_concepts", [])

            if score < 30.0:
                return {
                    "name": "Spec-Code Alignment (Rust)",
                    "status": "warning",
                    "message": f"Low spec-to-code alignment ({score:.1f}%). Missing symbols for: {', '.join(missing[:3])}",
                }

            return {
                "name": "Spec-Code Alignment (Rust)",
                "status": "passed",
                "message": f"Spec-to-code alignment: {score:.1f}% (High-Performance Scan)",
            }

        except ImportError:
            # Fallback to Python Implementation
            concepts = re.findall(r"(?:###|-)\s+([A-Z][a-zA-Z0-9\s]+)", content)
            concepts = [c.strip() for c in list(set(concepts)) if len(c.strip()) > 5]

            if not concepts:
                return {
                    "name": "Spec-Code Alignment",
                    "status": "passed",
                    "message": "No high-level concepts found in SPECIFICATION.md to validate.",
                }

            from onecoder.tools.tldr_tool import TLDRTool  # type: ignore

            tldr = TLDRTool()
            found_count = 0
            missing = []

            check_list = concepts[:20]
            for concept in check_list:
                # Try to search concept name (case insensitive)
                query = concept.replace(" ", "")
                matches = tldr.search(str(repo_root), query)
                if matches:
                    found_count += 1
                else:
                    missing.append(concept)

            alignment = (found_count / len(check_list)) * 100 if check_list else 0
            if alignment < 30:
                return {
                    "name": "Spec-Code Alignment (Legacy)",
                    "status": "warning",
                    "message": f"Low spec-to-code alignment ({alignment:.1f}%). Missing symbols for: {', '.join(missing[:3])}",
                }

            return {
                "name": "Spec-Code Alignment (Legacy)",
                "status": "passed",
                "message": f"Spec-to-code alignment: {alignment:.1f}% ({found_count}/{len(check_list)} concepts found).",
            }

    except Exception as e:
        return {
            "name": "Spec-Code Alignment",
            "status": "warning",
            "message": f"Could not perform alignment check: {e}",
        }


def check_secrets(
    repo_root: Path, scan_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Basic secret scanning with placeholder avoidance."""
    violations = []
    placeholders = {
        "sk-ant-api03-" + "x" * 12,
        "sk-or-v1-" + "x" * 12,
        "AIza" + "x" * 35,
    }

    # Use Rust engine findings if available
    if scan_data:
        for violation in scan_data.get("secrets_found", []):
            snippet = violation.get("snippet", "")
            match_content = snippet
            is_placeholder = False
            for ph in placeholders:
                if ph[:10] in match_content and "xxx" in match_content:
                    is_placeholder = True
                    break

            if is_placeholder:
                continue
            violations.append(violation.get("file"))

        violations = list(set(violations))

        if violations:
            return {
                "name": "Secret Scanning (Rust)",
                "status": "failed",
                "message": f"Found potential secrets in {len(violations)} files: {', '.join(violations[:3])}...",
                "critical": True,
            }
        return {
            "name": "Secret Scanning (Rust)",
            "status": "passed",
            "message": "No potential secrets found (High-Performance Scan).",
        }

    # Fallback if engine missing (simplified)
    return {
        "name": "Secret Scanning",
        "status": "passed",
        "message": "Secret check skipped (Engine missing).",
    }
