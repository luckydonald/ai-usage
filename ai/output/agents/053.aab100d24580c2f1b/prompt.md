Read source code in ~/git/DimazzzZ/tokenpulse-intellij-plugin for these providers and extract EXACT implementation details (literal field names, literal URLs, literal headers — not summaries) needed to port to a Python tool:

1. Cline — files under `provider/cline/` (e.g. `ClineProviderClient.kt`). Need: exact response JSON field names for `/api/v1/users/me`, `/users/balance`, `/users/usages`, `/users/plan/usage-limits` (read actual Kotlin data classes / parsing code), exact headers used, how identity/email is derived from `/users/me` (exact field name).

2. OpenRouter — files under `provider/openrouter/` (`OpenRouterProviderClient.kt`, `OpenRouterPluginBridgeClient.kt`). Need: exact endpoint URL(s) used for credits/usage, exact JSON response field names parsed (is it `/api/v1/credits` giving `total_credits`/`total_usage`, or `/api/v1/key` giving `limit`/`usage`/`limit_remaining`, or something else entirely?), exact headers (Authorization scheme).

3. Also check: does this repo's xAI-adjacent or generic OAuth code (if any SuperGrok/xAI equivalent exists here — check `provider/` directory listing for anything xAI/grok-related) give any hints about identity fields not found in the other repo? If nothing exists, say so explicitly.

4. Shared infra: read `provider/SessionParser.kt` and `provider/oauth/{AbstractOAuthUsageClient,AbstractOAuthRefreshClient,TokenExpiry,OAuthHttp}.kt` — extract exact method signatures / patterns that could generalize (for reference, not for direct reuse since target is Python).

Return literal field names, literal strings, literal URLs, quoting actual code lines where useful. This is for porting to a Python client so precision matters more than prose.