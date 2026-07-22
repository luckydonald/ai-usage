# Claude CLI fallback: detect first-run setup clearly

## Summary

The configured Claude profile is already the expected `/home/user/.claude`; the fallback copies its environment and explicitly sets `CLAUDE_CONFIG_DIR` to that path. `pexpect` does not use a temporary working directory. The recorded transcript is Claude Code’s theme-onboarding screen, which consumes the sent `/usage` command before usage output can appear.

## Key changes

- Recognize Claude’s first-run/theme-selection screen in the pseudo-terminal transcript before reporting a generic timeout.
- Raise an actionable error that names the configured profile path and instructs the user to initialize that exact profile interactively (for example, `CLAUDE_CONFIG_DIR=/home/user/.claude claude`), choose the theme, and retry.
- Preserve the existing configured-profile behavior; do not silently fall back to a different default profile and do not auto-select a theme or alter Claude configuration.
- Keep generic timeouts/errors for all other startup failures, without exposing raw terminal output that may contain sensitive information.

## Test plan

- Cover onboarding transcript detection, including ANSI-decorated output from the real error sample.
- Verify the resulting error includes the profile path and initialization guidance.
- Retain coverage for normal `/usage` parsing and non-onboarding timeout behavior.

## Assumptions

- The desired behavior is to leave Claude profile setup under user control.
- A theme-selection prompt is treated as required setup, not as an authentication failure; authentication remains handled by Claude’s normal configured profile.
