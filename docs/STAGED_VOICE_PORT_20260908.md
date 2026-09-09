# Staged voice transplant checkpoint

Isolated worktree /tmp/hermes-staged-voice-20260908; parent e67baf1853af4fbaff6e529abfabb310fe1ca073. Source 72acb2bb849b6f8aa90e73b90dcd3287f0abb79d, old parent 9bd1a2e6df91c93963b0745ca9150e57d8f247ff. Candidate remains uncommitted.

- Source-identical voice_capture_lease module and tests applied; verified module import origin inside this worktree, then two canonical tests passed. Prior tests-only result was rejected because editable-install fallback loaded the live module.
- Recorder-related source tests applied. Three-way production conflict rejected in favor of preserving upstream structure, then targeted semantic transplant started.
- PortAudio close retains stream handle on timeout/failure, supports retry, returns actual closure result, and preserves short responsive joins. Worker starts under the recorder lock to avoid duplicate workers before is_alive becomes true. Three regression tests failed before transplant and passed after.
- Termux stop/cancel/shutdown preserve recording state until termination is confirmed, return success/failure where applicable, and remain idempotent. Existing upstream quiet-process and reset-state helpers retained.
- Final targeted canonical gate: six tests passed (Termux recorder class plus stream close exception/timeout). git diff --check passed. No physical microphone was used.

Broad test_voice_mode gate before Termux transplant: 61 passed, 13 failed, 2 skipped, normal exit 1; full log /tmp/hermes-recorder-full-gate.log. Broad gate has not been rerun after Termux change. Remaining failures include missing Pulse fallback/shutdown integration and bounded-capture/progress callback interfaces. No full recorder acceptance claimed.

Still required: remaining recorder delta, hermes_cli/voice.py ownership integration, config and classic CLI hooks, gateway handlers, frontend state, focused/full gates and source preservation audit. Original live checkout, canonical refs, and memory store remain untouched.

## Follow-up: Pulse shutdown semantics

Ported fallback process/path ownership and cancel/shutdown boolean results. A failed kill/wait retains the process handle and reports failure; successful termination permits file cleanup and stream closure. This ports shutdown semantics only: fallback startup and normal stop remain outstanding.

Full canonical recorder rerun: 65 passed, 9 failed, 2 skipped; ordinary exit 1. Evidence: /tmp/hermes-recorder-after-shutdown.log. Diff check passed. Remaining failures cover WSL detection, fallback startup/cutoff, cleanup expectations, silence/cutoff callback interfaces, and normal-stop timeout propagation. No full recorder acceptance claimed.

## Follow-up: normal stop, cleanup, and WSL test isolation

Normal Pulse stop now requests graceful completion, forces termination on wait failure, and propagates a second wait failure without dropping the process handle. Existing upstream WAV validation remains unchanged. Three additional finalization tests pass (successful save, process-error reporting, and short capture rejection).

Ported source-topic FLAC cleanup alongside WAV cleanup while retaining upstream's concise cleanup loop. The old WSL test depended on whether the host had PowerShell/ffmpeg installed; it now explicitly excludes that output fallback and PipeWire. Production WSL detection stays unchanged, preserving upstream's TTS-only fallback and its separate tests.

Latest full canonical recorder gate: 68 passed, 6 failed, 2 skipped; ordinary exit 1. Evidence: /tmp/hermes-recorder-after-cleanup.log. Diff check passed. Remaining failures are Pulse fallback startup/limit handling and recorder/full-duplex silence-progress/cutoff interfaces. Candidate remains incomplete and uncommitted; no live changes or publication.

## Follow-up: bounded Pulse startup

Ported ffmpeg lossless mono 16 kHz FLAC capture with a configured positive duration cap (300 seconds otherwise), missing-default-input fallback dispatch, and completion-monitor cutoff/stop callbacks. Both source-topic Pulse startup tests now pass. Latest full recorder gate: 70 passed, 4 failed, 2 skipped; ordinary exit 1, /tmp/hermes-recorder-after-pulse-start.log. Diff check passed.

Still incomplete: public start callback arguments and full-duplex callbacks. Before recorder acceptance, additionally verify repeated Pulse start/stop cycles and early process completion against startup state transitions; passing helper tests does not establish those integration behaviors.

## Follow-up: callback contract and focused gate

Ported recorder silence-countdown transitions, resumed-speech clearing, one-shot hard-limit reporting, and Termux-compatible callback arguments. Adapted the newer upstream `_capture_until_quiet` / `_BargeDetector` decomposition rather than replacing it with the source topic's monolithic listener. Full-duplex capture now reports endpoint countdown/reset and hard-limit cutoff.

Reconciled source-topic policy defaults: `input_mode=submit`, `recording_mode=silence`, five-minute configured capture cap, and explicit `thinking_sound=true`. The low-level thinking-sound helper remains fail-closed (`false`) when the voice config key is absent; loaded canonical defaults explicitly enable it. CLI malformed/missing max-duration fallback is now five minutes. `_RecorderBase` owns the duration field so both recorder implementations satisfy the typed CLI contract.

Canonical focused gate `/tmp/hermes-staged-voice-focused-green.log`: 6 files, 122 passed, 0 failed, 2 macOS-only skipped; ordinary exit 0. Included recorder, Pulse-finalization, microphone-lease, classic CLI integration, thinking-sound, and duration-policy tests. `git diff --check` passed.

Not yet accepted: continuous-capture lease release before STT, staged/dictation CLI/gateway/TUI behavior, repeated real Pulse cycles, physical microphone capture, macOS lane, source-commit preservation/supersession audit, or broader integration tests.

## Follow-up: silence-triggered capture ownership boundary

Added a serialized capture-shutdown helper around the newer upstream continuous-loop decomposition. For silence-triggered capture, recorder stop and stream shutdown now finish before `on_capture_stopped` releases cross-process microphone ownership, and that callback runs before transcription. A shutdown result of `False` or an exception retains ownership. Capture-notification state is reset before each initial/restarted recording.

Added two adapted tests rather than applying the obsolete source test fixture wholesale: ordering is `stop -> shutdown -> capture_stopped -> transcribe`, and failed shutdown does not release. RED evidence: `/tmp/hermes-voice-capture-boundary-red.log`; GREEN evidence: `/tmp/hermes-voice-capture-boundary-green.log`. Full current wrapper gate: 25 passed, 0 failed, ordinary exit 0 (`/tmp/hermes-voice-wrapper-boundary.log`); diff check passed.

Still pending in this layer: public `stop_continuous` shutdown/retry semantics, overlapping-stop serialization cases, completion-beep/error behavior, and the remaining 19 source-only wrapper tests. Silence-path green does not imply those paths are preserved.

## Follow-up: retry-safe public stop

`stop_continuous` now retains its callback/ownership state when recorder shutdown is unconfirmed. While pending, a new start returns busy and a second public stop retries cancellation plus shutdown. Only confirmed shutdown clears `_continuous_stopping`, clears callbacks, reports idle, and permits lease release. The normal cancel path no longer emits the STT-completion beep.

Verification includes both a deterministic fake-shutdown sequence (`False`, then `True`) and the real `AudioRecorder` Pulse fallback path with two `TimeoutExpired` waits followed by successful termination. The second owner cannot acquire the file lease between attempts and can acquire it after the successful retry. RED evidence: `/tmp/hermes-voice-public-stop-red.log`. Final wrapper gate: 27 passed, 0 failed, ordinary exit 0 (`/tmp/hermes-voice-public-stop-pulse.log`); diff check passed.

Still pending: forced-transcription shutdown completion handling, overlapping shutdown callers, source error callbacks and completion cues, broader gateway integration, and remaining source-only wrapper behavior. No claim that all continuous paths are green yet.

## Follow-up: forced-transcription shutdown completion

The forced-stop STT tail now delivers any captured transcript but retains `_continuous_stopping`, callbacks, and lease ownership when stream shutdown is unconfirmed. It reports idle and clears retry state only after confirmed shutdown; the next public stop can perform that retry. The completion cue now plays only when STT produced usable text, not for cancellation or empty capture.

RED evidence: `/tmp/hermes-voice-forced-stop-red.log`. Full wrapper GREEN: 28 passed, 0 failed (`/tmp/hermes-voice-forced-stop-green.log`). Combined staged-voice gate: 7 files, 150 passed, 0 failed, 2 macOS-only skipped, ordinary exit 0 (`/tmp/hermes-staged-voice-continuous-green.log`). `git diff --check` passed.

Still pending: overlapping automatic/public stop serialization, transcription-error callback propagation, other source-only loop cases, gateway/TUI behavior, physical and macOS runtime checks, and preservation audit.

## Follow-up: overlapping stop serialization

Ported the source race test onto the upstream callback-tuple implementation. One thread runs the automatic silence stop while blocked inside recorder stop; a concurrent forced public stop waits behind `_continuous_capture_stop_lock`. No lease-release callback fires while the owning shutdown is blocked, both calls finish after release, and exactly one callback fires.

Targeted race gate passed (`/tmp/hermes-voice-overlap-target.log`). Full wrapper gate: 29 passed, 0 failed, ordinary exit 0 (`/tmp/hermes-voice-overlap-green.log`); diff check passed. This is deterministic fake-recorder concurrency coverage, not a physical-device stress test.

Still pending: transcription-error callback propagation, direct helper cases for blocked PortAudio close/Termux failure, remaining loop semantics, gateway/TUI staged dictation, and broader runtime/preservation gates.

## Follow-up: transcription error propagation

Split transcription into a result helper returning `(text, provider_error)` while preserving the existing text-only compatibility wrapper. Continuous silence and forced-stop paths now forward provider failures through `on_error`; provider failure holds the no-speech counter rather than treating infrastructure failure as user silence. Empty successful audio remains a true silent cycle. Completion beeps moved after usable text confirmation, so failed/empty STT no longer sounds successful.

RED evidence: `/tmp/hermes-voice-error-red.log`. Full wrapper gate: 30 passed, 0 failed (`/tmp/hermes-voice-error-green.log`). Combined staged-voice gate after the six-field callback-tuple change: 7 files, 152 passed, 0 failed, 2 macOS-only skipped, ordinary exit 0 (`/tmp/hermes-staged-voice-error-combined.log`). `git diff --check` passed.

Still pending: direct blocked-close and Termux lease helper cases, remaining loop tests, then gateway/TUI staged-dictation transplant and broader source audit.

## Follow-up: direct shutdown failure matrix

Ported source helper tests for Pulse wait timeout in both discard and keep-audio modes, Termux stop failure, PortAudio close exception, and repeated shutdown attempts while one PortAudio close worker is blocked. In every failure case the competing process remains unable to acquire the microphone lease, recorder ownership/path state remains available for retry, and repeated blocked-close calls create only one close worker.

Targeted direct-shutdown gate passed (`/tmp/hermes-voice-direct-shutdown.log`). Full wrapper gate: 35 passed, 0 failed, ordinary exit 0 (`/tmp/hermes-voice-direct-shutdown-green.log`); diff check passed. These tests use deterministic process/stream doubles plus the real recorder lifecycle code and real file lease implementation; no microphone hardware was exercised.

Remaining wrapper work is now primarily client-driven loop semantics and gateway-visible policy rather than untested recorder-shutdown classes. Gateway/TUI staged-dictation transplant, broader integration, macOS/physical capture, and source preservation audit remain open.

## Follow-up: client-driven loop closure

Ported the remaining source behaviors for non-transcribing cancel cues, one-shot (`auto_restart=false`) completion, retained silence strikes across separately initiated captures, forced-buffer delivery, empty forced captures reaching the silence limit without a success cue, successful forced capture resetting strikes, stop failure fallback to cancel, and restart failure returning idle.

Full wrapper gate: 44 passed, 0 failed, ordinary exit 0 (`/tmp/hermes-voice-client-loop-complete.log`); diff check passed. A mechanical source/current test-name comparison leaves four source-only names, all ownership cases represented by adapted tests under different names because the upstream implementation now uses a callback tuple. This is semantic coverage, not byte-identical test preservation.

Continuous wrapper behavior is now locally green. Next voice phase: gateway method/config integration and TUI staged-dictation state. Broader topic audit and runtime gates remain open.

## Follow-up: gateway enablement and effective policy

Adapted the monolithic source changes into upstream's split `tui_gateway/methods_voice.py`. `voice.toggle on` now probes requirements before changing the runtime flag and returns 4016 with details when unavailable. Gateway status now reports normalized input mode, silence/manual recording mode, positive silence duration, and the five-minute default hard cutoff. Toggle-off also stops the ambient thinking sound.

RED evidence: `/tmp/hermes-voice-gateway-policy-red.log`. Focused policy GREEN: `/tmp/hermes-voice-gateway-policy-green.log`. All current gateway tests selected by `voice`: 17 passed, 0 failed, ordinary exit 0 (`/tmp/hermes-voice-gateway-policy-all.log`); diff check passed.

Known temporary inconsistency: `voice.toggle/status` now reports the five-minute source policy, but `voice.record start` still forwards upstream's old 120-second fallback. The next gateway step must port the complete start/status contract, callbacks, and lease ownership before gateway behavior is accepted.

## Follow-up: gateway recording contract and ownership

Removed the 120/300-second inconsistency. `voice.record start` now uses the normalized five-minute policy, 5-second silence default, manual/silence mode, and submit/dictation delivery mode. It emits stable listening timestamps plus silence countdown and cutoff metadata, forwards STT failures as transcript errors, and holds a process/file microphone lease until the wrapper's confirmed `on_capture_stopped` boundary.

Added process-local ownership shared by one-shot recording and the full-duplex listener; full duplex acquires before arming and releases in its `finally` path. Start failures/busy returns release newly acquired ownership, while explicit stop intentionally retains it until recorder shutdown confirms closure. The source policy contract test exercises callback payloads and release timing.

Gateway + wrapper voice gate: 62 passed, 0 failed (`/tmp/hermes-voice-gateway-record-green2.log`). Expanded gateway selection `voice or full_duplex or barge`: 22 passed, 0 failed (`/tmp/hermes-voice-gateway-capture-owners.log`). Ordinary exits 0; diff check passed.

Still pending: explicit same-process and mocked cross-process refusal tests, dictation transcript test, persisted dictation/silence toggle actions, richer full-duplex status callbacks, TUI state, and broad gateway suite.

## Follow-up: gateway owner refusal, dictation, and controls

Added explicit tests that a one-shot recording refuses an active full-duplex owner, refuses an unavailable cross-process file lease, and emits `delivery=draft` in dictation mode. Added persisted `voice.toggle dictation on|off|status` and `voice.toggle silence off|1..60|status` actions with validation and writes to `voice.input_mode`, `voice.recording_mode`, and `voice.silence_duration`.

Extended `start_continuous` and `AudioRecorder` with the real manual/silence switch plus silence-progress/cutoff callbacks; callbacks survive auto-rearm through the upstream wrapper decomposition. Initial combined test exposed that dynamically rebound split handlers do not inherit `methods_voice.py`'s module-level `math` global. Fixed by importing `math` locally inside the silence handler rather than changing the server binding contract.

Final gateway/wrapper selection (`voice or full_duplex or barge`): 71 passed, 0 failed, ordinary exit 0 (`/tmp/hermes-voice-gateway-controls-green.log`); diff check passed. Earlier failing evidence: `/tmp/hermes-voice-gateway-controls.log`.

Next: richer full-duplex capture status/cutoff callbacks and then TUI state/commands. Full gateway file and topic preservation audit remain open.

## Follow-up: full-duplex metadata and gateway closure

Full-duplex capture now uses the same normalized 5-second endpoint and 300-second hard cap, forwards both into `full_duplex_listen`, and emits `voice.status` events for listening (stable timestamp/countdown), cutoff/transcribing, and idle. STT provider failures emit `voice.transcript {error}` while capture files are still removed in `finally`. Existing upstream `_fd_trip` interruption logic remains the sole TTS/turn-cut path.

Updated the existing barge test to assert callback arguments and status phases; added the source transcription-failure test. Gateway/wrapper focused selection: 72 passed, 0 failed (`/tmp/hermes-voice-gateway-full-duplex.log`). Complete gateway file: 646 passed, 0 failed, ordinary exit 0 (`/tmp/hermes-voice-full-gateway.log`). `git diff --check` passed.

Gateway phase is locally green under deterministic tests. Remaining voice work: TUI types/state/commands and frontend builds/tests, then source-commit preservation/supersession audit and physical/macOS limitations.

## Follow-up: TUI status/event state

Added typed gateway payloads for recording policy, deadline/countdown, cutoff, draft delivery, and STT errors. Added pure `recordingDeadlineFromStatus` and `formatVoiceStatusLabel` helpers, React state for authoritative deadline/silence countdown, a one-second display clock active only during bounded recording, and event-handler behavior that clears state on STT/idle, reports cutoff/error, and appends explicit dictation deliveries with paragraph separation without submitting.

The first event test invocation did not execute that suite because the isolated `@hermes/ink` output was absent (`./dist/entry-exports.js`); this was a build precondition failure, not behavioral evidence. After `npm run build:ink`, the two focused frontend files passed 114 tests (`/tmp/hermes-voice-tui-events-green2.log`). `npm run typecheck --workspace ui-tui` passed (`/tmp/hermes-voice-tui-typecheck.log`). Pure status tests are source-aligned; event tests are adapted to current upstream context ownership.

Remaining TUI work: input hotkey stop routing/request state and `/voice` status/dictation/silence commands, then broader frontend tests/lint/format/production build.

## Follow-up: TUI controls and frontend closure

Recording starts now wait for authoritative gateway state; stop clears REC and shows STT immediately while synchronous recorder shutdown is pending. Gateway responses distinguish active barge-listener ownership from STT-busy state. The configured record hotkey can stop an open microphone even when ordinary input is blocked, without allowing blocked capture starts or unrelated keys.

`/voice status` now displays input delivery, recording termination mode, silence endpoint, and hard cutoff. `/voice dictation on|off` and `/voice silence 1..60|off` route to the persisted gateway controls with explicit user feedback.

Final frontend gates: all 169 TUI test files / 1,777 tests passed (`/tmp/hermes-voice-tui-final-tests.log`); TypeScript passed; production build passed; changed-file ESLint passed with zero warnings; Prettier check passed. Logs: `/tmp/hermes-voice-tui-final-typecheck.log`, `/tmp/hermes-voice-tui-final-build.log`, `/tmp/hermes-voice-tui-final-lint.log`, `/tmp/hermes-voice-tui-final-format.log`. `git diff --check` passed and npm installation changed no lockfile.

TUI staged-dictation behavior is locally green. Remaining topic work: source-commit preservation/supersession audit, complete combined Python/frontend gates, and explicitly bounded physical/macOS runtime limitations before this topic can be composed.
