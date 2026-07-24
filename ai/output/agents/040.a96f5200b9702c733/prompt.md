Working on plan file /home/user/.claude/plans/wise-discovering-popcorn.md — inventory of usage/quota parsers in ~/git/moritzfl/llm-subscription-usage-intellij. User wants MORE detail: exact credential/token source, verbose on what's needed from user, exact API routes (full URL, method, headers), exact response/request data model fields.

Do this ONLY for: Ollama, SuperGrok (xAI), Z.ai.

Read fully:
- src/main/kotlin/de/moritzf/quota/ollama/{OllamaQuotaClient.kt,OllamaQuota.kt,OllamaWebSearchClient.kt,OllamaQuotaException.kt}
- src/main/kotlin/de/moritzf/quota/idea/ollama/{OllamaApiKeyStore.kt,OllamaSessionCookieStore.kt}
- src/main/kotlin/de/moritzf/quota/idea/settings/OllamaSettingsPanel.kt

- src/main/kotlin/de/moritzf/quota/supergrok/{SuperGrokQuotaClient.kt,SuperGrokQuota.kt,SuperGrokImagineClient.kt,SuperGrokWebSearchClient.kt,SuperGrokQuotaException.kt}
- src/main/kotlin/de/moritzf/quota/idea/settings/SuperGrokSettingsPanel.kt
(find credential store file for SuperGrok — search src/main/kotlin/de/moritzf/quota/idea/ for supergrok directory or ApiKeyStore/CredentialsStore/SessionCookieStore for it)

- src/main/kotlin/de/moritzf/quota/zai/{ZaiQuotaClient.kt,ZaiQuota.kt,ZaiWebSearchClient.kt,ZaiQuotaException.kt}
- src/main/kotlin/de/moritzf/quota/idea/zai/ZaiApiKeyStore.kt
- src/main/kotlin/de/moritzf/quota/idea/settings/ZaiSettingsPanel.kt

For EACH of the 3 providers report:
1. Credential source: exactly how credential enters system — user pastes what into which settings field, or file read, or OAuth flow. What exactly must user supply (API key? session cookie? both?).
2. Token refresh logic if any.
3. Every distinct HTTP API call: full URL, HTTP method, all headers (name + value/source), auth header format.
4. Full data model: every field name and type/purpose from Kotlin data/serializable classes for request+response, including any web-search-credit specific endpoints.
5. Quirks/fallback logic.

Output as markdown, one H2 per provider (## Ollama, ## SuperGrok, ## Z.ai), subsections for credential source / API calls / data models / quirks. Be verbose and exact, quoting actual field names and URLs from code. Copy-paste ready markdown.