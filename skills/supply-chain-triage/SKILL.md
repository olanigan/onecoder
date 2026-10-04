---
name: supply-chain-triage
description: Judge only the fuzzy parts of a dependency change (CVE reachability, license fit) after deterministic tools have produced the facts. Use when `onecoder preflight` reports changed dependency manifests.
---

# supply-chain-triage

Division of labor. **Never** use a model for the deterministic parts:

| Step | Who | How |
|---|---|---|
| Detect manifest change | script | `onecoder preflight` (`supply-chain` check) |
| SBOM, hashes, CVE lookup | existing tools | your scanner via `supply_chain.scanner_cmd` (e.g. osv-scanner, syft, trivy) |
| "Is this CVE reachable from our call sites?" | you | read the code that imports/calls the vulnerable symbol |
| "Is this license compatible with the project?" | you | read the license text against the project's stated policy |

## Output (typed; one entry per finding)
```json
{"component": "pkg@1.2.3", "kind": "cve|license", "id": "CVE-... | SPDX-id",
 "verdict": "reachable|not_reachable|compatible|incompatible|needs_review",
 "evidence": "path:line or license clause"}
```
- Unknown or unreadable input → `needs_review`. Never guess a license from a package name.
- If no scanner is configured, say so plainly; do not invent advisories or an SBOM. Ask the human to set `supply_chain.scanner_cmd`.
- `reachable`, `incompatible`, or any unresolved `needs_review` → escalate to the human; do not proceed in yolo.
