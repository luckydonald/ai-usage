Repo: ~/git/DimazzzZ/tokenpulse-intellij-plugin (Kotlin IntelliJ plugin).

Prior research found these providers read a "stored API secret/key" then call remote API: Cline (provider/cline/ClineProviderClient.kt), Nebius (provider/nebius/NebiusProviderClient.kt), OpenRouter (provider/openrouter/OpenRouterProviderClient.kt), OpenAI Platform (provider/openai/platform/OpenAiPlatformProviderClient.kt), Xiaomi (provider/xiaomi/XiaomiProviderClient.kt).

Question: where does that stored secret actually come from — is it read from a local disk file/config (e.g. some vendor CLI's own config file on disk, similar to Claude Code's ~/.claude/.credentials.json or Codex's ~/.codex/auth.json), or is it entered directly by the user into the plugin's own Settings UI (settings/ package) and persisted only in IntelliJ's own settings storage (not read from any external vendor file)?

For each of the 5 providers above:
1. Find where the secret/key variable is populated - trace it back to its origin (grep for the field name, follow to settings/ package or provider/oauth/OAuthCredentialStore.kt, or to a local file path).
2. State clearly: "user-entered via plugin settings UI" vs "read from external vendor config file on disk at path X" vs "read from OS keychain".
3. Cite file:line for the read/retrieval call.

Also check ProviderRegistry.kt / settings/ package structure to confirm how plugin settings (API keys entered by user) are persisted (e.g. PersistentStateComponent, PasswordSafe, plaintext).

Keep answer as a short list per provider, cite file paths.