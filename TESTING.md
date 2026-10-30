# Validation record

Checked 2026-10-20 on the running Omarchy Quattro desktop.

- `omarchy plugin validate`: passed.
- Qt 6 qmllint syntax/duplicate-ID checks: passed for all three QML files.
  Full static type linting requires the shell's dynamic `qs` import environment;
  syntax-only checks are not a claim of full type-lint coverage.
- 17 Python tests passed: shortened invocation paths with preserved arguments,
  framework/runtime and custom-project detection,
  internal tool exclusion, IPv4/IPv6/wildcard/HTTPS URLs, `/proc` socket decoding,
  unreadable socket tables, foreign ownership, live child-process discovery,
  graceful termination and port rebind, forced termination, stale identity,
  wrong port/inode, self-protection, and JSON error output.
- Enabled in the right bar section. Live service IPC reported ready without
  errors, discovered the existing Vite listener on IPv6 port 9527, and excluded
  Codex/OpenCode internal listeners. Existing user servers were not terminated.
- Shell summon/hide succeeded. Visual inspection confirmed the server bar icon,
  project/address/port/PID, wrapped launch command, URL, and both action buttons.
  No Konoports QML runtime errors were observed in the shell log.
- Series-style alignment: switched to shared `PanelHero`, bordered `Button`,
  `PanelSeparator`, theme font/color/spacing tokens, and a 380-unit panel width.
  Syntax/manifest checks passed. After restarting the shell to clear cached QML,
  visually checked both the empty state and a temporary Python HTTP listener:
  project/port alignment, compact command, localhost URL, and shared buttons.
  The temporary listener was terminated after the check.
- Regression: internal-tool exclusions inspect program identities instead of
  arbitrary arguments. A Python HTTP server with `--directory /tmp/opencode`
  is now discovered; live IPC confirmed the test listener at `localhost:8765`.

Still to test manually: browser launching, pointer/keyboard confirmation flow,
  empty-state icon hiding/reappearance, multiple/vertical bars, many-row scrolling, HTTPS
  servers, supervised/shared listeners, and container/network namespace behavior.
Stop tests only target child processes created by the test suite.
