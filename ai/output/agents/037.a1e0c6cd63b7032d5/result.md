Good, enough evidence. Confirmed: metadata (Account list, non-secret) persisted via `TokenPulseSettingsService` (PersistentStateComponent → `tokenpulse.xml`), while the actual secret is saved via UI (`ui/TokenPulseConfigurable.kt`) into `CredentialsStore` → IntelliJ PasswordSafe (OS keychain).

## Findings

**All 5 providers** (Cline, Nebius, OpenRouter, OpenAI Platform, Xiaomi) receive their secret as a plain `secret: String` function parameter into `fetchBalance(account, secret)` / `testCredentials(account, secret)` — they never read any file or vendor CLI config themselves. The secret is fetched once, upstream, in:

- `src/main/kotlin/org/zhavoronkov/tokenpulse/service/BalanceRefreshService.kt:37` — `val apiKey = CredentialsStore.getInstance().getApiKey(account.id)`, then passed into the provider client at line 43 (`.fetchBalance(account, apiKey)`).

- `src/main/kotlin/org/zhavoronkov/tokenpulse/settings/CredentialsStore.kt:26-29` — `getApiKey()` calls `PasswordSafe.instance.getPassword(attributes)` (IntelliJ's `com.intellij.ide.passwordSafe.PasswordSafe`, backed by the OS keychain / native credential store), keyed by `CredentialAttributes(serviceName = generateServiceName("TokenPulse", accountId), userName = accountId)` (lines 36-41).

- The secret is written there via `saveApiKey()` (`CredentialsStore.kt:21-24`), called from `src/main/kotlin/org/zhavoronkov/tokenpulse/ui/TokenPulseConfigurable.kt` — the plugin's own Settings UI where the user pastes/enters the key/session — and also from `provider/ProviderRegistry.kt` (e.g. when persisting a captured session, still originating from user action/UI flow, not an external file).

### Per-provider verdict

1. **Cline** — `provider/cline/ClineProviderClient.kt:57` (`fetchBalance(account, secret)`): user-entered via plugin Settings UI (personal API key pasted by user), stored in OS keychain via PasswordSafe. Not read from any Cline-CLI-owned file.
2. **Nebius** — `provider/nebius/NebiusProviderClient.kt:81`: secret is a JSON blob (`appSession`/`csrfCookie`/`csrfToken`/`parentId`) captured through an embedded-browser login flow triggered from the plugin UI, then stored in PasswordSafe (per class doc comment lines 28-36 and `Account.kt:22-31`). Not read from an external vendor config file on disk — it's a session captured by the plugin itself.
3. **OpenRouter** — `provider/openrouter/OpenRouterProviderClient.kt:38`: user-entered Provisioning Key via Settings UI, stored in PasswordSafe. (Note: there's also `OpenRouterPluginBridgeClient.kt`, a "Plugin Integration" bridge mode, but it still resolves to a `provisioningKey` passed the same way — no external file read found.)
4. **OpenAI Platform** — `provider/openai/platform/OpenAiPlatformProviderClient.kt:66`: secret can be either a raw Admin API key entered by the user, or an OAuth token JSON blob obtained via the plugin's own PKCE OAuth flow (`AuthType.OPENAI_OAUTH`, `Account.kt:33-39`) — both cases: user-entered/plugin-driven flow, persisted in PasswordSafe. Not read from Codex's `~/.codex/auth.json` or any other external file (that's a separate, unrelated OAuth client for the Codex CLI provider in `provider/openai/chatgpt/oauth/`).
5. **Xiaomi** — `provider/xiaomi/XiaomiProviderClient.kt:62`: secret is either a raw API key entered by user, or a captured platform session JSON (serviceToken/passToken/cookies) obtained via embedded browser session capture triggered by the plugin, stored in PasswordSafe (doc comment lines 32-44).

### Contrast: what this repo's Claude Code / Codex providers do differently
Unlike the 5 above, `provider/anthropic/claudecode/ClaudeOAuthUsageClient.kt` and `provider/openai/chatgpt/oauth/CodexOAuthUsageClient.kt` are the ones that actually read external vendor CLI files from disk (e.g. `~/.claude/.credentials.json`, `~/.codex/auth.json`) — that logic lives in `provider/oauth/OAuthCredentialStore.kt` / `AbstractOAuthRefreshClient.kt`, not in any of the 5 providers you asked about.

### Settings persistence confirmed
- `settings/TokenPulseSettingsService.kt:10-35` — `PersistentStateComponent<TokenPulseSettings>` with `@State(name="TokenPulseSettings", storages=[Storage("tokenpulse.xml")])`: stores non-secret metadata (accounts list minus actual secrets, refresh interval, display prefs) in plaintext `tokenpulse.xml` under the IDE config dir.
- `settings/CredentialsStore.kt`: stores the actual secret bytes via IntelliJ `PasswordSafe` (OS keychain/native store, or IDE-encrypted fallback), never in `tokenpulse.xml`.
- `ui/TokenPulseConfigurable.kt` is the Settings UI Configurable where the user types/pastes keys or triggers OAuth/browser-session capture flows that ultimately call `CredentialsStore.saveApiKey(...)`.