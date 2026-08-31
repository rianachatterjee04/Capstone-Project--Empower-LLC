# Commit gate

`pre-commit` refuses a commit that touches a guarded package unless that
package's test suite passes. `prepare-commit-msg` records a deliberate bypass
in the commit message so it is visible in history.

## Why it exists

Two commits in one session shipped with failing tests. Not because anyone
decided to ship red — because a compound shell command ran the suite and the
commit together, so nothing gated one on the other and the result scrolled past
in a tail. Remembering not to write that command is not a control. This is.

## Bypass

Deliberate and visible:

    FINTRA_GATE_BYPASS="reason" git commit -m "..."

The reason is required, printed, and written into the commit as a
`Gate-Bypassed:` trailer. `git commit --no-verify` also works, as it does in
every git repository — the goal is that a *normal* commit cannot go red by
accident, not that bypass is impossible.

## Engineering rule: verifying this gate

**A destructive git command against the active worktree is not part of
automated gate verification.**

`git reset --hard`, `git checkout -- .`, `git clean -fd` and equivalents
discard uncommitted work in the tree they run in. Verifying the gate by
committing and then hard-resetting the development worktree cost real
uncommitted work once, and the acceptance test for a safety control must not
itself threaten the thing it protects.

Verify the gate in a **disposable repository** instead — see
`packages/payroll/tests/test_commit_gate.py`, which builds a throwaway git repo
in a temporary directory, installs these hooks into it, and proves both
directions there. Nothing it does can reach a real worktree.

> **Cross-references.** Paths under `packages/api`, `packages/payroll`, `packages/sentri-api`
> and similar refer to services in the wider Fintra platform that are **not part of this
> build**. They are named so the seam is visible, not because the code ships here.
