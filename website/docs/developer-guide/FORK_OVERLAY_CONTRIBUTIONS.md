# Fork overlay contribution ledger

## Provider-admission repair — 2026-09-12

This entry records the session-repair stack, not a reconstructed inventory of every
historical contribution. Existing `contrib/*` and `candidate/contrib-v2/*` refs are
preserved. Git Machete's operator view lives in the shared `.git/machete` file.

### Frozen inputs and declared dependencies

| Role | Ref / commit |
|---|---|
| Previous upstream base | `aa05e5c0f4545eafcff7058064d6dc3f956b9c99` |
| Previous integration / rollback | `backup/main-pre-provider-admission-20260912` — `c38abf75cfbd0cb4c130eafb4772e5586a75c140` |
| Original verified repair | `backup/contrib-provider-admission-verified-20260912` — `bc484c68b2458ba584a24a921370a19d65445301` |
| Frozen new upstream | `candidate/upstream-provider-admission-20260912` — `b7b35a84b7fbe1aa2e223a6ce726a2471300d0a4` |
| Rebased integration prerequisites | `candidate/integration-base-provider-admission-20260912` — `bdca3ffe1a1545d7ba49329477caade684d41ccc` |
| Rebased repair contribution | `contrib/provider-admission-repair` — `7a4704d08870f4b9e46a15be8276102aa9a8f626` |
| Test-stability sibling | `contrib/virtual-history-test-stability` — `4f5034bcc5e304bc0fb41d5ec538887f1060feae` |
| Integration candidate | `integration/main-provider-admission-20260912` — repair, test-stability sibling, and this ledger |

The existing 30-commit integration prerequisite was replayed once onto the frozen
upstream. The repair was then replayed once as its single-commit child, followed
by one compatibility fix after composed tests exposed a removed prerequisite.
The test-stability topic is a separate single-commit child of the same integration
base, cherry-picked into the integration as `17c7a430b15c2f5dff2e4fee4801a79870fef570`.
These topics' parent is **not bare upstream**: provider admission originated in the mixed fork closure
commit `b0df576eeb`. Do not rebase this repair onto upstream alone or replay the
entire prerequisite range a second time as though it were a one-commit topic.

### Conflict disposition

- `plugins/memory/hindsight/__init__.py`: keep the fork's shared local-inference
  startup lease **and** upstream's `_may_rewrite_profile_env` guard. An unavailable
  secret scope must not erase a daemon's only key or trigger a keyless restart.
- `web/src/lib/api.ts`: preserve structured `SessionContent`, using upstream's
  current formatting. This is a type/format union, not a rollback of API fields.
- The provider-admission repair replay itself was conflict-free, but composed
  tests failed because upstream's Collective Wisdom revert removed `_FileLock`'s
  `blocking` option. Restore only that additive option on the repair contribution;
  keep the removed feature removed. Existing callers still default to blocking.
- A full TUI run exposed a flaky pre-existing unmount-measurement fixture. The
  separate test-stability topic forces the real row-ref cleanup in the same render
  as stale-height injection instead of racing deferred virtualization/layout.

### Repair contract

- One lease at physical dispatch; no nested streaming admission or blanket reentrancy.
- Physical workers retain active leases after their logical caller stops waiting.
- Async cancellation drains the acquisition worker and releases any raced acquisition.
- Registry-lock waits honor queue cancellation/deadlines; cleanup/status lock waits
  are bounded. Expire abandoned queued entries, never live active workers.
- `provider_admission.max_in_flight: 0` is the default (no local concurrency cap).
  Positive limits are operator-selected; no universal subscription capacity is claimed.
- Existing provider retry/backoff, prompt caching, and foreground silence-watchdog
  semantics remain intact. Python stays within `>=3.11,<3.14`.

### Verification and promotion

Rebased integration gates (Python 3.11.15; isolated CI-extras environment):

- Canonical Python runner: **974 passed, 0 failed, 2 Windows-only skips**, 54 owning
  and conflict-owner files, four workers, automatic file retries disabled.
- Web: typecheck, **298 tests**, lint (27 warnings baseline-classified against
  frozen upstream), and production build pass.
- TUI: Ink build, typecheck, **1,827 tests**, and lint pass. Two lint warnings in
  session lifecycle/text input remain documented rather than called warning-free.
- Changed Python modules pass Ruff; the admission module passes a 3.11 type check.
- Full repository-wide Python, Windows/macOS runtime, Docker/Nix, and live-provider
  acceptance have **not** been run. These focused gates are not a full CI seal.

The pre-rebase 850-test result is historical. Composed verification caught and
repaired both a removed lock prerequisite and a timing-dependent test fixture;
a clean textual replay was not treated as sufficient evidence.

The candidate is not installed or published by creating these refs. Promoting the
checked-out live `main`, publishing `origin/main`, and gracefully restarting old
sessions are distinct operations. Never delete live admission-registry entries or
force-kill sessions merely to make a handoff appear complete.
