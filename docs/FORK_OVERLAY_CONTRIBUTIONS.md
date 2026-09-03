# Fork Overlay Contribution Map

This is a fork-maintenance artifact. It maps the local overlay onto independently reviewable upstream candidates without rewriting the working branch.

## Snapshot

- Base: `upstream/main`
- Overlay at creation: 30 commits, zero merge commits.
- `origin/main` contains an older lineage. `git cherry main origin/main` identified 23 patch-equivalent remote-only commits. Do **not** merge or cherry-pick those copies into `main`.
- Two remote copies are non-equivalent: the original recovery bundle and an earlier Hindsight daemon implementation. Extract current behavior from this branch instead.
- Machine-readable active topology, focused gates, and related PRs: `docs/fork-overlay-topology.json`.

## 2026-09-03 upstream refresh

- Fetched once and froze `upstream/main` at `63279301bcbdc185c1b07b98a9312eb0c862f26d`, 1,269 commits beyond the previous frozen base. Backup refs preserve all 34 source refs under `backup/hermes-refresh-20260903-170015/*`; the external ref ledger is `/home/zip/.hermes/backups/hermes-refresh-20260903-170015/refs-before.txt`.
- Audited all 21 canonical topics against the frozen upstream delta and 37 related pull requests. No topic commit is patch-equivalent to upstream and no whole topic is semantically superseded, so all 21 remain active.
- Retained only the distinct behavior around merged upstream work: provider registration from PR #31907, WSL enablement from PR #4317, managed-lockfile cleanup from PR #52841, undelivered-steer reporting from PR #76805, and post-update processing from PR #92769 are upstream-owned prerequisites rather than reasons to duplicate their older approaches.
- Replayed every root and both declared stacks in isolation. Semantic conflict resolutions preserve upstream's centralized non-interactive Git helper, cron/unattended fail-closed approval ordering, `compacting` status support, edited-history-input routing, and current Ink layout ownership while retaining the fork's replay rollback, delegated-child decision, staged-voice shutdown, and structural repaint contracts.
- Composed `integration/main-refresh-20260903` once from 75 topic commits, including one test-only adaptation to upstream's profile-scoped startup thread, then restored this topology ledger as integration-only documentation. The focused TUI contracts pass 167 tests; TUI typecheck/lint and Ink/production builds pass; web typecheck and Python syntax/whitespace checks pass. The whole TUI suite's 22 failures reproduce identically on frozen upstream and are baseline/environment debt, not overlay regressions.
- Preferred future consolidations: one renderer owns physical repaint; one generation-bound owner reaps session transport; one noninteractive updater transaction owns baseline/replay/rollback/lease; one supervised capture lifecycle owns microphone and GPU leases; and registered provider hooks own STT integration rather than fork-local registries.

## 2026-08-30 upstream refresh

- Fetched once and froze `upstream/main` at `66666f6e2eca0ae883195a34c66131985ea7dd06`; timestamped backup refs preserve the prior integration and every contribution tip.
- Replayed all canonical roots and both declared stacks. The fleet now has 21 active topics, including the new isolated `contrib/tui-numeric-selection` root.
- Archived retired zero-delta markers (`delegation-routing`, `trace-upload-compat`) and duplicate aliases (`hindsight-runtime-rebased`, `web-defensive-rendering-rebase`) under timestamped `archive/*` refs.
- Audited every active topic against upstream PR metadata and current upstream patches. No merged PR supersedes a whole active topic; related PRs are recorded in the topology manifest.
- Adapted TUI repaint recovery to current Ink architecture: Ink alone owns physical focus/resize recovery. The app updates layout width but no longer races the renderer with a second `forceRedraw`, preventing stale status frames from covering wrapped composer input.
- Added a bounded live-transcript-tail invalidation owner for structural tool/thinking-tree transitions and unmount. Ordinary assistant token growth keeps the same signature, avoiding per-token full redraws while stale physical tree rails are erased when live block shape changes.
- Preserved staged voice cancellation: Ctrl-B clears local `REC` state immediately while recorder shutdown/transcription completes. Added visible-window numeric quick picks to the model picker; digits remain filter text once a filter is active.

## 2026-08-27 upstream refresh

- Fetched upstream once for the main replay and froze `5d4ad23b0dc1412fea1f6592160ab4e8d154269c` after a 3,699-commit advance. Closure added 16 cleanly replayed commits; the read-only updater smoke then detected one additional disjoint model-picker commit, producing final base `6607f706732492b4ffd226e38a73a9994ac97fd1`. Rollback refs and receipts are under `/home/zip/.hermes/backups/hermes-refresh-20260827-093326/`.
- Refreshed all 22 canonical `contrib/*` topics while preserving the Hindsight -> local inference -> Parakeet -> staged voice and frame -> approval -> payload stacks. Twenty topics remain nonzero; `contrib/trace-upload-compat` and retired `contrib/delegation-routing` are zero-delta markers at the final upstream tip.
- Upstream superseded the old model-facing delegation-routing policy, compression-owner append recovery (replaced by watermark compaction), the plugin status-item surface, TUI pet single-flight helper, selected-workspace npm closure, and stale desktop-freshness assertions. Their pre-refresh history remains under timestamped backup refs.
- Adapted surviving behavior to current contracts: cron and single-query approval stay fail-closed before delegated-child policy; current updater helpers retain fork rebase/rollback plus HEAD-aware banner cache invalidation; TUI lifecycle retains hydration/resume/Ctrl-C behavior; current Ink imports retain frame repair; voice retains WSL/Pulse and staged bounded capture together.
- Promoted the preserved dirty Parakeet readiness/warmup changes and voice transcription-failure signaling onto their owning topics. The old plugin-status dirty hunk was intentionally omitted because its complete upstream extension surface no longer exists.
- Composed `integration/main-refresh-20260827` once from refreshed topic deltas, then closure-rebased its 69 commits. `git range-diff` accounts for every retained overlay change and records obsolete commits explicitly rather than silently replaying them.
- Validation: the 39-file Python pass reached 1,739 passing tests before isolated diagnosis; all transient shared-process failures passed independently, three stale test contracts were corrected on their owning topics, and the adapted rerun passed 733 tests. Closure-overlap verification passed 697 tests. Changed TUI tests passed 367; TUI typecheck/lint and web typecheck passed. `git diff --check` passed throughout.

## 2026-08-13 upstream refresh

- Fetched once and froze `upstream/main` at `ae56c97c6063a87250e74eccfb5697dd303bf930`; 299 upstream commits advanced from the prior frozen base. Rollback refs are under `backup/pre-refresh-20260813-104042` and `backup/contrib-pre-refresh-20260813-104042/*`.
- Rebased every canonical `contrib/*` topic exactly once. The declared stacks remain Hindsight -> local inference -> Parakeet -> staged voice and TUI frame -> approval -> payload; `*-rebased` refs are aliases and `contrib/trace-upload-compat` is the zero-delta upstream tip.
- No topic is patch-equivalent to current upstream. Upstream superseded stale contributor assumptions: desktop launches retain the upstream always-build policy; voice keeps the current 3-second silence and thinking-sound defaults while retaining the fork's 300-second bounded dictation cap, delivery marker, countdown, and shutdown leases.
- Composed `integration/main-refresh-20260813` from topic ranges once (72 overlay commits including compatibility/test glue), without rebasing the overlay a second time. The 484-test focused Python pass exposed two stale upstream-contract assertions; their adapted rerun passed 25/25. TUI typecheck passed and voice handler tests passed (105).

## 2026-08-11 upstream refresh

- Fetched once and froze `upstream/main` at `c0106e50e7ecedb3ce34e785d949725dc4e0e457`, 125 commits beyond the previous base. Rollback refs and replay evidence are preserved under `/home/zip/.hermes/backups/hermes-refresh-20260811-101906`.
- Refreshed all canonical `contrib/*` topics and preserved the declared Hindsight/Parakeet/voice and TUI frame/approval/payload stacks. Twenty-one contributions remain distinct; zero-delta `contrib/trace-upload-compat` is fully superseded upstream.
- Upstream's 15 Kanban review-lifecycle commits supersede the fork's old review implementation. `contrib/kanban-persistence` was rebuilt with only the distinct accepted-backlog and deleted-parent contracts.
- Regenerated `uv.lock` for the Parakeet stack. Voice composition retained WSL/Pulse/Termux device handling plus staged dictation's bounded FLAC capture and recorder-shutdown lease guarantees.
- Strengthened `contrib/test-isolation` so doctor fixes isolate `PROJECT_ROOT` and `Path.home()`; the full Python sweep left the real `~/.local/bin/hermes` target unchanged. The sweep's inherited baseline failures and resource-sensitive cases all passed focused reruns after test-only corrections.
- Composed `integration/main-refresh-20260811` from 65 topic commits plus minimal integration/test/lint glue. Python verification, TUI/web/shared TypeScript and lint checks, 1,580 TUI tests, 3,680 Desktop UI tests, 1,035 Desktop Electron tests, web tests, and Desktop packaging passed.

## 2026-08-06 upstream refresh

- Fetched once and froze `upstream/main` at `aaf9688519cca58dd5f76a589a0911aff269b060`; rollback refs preserve `main` and every contribution under `backup/main-pre-refresh-20260806-160000` and `backup/contrib-pre-refresh-20260806-160000/*`.
- Rebased every active root once on the frozen SHA, moved zero-delta `contrib/trace-upload-compat` directly to it, preserved the declared `tui-frame-recovery` -> `tui-approval-review` -> `tui-tool-payload-disclosure` stack, and kept the Hindsight/web `*-rebased` refs as exact aliases of their canonical topics.
- `git cherry upstream/main <topic>` confirmed every nonzero topic remains unique upstream work; no contributor change was discarded as superseded. The integration candidate was composed from refreshed topic patches plus recorded integration glue, rather than replaying the overlay a second time.
- The only composition conflict was TUI install freshness in `hermes_cli/main.py`. It retains the lock-digest and dependency-closure checks, the workspace-scoped `npm install --no-save` sibling-preservation rule, and the current upstream update receipt. A follow-up restores the global fresh-bundle build guard. `git range-diff` matches all 52 prior overlay patches; focused Python/TUI checks, TypeScript, syntax, and whitespace checks passed.

## 2026-08-04 upstream refresh

- Fetched once and froze `upstream/main` at `f5be9236e00ddf2f2a412697f267078fc4ee068e`; rollback refs preserve `main` and every topic under `backup/main-pre-refresh-20260804-145646` and `backup/contrib-pre-20260804-145646/*`.
- Refreshed all 21 `contrib/*` refs. Every root has the frozen upstream as an ancestor; zero-delta `contrib/trace-upload-compat` points at the frozen SHA; duplicate Hindsight and web compatibility refs match their canonical topics.
- Preserved the declared TUI stack parent-first: `contrib/tui-frame-recovery` (`a95488acc`) -> `contrib/tui-approval-review` (`ed34bdd05`) -> `contrib/tui-tool-payload-disclosure` (`c91d9ac28`).
- Replayed the complete integration overlay onto the frozen SHA. `git range-diff` classified all 51 prior commits as patch-equivalent; focused TUI tests, TypeScript, lint, build, Python syntax, ancestry, stack topology, and whitespace checks passed.
- Frozen upstream and the replayed integration tree reproduce the same three assertion failures: two Windows launcher-quarantine assertions in `test_update_concurrent_quarantine.py` and one OpenViking closed-port timing assertion. Gateway test files also complete all assertions but can exceed process-cleanup time on this WSL host. These are baseline/environment findings, not replay regressions.

## 2026-08-03 frozen upstream refresh and session-recovery topics

- Added `contrib/tui-session-lifecycle` on current `upstream/main` `f03eb252c` for deterministic TUI dependency freshness, non-blocking inventory hydration, durable exit-resume IDs, and fail-open single-flight pet rendering. The extracted topic preserves upstream's newer workspace-install coverage; 16 focused TUI tests, 5 focused Python tests, TypeScript, lint, build, ancestry, and whitespace checks passed.
- Fetched once and froze `upstream/main` at `cb11a7e25579638c9f67e8501dd151f581c4c942`; all topic and integration replay used that immutable SHA with no worker fetches. Rollback refs preserve the pre-refresh heads under `backup/pre-refresh-20260803-140003/*`.
- Every `contrib/*` ref now has the frozen upstream SHA as an ancestor and is zero commits behind it. The declared stack remains `contrib/tui-frame-recovery` -> `contrib/tui-approval-review` -> `contrib/tui-tool-payload-disclosure`; duplicate compatibility refs point at their refreshed canonical topic heads.
- Semantic conflict resolutions retained current upstream architecture plus the fork contracts: cron approvals remain non-interactive/fail-closed before delegated-child auto-approval; delegated children cannot wait on inherited interactive approvals; workspace-scoped npm installs preserve sibling workspace dependencies while retaining npm-engine repair; TUI focus/resize recovery keeps the renderer-owned redraw and WSL direct-echo fallback.
- Added `contrib/autonomous-session-recovery` for delegated approval, dead compression-owner recovery, and detached-turn settlement cleanup; added `contrib/tui-todo-scroll` and `contrib/tui-session-tree-interventions` for the final August 3 TUI fixes.
- Upstream already contains patch-equivalent queued-paste and collapsed-paste fixes, so those two integration commits were intentionally omitted rather than duplicated.
- Reconstructed the integration overlay from the refreshed topic ranges on top of the frozen SHA. Topic ancestry, stack ancestry, and `git diff --check` passed before integration verification.
- Post-replay integration exposed one real cross-topic regression: the refreshed concurrent tool-progress path drained `/steer` before aggregate tool-output budgeting and could lose the user intervention. `contrib/tool-executor-flush` now retains the steer until the existing post-budget finalizer; its 32-test segmentation suite passes.
- Refreshed Kanban decompose/specify tests now follow the accepted-backlog contract on `contrib/kanban-persistence` (160 Kanban tests pass). New `contrib/test-isolation` injects the FAL fake client directly and isolates Iron Proxy OpenSSL and Termux/WSL host probes; all 15 files that failed during the first canonical pass subsequently passed after installing the repository-pinned FAL, Modal, Daytona, and Parallel Web SDKs.
- Patch-provenance validation found every functional integration patch on a materialized `contrib/*` ref. The only integration-only commits before this ledger update are `d1f010ec4` (post-replay TUI hook style normalization) and `f28045aef` (refresh documentation).

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
| `contrib/update-managed-install` | `upstream/main` | Sibling-workspace dependency preservation; older closure/freshness logic is superseded upstream. |
| `contrib/fork-update-rebase` | `upstream/main` | Fork overlay replay, rollback, and lease-protected origin synchronization. |
| `contrib/wsl-voice` | `upstream/main` | Scoped Pulse fallback plus dependent voice lifecycle commits. |
| `contrib/tool-executor-flush` | `upstream/main` | Completion flush, output-risk preservation, and post-budget `/steer` delivery. |
| `contrib/delegation-routing` | `upstream/main` | Retired zero-delta marker: upstream routing is config-authoritative and non-model-facing. |
| `contrib/hindsight-runtime` | `upstream/main` | Runtime failure/limits plus scoped startup optimization. |
| `contrib/local-inference-coordination` | `contrib/hindsight-runtime` | Shared local GPU workload lease and coordination. |
| `contrib/parakeet-stt-shared-service` | `contrib/local-inference-coordination` | Shared Parakeet service plus readiness/warmup hardening. |
| `contrib/voice-staged-dictation` | `contrib/parakeet-stt-shared-service` | Bounded staged capture, shutdown leases, dictation status, and transcription-failure signaling. |
| `contrib/trace-upload-compat` | `upstream/main` | Zero-delta upstream marker; original history remains under timestamped backup refs. |
| `contrib/usage-governor` | `upstream/main` | End-to-end usage status contract and lint cleanup. |
| `contrib/kanban-persistence` | `upstream/main` | Kanban persistence and accepted-backlog test contract. |
| `contrib/test-isolation` | `upstream/main` | Optional FAL routing fake plus host-independent Iron Proxy and Termux capability probes. |
| `contrib/tui-input-recovery` | `upstream/main` | Input, overlay, resize, focus, and WSL echo behavior. A governor-poll hunk was intentionally excluded because it belongs to `contrib/usage-governor`. |
| `contrib/tui-numeric-selection` | `upstream/main` | Consistent visible-window numeric quick picks for provider/model prompts. |
| `contrib/autonomous-session-recovery` | `upstream/main` | Delegated-child approval recovery and detached-turn settlement cleanup; compression-owner recovery is superseded by upstream watermark compaction. |
| `contrib/tui-todo-scroll` | `upstream/main` | Keep active turn todos mounted while transcript history scrolls. |
| `contrib/tui-session-tree-interventions` | `upstream/main` | Session-tree lineage plus safe steering and interruption controls. |
| `contrib/tui-session-lifecycle` | `upstream/main` | Dependency freshness, non-blocking hydration, durable exit-resume IDs, and fail-open cosmetic pet rendering. |
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
