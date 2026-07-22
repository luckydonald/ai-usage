# Claude default-profile canonicalization

## Summary

Treat `profile_dir: null`, an omitted profile, and the literal default path `~/.claude` as the same native Claude profile. Only a non-default profile directory may set `CLAUDE_CONFIG_DIR`.

## Implementation changes

- Add one Claude profile resolver that:
  - returns `~/.claude` for relay settings-file operations when the value is missing or `null`;
  - returns no environment override for missing, `null`, or the resolved default path;
  - returns an explicit `CLAUDE_CONFIG_DIR` only for a genuinely alternate profile.
- Use that resolver in CLI fallback startup, first-run recovery instructions, relay install, and relay removal.
- Canonicalize default-profile account options to `profile_dir: null` during provider setup/account creation, while retaining existing explicit default-path configurations as compatible input.
- Keep discovery’s existing fingerprint-compatible default-path value, then store the selected setup as `null`; this avoids duplicate accounts for existing discovered profiles.
- Update the Claude quick-start command to omit `--profile-dir` for the native default profile, documenting that the option is only needed for alternate profiles.

## Test plan

- Verify `null`, missing, and `~/.claude` all leave `CLAUDE_CONFIG_DIR` unset and produce a plain `claude` recovery command.
- Verify an alternate profile still sets the override, uses it in the recovery command, and writes relay settings there.
- Verify new default-profile setup persists `profile_dir: null` and rediscovery still recognizes an existing account.
- Retain the recorded onboarding-transcript and hashed-error-log coverage.

## Assumptions

- `null` is the canonical stored representation for Claude’s native profile.
- Existing account YAML containing the explicit default path remains valid and need not be migrated proactively.
