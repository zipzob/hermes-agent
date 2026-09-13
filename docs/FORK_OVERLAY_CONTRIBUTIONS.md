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

## Goal continuity and interactive UI repairs — 2026-09-12

Each repair remains on a focused topic branch. Commit bodies carry the local
problem/root-cause/fix/verification record; this ledger provides the cross-topic
map. `.git/machete` records stack topology only and is not the rationale store.

### Per-run goal-budget continuation

- **Branch / commit:** `fix/goal-budget-continuation-20260912` —
  `750f519f46c02cfc22ada06bcbe97b23b02c33b9`.
- **Symptom:** hitting `agent.max_turns` looked like a voluntary final response and
  `/goal` remained idle until another user message arrived.
- **Root cause:** per-run iteration exhaustion was finalized as ordinary output;
  post-turn goal logic could therefore judge it as a completed turn rather than an
  incomplete lifecycle outcome.
- **Contract:** propagate bounded budget-exhaustion metadata; give failure and
  interruption precedence; continue directly without judging or spending a goal
  turn; drain queued user input first; never forward transcript or credential data.
- **Verification:** 38 focused lifecycle tests and 138 related goal tests passed;
  the exact integrated candidate passed the canonical repository runner with
  retries disabled. The accompanying TUI compaction-status change passed 111 tests,
  typecheck, and build.

### Desktop topmost Escape ownership

- **Branch / commits:** `contrib/desktop-input-layer-ownership` —
  `c7d79d060a9f664ad9ca3a15851f2ca9f7b9347b` and
  `a2bdaac163f62c717ad46cac8e22a37a2aca373d`.
- **Symptom:** Escape in a foreground subgoal/dialog could deny a background
  approval.
- **Root cause:** approval used a capture-phase window listener and had no shared
  notion of which mounted interaction layer owned Escape.
- **Contract:** mounted modal content outranks approval; shared Dialog, Sheet,
  session picker, and command palette register ownership for their mounted portal
  lifetime; topmost approval still maps Escape to deny.
- **Mode scope:** this is a Desktop-renderer repair. Gateway/API/web transports do
  not share this local keyboard listener, and classic CLI serializes its prompt.
  The independently identified TUI equivalent is handled by the next contribution.
- **Verification:** focused modal/approval regressions, changed-file ESLint, Desktop
  typecheck and build passed; the full Desktop UI suite passed 7,584 tests across
  798 files; independent exact-byte reviews reported no blockers.

### TUI topmost input ownership

- **Topic / integrated commit:** `contrib/tui-input-layer-ownership` —
  `c1a0c70272116dff97a25790a17394de88e9ab15` (fast-forwarded unchanged).
- **Symptom:** a modal widget and approval could coexist while background approval,
  voice, double-Escape, or composer handlers consumed foreground keys.
- **Root cause:** overlay state had no single input owner and global shortcuts ran
  before widget dispatch.
- **Contract:** a foreground modal widget owns every key before voice/composer/prompt
  logic; prompt handlers unmount while hidden; pending approval state is preserved
  and regains ownership after the widget closes.
- **Verification:** focused ownership tests passed 43 tests; full TUI passed 1,829
  tests across 175 files; ESLint, typecheck, build, diff check, and independent
  exact-byte review passed.

### TUI live-tail shrink repaint

- **Topic / integrated commit:** `contrib/tui-live-tail-repaint` —
  `6daee75ae5bcc213325bd4b55e3eabe038906478`; integrated as
  `0a5df5e4825552aa3b02e3718c60fa0c926eb635`.
- **Symptom:** shorter live thinking text could leave a physical suffix such as
  `sion`, shift rows by a cell, or appear to overwrite the composer until refresh.
- **Root cause:** the frame boundary detected structural changes but treated
  non-empty same-line thinking values as equivalent, leaving Ink unable to repair
  cells after display-width contraction.
- **Contract:** compare newline-delimited display widths (including wide Unicode),
  invalidate exactly once on shrink, never repaint for ordinary token growth, and
  preserve structural-transition and unmount recovery.
- **Verification:** three focused repaint tests, including exact-delta and CJK
  coverage, passed; full TUI passed 1,828 tests across 175 files; ESLint, typecheck,
  build, diff check, and independent exact-byte review passed.

### TUI empty-thinking activity

- **Topic / integrated commit:** `contrib/tui-thinking-activity` —
  `f0cdd6e5de0de230f339c56efd121768f7b5407c`; integrated as
  `7c5b8f72be780c0cfc41ca991817a64a56d4d69f`.
- **Symptom:** active thinking displayed an empty dangling tree branch before the
  provider emitted its first reasoning text.
- **Root cause:** the empty-preview branch used a stream cursor that is blank before
  reasoning streaming starts.
- **Contract:** render the existing single-display-cell Braille spinner only while
  active and empty; keep inactive empty state absent; preserve the tree lead and
  non-empty reasoning rendering; clean up the spinner timer on unmount.
- **Verification:** three focused activity tests passed; full TUI passed 1,830 tests
  across 176 files; all configured spinner frames were audited as one-code-point
  Braille glyphs; ESLint, typecheck, build, diff check, and independent review passed.

### TUI primary status ordering

- **Topic / integrated commit:** `contrib/tui-status-order` —
  `090c6066389482c68fefed15d200525da3816a2a`; integrated as
  `4dcfd0d8caa8eee08fc404afef9c69493de1dc21`.
- **Symptom:** the multi-agent count appeared first and displaced the standard
  Hermes status/activity indicator.
- **Root cause:** secondary subagent and battery segments rendered before the
  primary idle status or busy `FaceTicker`.
- **Contract:** Hermes state is first; subagent and battery indicators follow;
  narrow-width priorities, stalled warnings, separators, and model/context
  essentials remain intact.
- **Verification:** 35 focused status tests and the full 1,829-test TUI suite passed;
  ESLint, typecheck, build, diff check, and independent exact-byte review passed.

## Resource-aware delegation and lifecycle resilience — 2026-09-13

These are separate contributions because model selection, stale-child detection,
and iteration-summary safety have different owners and rollback boundaries.

### Delegation workload and context routing

- **Topic / integrated commit:** `contrib/delegation-resource-routing` —
  `aa872403c1`; integrated as `57e94fd57c`.
- **Symptom:** delegated children used one configured model regardless of task
  capability, child working-set size, or independent subscription-pool pressure.
- **Contract:** classify each child as simple, volume, substantive,
  latency-critical, or judgment; use Luna/Terra/Sol respectively; select a 900k
  alias only for that child's large dossier; preserve explicit pins; never
  automatically select preview Spark or scarce Astra; retain bounded provenance.
- **Verification:** 29 focused routing/live-log tests, Ruff, and diff checks passed.

### Semantic delegated-child staleness

- **Topic / integrated commit:** `contrib/delegation-semantic-stale-detection` —
  `1cacd75296`; integrated as `5dbb2c6bb3`.
- **Symptom:** a live PID or transport heartbeat could hide a child that made no
  semantic progress until the hard timeout.
- **Contract:** track semantic model/tool progress separately from process and
  transport liveness, and classify bounded no-progress children as stalled without
  treating ordinary long-running physical work as dead.
- **Verification:** 57 focused tests passed with one platform skip; earlier owning
  coverage passed 143 tests with one skip.

### Iteration-limit summary capacity guard

- **Topic / integrated commit:** `contrib/iteration-summary-context-fallback` —
  `ba66db5e02`; integrated as `cf9ded7e09`.
- **Symptom:** a resumed, very large session could reach `agent.max_turns`, then
  fail the final summary request because the replay itself exceeded model context.
- **Contract:** estimate the wire request with output/safety reserve; skip an
  unsafe provider request and emit a bounded deterministic handoff; preserve
  unrelated provider errors rather than misclassifying them as context overflow.
- **Verification:** 286 owning tests passed with the Anthropic test extra enabled;
  Ruff and diff checks passed.
