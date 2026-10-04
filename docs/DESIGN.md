# onecoder design

```
                        ┌──────────── AGENTS.md (contract, any harness) ────────────┐
 human ── decisions ──► │ mode: human-driver | yolo      isolation: none|branch|wt  │
                        └───────────────┬───────────────────────────┬───────────────┘
                                        │ hooks / git               │ skills (judgment only)
                  ┌─────────────────────▼──────────┐   ┌────────────▼───────────────┐
                  │ onecoder hook / preflight (code) │   │ spec-review (fresh context)│
                  │ secrets · paths · cmds · size  │   │ supply-chain-triage        │
                  │ review.json validity (HEAD pin)│   └────────────────────────────┘
                  └─────────────────────┬──────────┘
          adapters: claude PreToolUse │ git pre-commit │ (others: call `onecoder hook`)
```

## Environment → recommendation
```
 sandbox? attended?   mode
 ─────────────────────────────────────────────
 yes      no          yolo           (CI, unattended cloud)
 yes      yes         human-driver   (cloud session you are watching)
 no       any         human-driver   (laptop; yolo needs allow_yolo_on_host)

 isolation (when `auto`), first match wins:
   not a repo ................................ none
   already in a linked worktree .............. none
   other onecoder tasks active .................. worktree
   dirty tree ................................ worktree
   on default branch .......................... branch
   clean feature branch ....................... none  (branch already isolates)
```

## Properties (each is a regression test)
- **Fail closed:** invalid policy or any gate exception => `deny`, never allow.
- **Hard floor is mode-independent:** yolo never lowers `block`.
- **Verdicts are pinned:** `review.json` carries `head_sha`; a new commit makes it stale.
- **Nothing is fabricated:** no scanner => `warn`/`fail`/`skipped`, not `pass`; no invented SBOM data.
- **Task identity is structural:** branch `onecoder/<id>`; no diff-to-task inference.
- **State outlives worktrees:** `.onecoder/` lives in the main worktree (found via `--git-common-dir`) and is excluded via `info/exclude`.

## Not yet verified
- Claude Code's `PreToolUse` `permissionDecision` honored under `--dangerously-skip-permissions`: believed yes, **verify in a live session**.
- Adapters for Codex / Pi / OpenCode / Cursor: only the git adapter and `onecoder hook` stdin protocol are generic; harness-specific wiring is not written.
- `spec-review` quality is unmeasured (falsification test: story-1)
