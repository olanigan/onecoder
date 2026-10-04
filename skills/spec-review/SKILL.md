---
name: spec-review
description: Fresh-context adversarial review of an onecoder task branch against its acceptance criteria. Use after committing task work and before `onecoder finish`. Writes a typed verdict file pinned to the current HEAD. Never edits code.
---

# spec-review

You are the **reviewer**, not the author. If you wrote this code in the current context, stop: a fresh context (new session or subagent) must do this. Self-review is not a verdict.

## Procedure
1. `onecoder task current` → task id. Read `.onecoder/tasks/<id>/brief.md`.
2. Read the change: `git diff $(git merge-base HEAD <base>)...HEAD` and the files it touches. Read the code, not the commit messages.
3. For **each** `AC-n` line, decide `satisfied`, `not_satisfied`, or `not_applicable`.
   - `satisfied` needs evidence: `path:line` or a command output that proves it.
   - `not_applicable` needs the reason in `evidence`.
   - **No evidence means `not_satisfied`.** Default to skepticism; try to falsify each criterion.
4. Run the checks that exist (tests, linters). Quote real output; never claim a run you did not do.
5. Write `.onecoder/tasks/<id>/review.json`:
```json
{
  "task": "<id>",
  "head_sha": "<output of git rev-parse HEAD>",
  "fresh_context": true,
  "reviewer": "<harness/model or human>",
  "criteria": [
    {"id": "AC-1", "verdict": "satisfied", "evidence": "lib/x.py:42 and `python -m unittest` passed"}
  ]
}
```
6. Do **not** modify code or the brief. Report findings to the author; they fix, recommit, and request a new review (a new HEAD invalidates this verdict).

`onecoder finish` rejects a verdict that is missing, malformed, stale, from a non-fresh context, or that omits any criterion.
