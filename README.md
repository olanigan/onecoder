# OneCoder

Harness-agnostic governance for coding agents: a contract (`AGENTS.md`), policy (`policy.toml`), deterministic gates (`onecoder` CLI, stdlib-only) and judgment skills (`skills/`). Works under Claude Code, Codex, Pi, OpenCode or any agent that reads `AGENTS.md`.

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

Modes: `human-driver` (asks you on warnings) and `yolo` (sandbox only; the hard floor still blocks). Worktrees are optional. Design and properties: `docs/DESIGN.md`.

Policy layers (later wins): built-in defaults < repo `policy.toml` < `<project>/.onecoder/policy.toml` < `$ONECODER_POLICY`. A pip-installed copy has no bundled `policy.toml`, so it uses the built-in defaults.

`[closure]` (optional) adds task-directory rules checked by `finish`: `required_files`, `banned_files`, `min_retro_bytes` (ported from the legacy sprint PolicyEngine).

## History
v0.0.9 was a sprint-management CLI wrapper. It was retired in favour of this design (task identity = branch, gates = hooks, review = fresh-context verdict). The old code is preserved on the `legacy` branch.
