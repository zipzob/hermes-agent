# Usage-governor transplant — verification in progress

Source topic: 3672621f4664a9340a9f88a43c2ac60f0cd07975.
Frozen upstream: c8aa5608c24e3636e77c267650c0f1f52e44adb0.
Worktree: isolated repair/refresh-20260908/usage-governor; uncommitted candidate, not installed.

Preserved upstream's module extraction and HTTP/reset helpers. Codex-specific window metadata is layered over _usage_windows; independent model limits, duration-derived labels, overage, virtual daily pace, and reset exhaustion are retained. Shared classic-CLI segment rendering receives the plugin item once; current gateway _get_usage transports it to the TUI. Plugin status entries use upstream registration ownership/disposal and registry reset rather than restoring old plugin methods.

Parent canonical verification:
- Before transplant: usage + CLI status files, 54 passed / 8 failed.
- After account changes: tests/agent/test_account_usage.py and tests/test_account_usage.py, 16 passed / 0 failed.
- Status/usage/governor-filtered selection: CLI, plugin and gateway files, 86 passed / 0 failed (includes 35 gateway tests; not whole gateway suite).
- Final complete plugin + CLI status files including disposal regression: 128 passed / 0 failed.
- Staged and unstaged git diff --check passed.

Follow-up parent gates:
- Complete tests/test_tui_gateway_server.py: 638 passed, 0 failed; normal canonical runner exit (85-second per-file cap).
- Lockfile-based npm ci for TUI/Ink/shared workspaces with dev dependencies and lifecycle scripts disabled succeeded.
- Ink build, TypeScript check, 32 appChromeStatusRule tests, and production TUI build passed.
- Three blank-line lint warnings in the replayed governor poll were fixed; changed frontend files passed ESLint with --max-warnings 0 and Prettier checks. Typecheck, tests and production build reran after the edit.
- No lockfile edits were intended; verify final root lockfile diff during sealing.

Still required: supersession/per-commit preservation review, runtime polling/interaction acceptance, and final integration. No complete topic or publication acceptance is claimed. No provider reset was performed; reset tests use fixtures.
