# onecoder: operating contract

You are running under **OneCoder**. This file is the always-loaded contract. It is harness-agnostic: it applies the same under Claude Code, Codex, Pi, OpenCode or any agent that reads `AGENTS.md`.

## Start of every session
1. `onecoder detect` (or `<mount>/bin/onecoder detect` when not installed). Report the recommended mode and isolation to the human in one line.
2. Work on a task: `onecoder task new <id>` (uses the recommendation; `--mode` / `--isolation` override). Then fill in `brief.md` acceptance criteria **before** editing code.
3. Task identity is the branch `onecoder/<id>`. Never infer it from a diff.

## Modes
| Mode | Who decides | Gate `warn` | Gate `block` |
|---|---|---|---|
| `human-driver` | the human approves risky steps | **ask the human** | denied |
| `yolo` | you run unattended | allowed, logged | **denied** |

`yolo` is only valid in a sandbox (CI, container, cloud session) or when policy sets `modes.allow_yolo_on_host`. The hard floor (`block`) is identical in both modes: secrets in writes, protected paths, force-push, pushing the default branch, `--no-verify`, `curl | sh`, `rm -rf /`, `gh pr merge`.

## Isolation is optional
`none` (the current branch is already the isolation), `branch`, or `worktree`. Use whatever `onecoder detect` recommends unless the human says otherwise. Do not create worktrees you do not need.

## Rules
- **You never merge and never push the default branch.** The human merges.
- **Fail visible.** If a gate, scanner or reviewer cannot run, say so. A missing check is reported as `skipped`/`fail`, never as `pass`.
- **Escalate (human-driver):** destructive git, dependency changes, anything the gate asks about, any acceptance criterion you cannot satisfy.
- **Do not edit** `.onecoder/policy.toml`, `.env`, `*.pem`, or `.git/`. The gate will refuse; do not work around it.
- Deterministic checks (size, secrets, paths) are scripts. Models are used only where judgment is needed: `spec-review` and `supply-chain-triage` skills.

## Finishing a task
1. Commit your work on the task branch.
2. Get a verdict from a **fresh-context** reviewer: skill `spec-review` (writes `.onecoder/tasks/<id>/review.json` pinned to the current HEAD).
3. `onecoder finish` (preflight with warnings treated as failures). Fix, re-commit, re-review if it fails; a changed HEAD makes the old verdict stale.
4. Hand off. Do not push the default branch, do not merge.
