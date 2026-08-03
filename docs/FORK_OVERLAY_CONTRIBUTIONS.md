# Fork Overlay Contribution Map

This is a fork-maintenance artifact. It maps the local overlay onto independently reviewable upstream candidates without rewriting the working branch.

## Snapshot

- Base: `upstream/main`
- Overlay at creation: 30 commits, zero merge commits.
- `origin/main` contains an older lineage. `git cherry main origin/main` identified 23 patch-equivalent remote-only commits. Do **not** merge or cherry-pick those copies into `main`.
- Two remote copies are non-equivalent: the original recovery bundle and an earlier Hindsight daemon implementation. Extract current behavior from this branch instead.

## 2026-08-03 frozen upstream refresh and session-recovery topics

- Fetched once and froze `upstream/main` at `cb11a7e25579638c9f67e8501dd151f581c4c942`; all topic and integration replay used that immutable SHA with no worker fetches. Rollback refs preserve the pre-refresh heads under `backup/pre-refresh-20260803-140003/*`.
- Every `contrib/*` ref now has the frozen upstream SHA as an ancestor and is zero commits behind it. The declared stack remains `contrib/tui-frame-recovery` -> `contrib/tui-approval-review` -> `contrib/tui-tool-payload-disclosure`; duplicate compatibility refs point at their refreshed canonical topic heads.
- Semantic conflict resolutions retained current upstream architecture plus the fork contracts: cron approvals remain non-interactive/fail-closed before delegated-child auto-approval; delegated children cannot wait on inherited interactive approvals; workspace-scoped npm installs preserve sibling workspace dependencies while retaining npm-engine repair; TUI focus/resize recovery keeps the renderer-owned redraw and WSL direct-echo fallback.
- Added `contrib/autonomous-session-recovery` for delegated approval, dead compression-owner recovery, and detached-turn settlement cleanup; added `contrib/tui-todo-scroll` and `contrib/tui-session-tree-interventions` for the final August 3 TUI fixes.
- Upstream already contains patch-equivalent queued-paste and collapsed-paste fixes, so those two integration commits were intentionally omitted rather than duplicated.
- Reconstructed the integration overlay from the refreshed topic ranges on top of the frozen SHA. Topic ancestry, stack ancestry, and `git diff --check` passed before integration verification.

## 2026-07-31 upstream refresh and residual-topic review

- `hermes update --yes` fetched and rebased the 38-commit integration overlay onto frozen `upstream/main` `98105f31f`; updater fork sync completed before two reviewed residual fixes were added locally. Rollback ref: `backup/pre-hermes-update-20260731-090756`.
- `git range-diff` proved all 38 replayed overlay commits patch-equivalent. Upstream's 76 new commits did not supersede overlay behavior.
- Rebased active residual roots onto `98105f31f`: `contrib/tool-executor-flush` (three commits) and `contrib/web-defensive-rendering` (scoped to structured transcript coercion). Old refs remain under `backup/contrib-pre-20260731-090756/`.
- Added the two residual integration fixes: durability gate before concurrent `tool_complete_callback` projection, and structured `SessionMessage.content` coercion before session search/rendering. The web conflict retained main's stronger `shortModelLabel(unknown)` behavior.
- Superseded topics were intentionally preserved, not replayed: update-managed-install, fork-update-rebase, WSL voice, Hindsight runtime, usage governor, kanban persistence, trace-upload compatibility, all TUI recovery/review branches, and duplicate `*-rebased` web/Hindsight refs. Kanban's generated dashboard assets remain load-bearing.
- Focused checks passed: `tests/run_agent/test_tool_call_incremental_persistence.py` (5) and `web` `npm run typecheck`; `git diff --check` passed.

## 2026-07-30 upstream refresh and fork-updater port

- Rebased the 35-commit integration overlay onto frozen `upstream/main` `11089899f`. Rollback refs: `backup/pre-hermes-update-20260730-100817` (`eedbd9d0c`) and `backup/pre-upstream-refresh-20260730-1045` (`a275dd567`); the original dirty state remains in stash `43efb799dd57a26a7a95593a41d2fc829125bcc5`.
- Upstream architecture superseded the old updater location, but not the fork behavior. `contrib/fork-update-rebase` (`f92da5535`) ports overlay replay, conflict/syntax rollback, and lease-protected origin synchronization to `hermes_cli/update_cmd.py`; after final replay it is `6b8f38762` on `main`.
- Active root topics were refreshed onto `11089899f`. The declared TUI stack remains frame recovery `92bd8ea5b` -> approval review `c14d545d3` -> payload disclosure `86a2eebe5`. `contrib/trace-upload-compat` is the zero-delta upstream tip. Old topic refs remain under `backup/contrib-pre-20260730-103811/*`.
- Focused topic checks passed: delegation 80, Hindsight 61, kanban 29, tool executor 11, usage 12, managed install 43, WSL voice 134, and fork updater 4. Web and TUI TypeScript checks passed; integrated updater/autostash/npm-install verification passed 49 tests plus Python syntax and `git diff --check`.
- Deterministic replay order: independent roots may replay in parallel; TUI frame -> approval -> payload must replay sequentially; reconcile `main` from verified topic patches, then apply integration/docs glue. Workers use a frozen full-history upstream SHA and do not fetch or shallow shared worktree metadata.
- Closure fetch advanced upstream by 20 commits to `dd4eadcf7`; all 37 overlay commits replayed cleanly. Rollback ref: `backup/pre-final-upstream-delta-20260730-111650`.

## 2026-07-27 Nous Portal dual-wire refresh

- `hermes update --yes` rebased all 34 integration-overlay commits from `846b14ab0` onto upstream merge `2b0fb72ac`; rollback ref: `backup/pre-hermes-update-20260727-171357`.
- Upstream `02d5e2308` added model-sensitive Anthropic/Chat Completions wiring for Nous Portal. Its delegation changes re-derive API mode in `_build_child_agent`; the fork's per-task provider/model routing, complexity policy, and verification contract remain additive and were not superseded.
- `git range-diff` reported all 34 fork commits patch-equivalent after replay, with no conflicts. `origin/main...main` returned `0 0` immediately after the updater's fork sync.
- Only `contrib/delegation-routing` shared upstream-changed files. It was rebased onto `2b0fb72ac` with zero non-equivalent range-diff entries and `164` focused delegation tests passing. Its prior ref remains at `backup/contrib-pre-20260727-171357/delegation-routing`; unaffected topic refs were intentionally left on their documented base.

## 2026-07-27 later upstream refresh

- `hermes update --yes` rebased the integration overlay from `d71033a40` onto `upstream/main` at `846b14ab0`; rollback ref: `backup/pre-hermes-update-20260727-163421`.
- Upstream added 12 commits in compression, model normalization, service startup, and Desktop session branching. The only shared file was `tui_gateway/server.py`, where upstream changed `session.branch` and the fork changes `_get_usage`; no topic was superseded.
- `git range-diff` reported all 33 fork commits patch-equivalent after replay, with no conflicts.
- Every active `contrib/*` branch was rebased onto `846b14ab0` with zero non-equivalent range-diff entries. The zero-delta trace topic moved with `upstream/main`; pre-refresh refs remain under `backup/contrib-pre-20260727-163421/*`.

## 2026-07-27 initial upstream rebase assessment

- Rebased the integration overlay onto `upstream/main` at `d71033a40`; rollback ref: `backup/pre-hermes-update-20260727-130910`.
- Replayed 31 fork commits. `3124ab608` was omitted from the integration branch because upstream `40dc36a84` implements the same `huggingface-hub==1.24.0` compatibility fix with stronger lockfile and invariant coverage. The original remains on the rollback ref and `backup/contrib-pre-20260727/trace-upload-compat`; `contrib/trace-upload-compat` now points at `upstream/main` to mark the topic resolved.
- `698704040` was adapted to upstream's child lifecycle helper and its new rule that missing model labels stay hidden; per-task routing and non-string model hardening remain.
- `dc92daf65` kept the embedded-startup circuit breaker; its synchronous dependency-import hunk was already supplied by upstream `ab2c9289c`.
- `a4f60ef40` now composes plugin governor status with upstream goal/focus status segments.
- `01d873ec4` intentionally keeps package discovery instead of heavyweight Hindsight imports during startup; real imports remain in the daemon path and feed the fail-fast state.
- Contribution refs were preserved before topic-branch replay under `backup/contrib-pre-20260727/*`. At that checkpoint every active `contrib/*` branch descended from `d71033a40`; the approval and payload branches retained their documented stack parents. Rebase conflicts and supersession decisions above are integration evidence, not permission to discard contributor branches.

## Topic groups

| Topic | Source commits | Scope | Upstream preparation |
|---|---|---|---|
| Update and managed-install safety | `698704040` (selected update hunks), `01d873ec4` (selected startup hunks) | `hermes_cli/main.py`, update/install tests | Rebuild as small patches; do not cherry-pick the recovery bundle. Separate managed-checkout cleanup from fork-rebase semantics. |
| Fork update rebase and rollback | `f92da5535` | `hermes_cli/update_cmd.py`, updater runtime tests | Preserve overlay replay, conflict/syntax rollback, dirty-worktree semantics, and force-with-lease synchronization together. |
| WSL/PulseAudio voice recording | `698704040` (voice hunk), `91d9610b6`, `544c04872`, `02ab36e8c`, `3e1d0067c`, `3b4204258` | recorder fallback, lifecycle, CLI voice feedback, docs/tests | Keep the fallback, cancel silence, PipeWire forwarding, and orphan-process tests together. |
| Tool executor completion reliability | `13d60bd7f`, `06e291675` | `agent/tool_executor.py` and persistence test | One focused reliability series; preserve early-flush and output-risk ordering tests. |
| Delegation routing policy | `698704040` (delegation hunk), `9af530aae` | `tools/delegate_tool.py`, delegation tests | Split model/provider overrides from complexity policy if maintainer scope demands it. Both depend on the same child credential resolution seam. |
| Hindsight embedded-runtime resilience | `dc92daf65`, `6034c6451`, `01d873ec4` (plugin/startup hunk), `3124ab608` | Hindsight provider, startup path, lazy dependency guard | Keep daemon failure diagnostics and runtime limits together; treat trace-upload dependency guard as a separately cherry-pickable compatibility fix. |
| Usage governor/status | `a4f60ef40`, `974782b46`, `5f821b8c4`, `eafd06802` | account usage, CLI/gateway/TUI status, tests | One end-to-end status-contract topic. The final lint cleanup belongs here. |
| Kanban dashboard persistence | `f12cf0965`, `dd239e1ab` | Kanban DB/plugin API and dashboard bundle test contract | Keep generated dashboard assets only if the upstream build/release policy requires checked-in assets. |
| TUI input, overlay, and repaint recovery | `61d954056`, `b115ab5d8`, `67a013d03`, `5977fa2a0`, `c14471cec` | input echo, resize/focus behavior, prompt layout | Split into input/WSL echo and overlay/repaint PRs if a reproducer does not require both. |
| Approval and tool-review UX | `42341a015`, `bf1eb8a40`, `76f4f4ea9`, `f3742a4c0`, `beb9bce62`, `d1b5ecf00` | Ink frame repair, approval transport, command review, expiry UI, per-call payload disclosure | Preserve command visibility and fail-closed expiry. The payload fold is a distinct follow-up after the approval transport/UI contract. |
| Web defensive rendering | `698704040` (web hunks) | non-string Markdown and model-label coercion | Two narrow defensive fixes; extract only after verifying current upstream still accepts these input shapes. |

## Recommended upstream order

1. WSL/PulseAudio voice recording.
2. Tool executor completion reliability.
3. Approval and tool-review UX, split into frame repair, approval transport/expiry, then payload disclosure.
4. Usage governor/status.
5. Delegation routing policy.
6. Hindsight embedded-runtime resilience.
7. Update/install safety only after a maintainer agrees on fork-update semantics.
8. Kanban and web defensive fixes after their current upstream contracts are reconfirmed.

## Materialized local branches

These refs are now rooted at `upstream/main` unless listed as a stack child. They
are local preparation branches only; no remote branch was pushed.

| Branch | Base / parent | Notes |
|---|---|---|
| `contrib/update-managed-install` | `upstream/main` | Scoped extraction from the recovery and startup commits. |
| `contrib/fork-update-rebase` | `upstream/main` | Fork overlay replay, rollback, and lease-protected origin synchronization. |
| `contrib/wsl-voice` | `upstream/main` | Scoped Pulse fallback plus dependent voice lifecycle commits. |
| `contrib/tool-executor-flush` | `upstream/main` | Completion flush and output-risk preservation. |
| `contrib/delegation-routing` | `upstream/main` | Scoped provider/model override plus policy enforcement. |
| `contrib/hindsight-runtime` | `upstream/main` | Runtime failure/limits plus scoped startup optimization. |
| `contrib/trace-upload-compat` | `upstream/main` | Resolved by upstream `40dc36a84`; current ref has zero fork commits. Original preserved at `backup/contrib-pre-20260727/trace-upload-compat`. |
| `contrib/usage-governor` | `upstream/main` | End-to-end usage status contract and lint cleanup. |
| `contrib/kanban-persistence` | `upstream/main` | Kanban persistence and test-contract adjustment. |
| `contrib/tui-input-recovery` | `upstream/main` | Input, overlay, resize, focus, and WSL echo behavior. A governor-poll hunk was intentionally excluded because it belongs to `contrib/usage-governor`. |
| `contrib/autonomous-session-recovery` | `upstream/main` | Delegated-child approval recovery, dead compression-owner recovery, and detached-turn settlement cleanup. |
| `contrib/tui-todo-scroll` | `upstream/main` | Keep active turn todos mounted while transcript history scrolls. |
| `contrib/tui-session-tree-interventions` | `upstream/main` | Session-tree lineage plus safe steering and interruption controls. |
| `contrib/tui-frame-recovery` | `upstream/main` | Ink frame invalidation and physical approval ghost repair. |
| `contrib/tui-approval-review` | `contrib/tui-frame-recovery` | Approval transport, expiry, and bounded repaint. |
| `contrib/tui-tool-payload-disclosure` | `contrib/tui-approval-review` | Per-call verbose payload disclosure. |
| `contrib/web-defensive-rendering` | `upstream/main` | Scoped non-string rendering and model-label hardening. |

## Extraction protocol

For each topic, start from a clean worktree at current `upstream/main`; do not branch from this fork overlay.

1. Create `contrib/<topic>` from `upstream/main`.
2. For commits that are already self-contained, cherry-pick with `-x` and run their focused tests.
3. For `698704040` or `01d873ec4`, apply only the documented path/hunk subset, then write a focused commit with the reproduced symptom and test evidence.
4. Re-check against current upstream intent before proposing a PR; no topic inherits fork-only update behavior merely because it works locally.
5. Keep the fork overlay unchanged until the extracted branch is independently green.

## Non-goals

- Do not merge the stale `origin/main` lineage into this branch.
- Do not squash the recovery bundle in place.
- Do not publish a topic branch until its behavior has been reproduced against then-current upstream.
