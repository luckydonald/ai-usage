Working on plan file /home/user/.claude/plans/wise-discovering-popcorn.md — inventory of usage/quota parsers in ~/git/moritzfl/llm-subscription-usage-intellij. User wants MORE detail: exact credential/token source, verbose on what's needed from user, exact API routes (full URL/RPC call format, method, headers), exact response/request data model fields, and full detail on the custom SolidStart parser.

Do this ONLY for: OpenCode (Go/Zen).

Read fully:
- src/main/kotlin/de/moritzf/quota/opencode/{OpenCodeQuotaClient.kt,OpenCodeQuota.kt,OpenCodeWorkspace.kt,OpenCodeQuotaException.kt,SolidStartValueParser.kt}
- src/main/kotlin/de/moritzf/quota/opencode/proxy/OpenCodeZenSubscriptionProxyProvider.kt
- src/main/kotlin/de/moritzf/quota/idea/opencode/{OpenCodeApiKeyStore.kt,OpenCodeSessionCookieStore.kt}
- src/main/kotlin/de/moritzf/quota/idea/settings/OpenCodeSettingsPanel.kt
- src/main/kotlin/de/moritzf/quota/idea/common/OpenCodeQuotaProvider.kt

Report:
1. Credential source: exactly how credential enters system — user pastes what (session cookie value? full cookie header? auth token?) into which settings field. Exact cookie/header name expected.
2. Every distinct HTTP/RPC call: full URL including SolidStart server-function id format (`?id=<functionId>&args=<encoded>`), HTTP method, ALL headers sent (X-Server-Id, X-Server-Instance, Referer, Origin, Cookie — exact values/sources), and how args are encoded.
3. Full data model: every field in OpenCodeQuota, OpenCodeWorkspace and any nested classes — field name, type, purpose. Explain fetchQuota()/fetchWorkspaces()/discoverWorkspaceId() logic in detail — what decides which workspace/Go vs Zen eligibility.
4. SolidStartValueParser in full detail: the wire format grammar it parses (object/array/string/number literals, `!0`/`!1` booleans, `new Date(...)`, `$R[n]` / `$R[n]=value` back-references), how the recursive descent parser works, how the references map resolves cyclic/shared refs. Give a concrete example of an encoded/decoded pair if you can find or infer one from tests or comments.
5. Quirks/fallback logic (workspace auto-selection order, error handling for missing eligibility, etc).

Output as markdown, one H2 section "## OpenCode" with subsections. Be verbose and exact, quoting actual field names, code, and URLs. Copy-paste ready markdown for pasting into the plan file.