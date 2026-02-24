# OneCoder OSS

Local-first sprint management and governance for coding agents and humans.

## 🚀 Quick Start

OneCoder is designed to work seamlessly with the [uv](https://docs.astral.sh/uv/) package manager.

### 1. Global Installation (Recommended for Humans)
Install OneCoder globally as a tool to use it across any project repository.

```bash
uv tool install onecoder --from git+https://github.com/olanigan/onecoder
```

Once installed, you can run commands directly:
```bash
onecoder guide
onecoder sprint status
```

### 2. Local Execution (Recommended for Agents)
For development or within automated workflows, run OneCoder directly from the source without global installation.

```bash
# Run the CLI using the local environment
uv run onecoder <command>

# Example: Initialize a sprint
uv run onecoder sprint init my-feature
```

## 🛠 Core Workflows

| Action | Command |
| :--- | :--- |
| **Onboarding** | `onecoder guide` |
| **Start Sprint** | `onecoder sprint init <name>` |
| **Preflight Check** | `onecoder sprint preflight` |
| **Governed Commit** | `onecoder sprint commit -m "..." --spec-id SPEC-123` |
| **Close Sprint** | `onecoder sprint close <name>` |

## 🛡 Governance & Traceability
OneCoder enforces high-quality engineering standards through automated checks:
- **Atomic Traceability**: Every commit is linked to a Sprint-Id and Spec-Id.
- **Preflight Enforcement**: Validates task breakdowns, LOC limits, and documentation before progress.
- **Local-First**: All metadata is stored in `.sprint/` and `.issues/` within your repository.

## 🧑‍💻 Contributing
1. Clone the repo
2. Install dependencies: `uv sync`
3. Run tests: `uv run pytest`
