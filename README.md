# OneCoder

Harness-agnostic governance, deterministic gates, and cross-workstation tracking for coding agents: a contract (`AGENTS.md`), policy (`policy.toml`), deterministic gates (`onecoder` CLI, stdlib-only), judgment skills (`skills/`), and unified agile tracking (`track/`). Works under Claude Code, Codex, Pi, OpenCode or any agent that reads `AGENTS.md`.

```sh
uv tool install onecoder --from git+https://github.com/olanigan/onecoder   # or: bin/onecoder from a checkout
onecoder doctor                  # policy valid? which tools exist?
onecoder detect                  # recommended mode + isolation, with reasons
onecoder task new my-task        # branch onecoder/my-task (+ optional worktree)
onecoder adapt claude --write    # PreToolUse hook -> .claude/settings.local.json
onecoder adapt git --write       # pre-commit -> `onecoder preflight --staged`
onecoder finish                  # strict preflight incl. fresh-context review verdict
python3 -m unittest discover -s tests
```

---

## Tracking & Agile Governance (CLI + MCP Dual Mode)

OneCoder unifies **macro project/sprint tracking** with **micro task execution**. It operates in two synchronized modes:

1. **Local CLI Mode (Zero-Dependency)**:
   * 100% Python standard library (built-in SQLite `~/.onecoder/track.db`).
   * No cloud credentials, no external servers, and zero pip packages required.
   * Works completely offline with full sprint, issue, session, and radar capabilities.

2. **Cloudflare-Remote MCP Mode**:
   * Connects to the Cloudflare Worker Edge + D1 backend (`https://apps.lanig.workers.dev` with `TRACK_PUSH_SECRET`).
   * Exposes all 18 standard tracking tools over Model Context Protocol (MCP) stdio JSON-RPC.
   * Can be run directly via `onecoder mcp` to serve agents in Antigravity IDE, Claude Desktop, or Cursor.

### CLI Tracking Commands

```sh
# Sprint lifecycle
onecoder sprint new "Sprint 01 - ADS Runtime" -p "decision-engine"
onecoder sprint list -p "decision-engine"
onecoder sprint update <id> --status completed
onecoder sprint close <id>

# Issues & stories
onecoder issue new "Implement discrete SLM router" -p "decision-engine" -s <sprint-id> -l "core,ai"
onecoder issue list -p "decision-engine"
onecoder issue close <id>

# Projects & path registry
onecoder project register "decision-engine" --path /path/to/project --repo-url https://github.com/...
onecoder project list
onecoder project locate "decision-engine"

# Workstation radar & conflict detection
onecoder station onboard --root-dir /path/to/workspace
onecoder station list
onecoder radar
onecoder conflicts -p "decision-engine"

# Real-time work pulses & session logs
onecoder pulse "Initialized decision-engine calibration run"
onecoder session log "Calibrate Brier score" "Achieved ECE < 0.03 across test set" -p "decision-engine"
onecoder progress query -p "decision-engine"

# Start MCP stdio server
onecoder mcp                     # auto-detects local vs remote
onecoder mcp --backend local      # force local SQLite
onecoder mcp --backend remote     # force Cloudflare D1
```

All tracking commands accept `--local` or `--remote` to override the default backend.

---

## Core Governance Modes

Modes: `human-driver` (asks you on warnings) and `yolo` (sandbox only; the hard floor still blocks). Worktrees are optional. Design and properties: `docs/DESIGN.md`.

Policy layers (later wins): built-in defaults < repo `policy.toml` < `<project>/.onecoder/policy.toml` < `$ONECODER_POLICY`. A pip-installed copy has no bundled `policy.toml`, so it uses the built-in defaults.

`[closure]` (optional) adds task-directory rules checked by `finish`: `required_files`, `banned_files`, `min_retro_bytes`.

`[track]` (optional) configures tracking backend (`auto` | `local` | `remote`), endpoint, and automatic task pulses.
