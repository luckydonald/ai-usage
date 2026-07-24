Working on plan file /home/user/.claude/plans/wise-discovering-popcorn.md — inventory of usage/quota parsers in ~/git/moritzfl/llm-subscription-usage-intellij. User wants MORE detail: exact credential/token source (direct user input? file read? OAuth flow? which store?), verbose on what's needed from user, exact API routes (full URL, method, headers), exact response/request data model fields (DTO field names, types).

Do this ONLY for: OpenAI Codex, Kimi (Moonshot), MiniMax.

Read fully:
- src/main/kotlin/de/moritzf/quota/openai/{OpenAiCodexQuotaClient.kt,OpenAiCodexQuota.kt,OpenAiCodexQuotaException.kt,OpenAiCodexQuotaSerializer.kt,OpenAiCredits.kt,UsageWindow.kt,RateLimitResetCredit.kt}
- src/main/kotlin/de/moritzf/quota/openai/dto/{CreditsDto.kt,OAuthTokenResponseDto.kt,OpenAiAuthorizationDto.kt,RateLimitDto.kt,UsageResponseDto.kt,UsageWindowDto.kt}
- src/main/kotlin/de/moritzf/proxy/auth/AuthLoader.kt, AuthFileResolver.kt, AuthManager.kt (find exact paths under src/main/kotlin/de/moritzf/proxy/auth/)
- src/main/kotlin/de/moritzf/proxy/util/JwtParser.kt
- src/main/kotlin/de/moritzf/quota/idea/settings/OpenAiSettingsPanel.kt

- src/main/kotlin/de/moritzf/quota/kimi/{KimiQuotaClient.kt,KimiQuota.kt,KimiDeviceHeaders.kt,KimiWebSearchClient.kt,KimiOAuthClient.kt,KimiCredentialRefresher.kt,KimiQuotaException.kt}
- src/main/kotlin/de/moritzf/quota/idea/kimi/{KimiAuthService.kt,KimiCredentialsStore.kt}
- src/main/kotlin/de/moritzf/quota/idea/settings/KimiSettingsPanel.kt

- src/main/kotlin/de/moritzf/quota/minimax/{MiniMaxQuotaClient.kt,MiniMaxQuota.kt,MiniMaxWebSearchClient.kt,MiniMaxQuotaException.kt}
- src/main/kotlin/de/moritzf/quota/idea/minimax/MiniMaxApiKeyStore.kt
- src/main/kotlin/de/moritzf/quota/idea/settings/MiniMaxSettingsPanel.kt

For EACH of the 3 providers report:
1. Credential source: exactly how credential enters system — user pastes what into which settings field, or file read from what exact path with what exact JSON structure, or OAuth flow steps. What exactly must user supply.
2. Token refresh logic if any (refresh_token grant, JWT exp check, interval, atomic file rewrite).
3. Every distinct HTTP API call: full URL, HTTP method, all headers (name + value/source), auth header format.
4. Full data model: every field name and type/purpose from the Kotlin data/serializable classes for request+response.
5. Quirks/fallback logic (alternate field names, retries, error codes, device fingerprint headers etc).

Output as markdown, one H2 per provider (## OpenAI Codex, ## Kimi, ## MiniMax), subsections for credential source / API calls / data models / quirks. Be verbose and exact, quoting actual field names and URLs from code. Copy-paste ready markdown for pasting into the plan file.