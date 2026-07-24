Have full detail now. Writing report.

## OpenCode

### Credential source
Two independent, orthogonal credentials, both stored via IntelliJ `PasswordSafe`, both entered by manual user paste in `OpenCodeSettingsPanel`:

1. **Session cookie** (used for quota fetching) — `OpenCodeSessionCookieStore` (`de.moritzf.quota.idea.opencode.OpenCodeSessionCookieStore`). `CredentialAttributes(SERVICE_NAME="OpenCode Session Cookie", USER_NAME="opencode-session")`. Settings-panel label: *"Extract from opencode.ai → DevTools → Storage → Cookies → `auth` cookie value. Valid for 1 year."* User pastes the raw value of the `auth` cookie (not the whole `Cookie:` header, just the value) into a `JBPasswordField`; clicking **Save** calls `OpenCodeSessionCookieStore.save(cookie)`.
2. **API key** (optional, used only for OpenCode Zen local-proxy pass-through, NOT for quota fetching) — `OpenCodeApiKeyStore`, `CredentialAttributes(SERVICE_NAME="OpenCode API Key", USER_NAME="opencode-api-key")`. Settings-panel tooltip: *"OpenCode API key for the local proxy."* Saved via separate **Save API Key** button. `OpenCodeZenSubscriptionProxyProvider` forwards this key upstream to `https://opencode.ai/zen/v1` as an OpenAI-compatible Bearer key (delegated to generic `OpenAiCompatibleApiKeySubscriptionProxyProvider`).

No OAuth flow, no file read — purely user-pasted values, cached in-memory (`AtomicReference`) after async load off the PasswordSafe.

### API calls
All requests use `java.net.http.HttpClient`, cookie header always `Cookie: auth=$sessionCookie`.

1. **Discover server-function ID** (one-time, cached in a static `AtomicReference<String?>`):
   - `GET https://opencode.ai/workspace/{workspaceId}/go` — headers: `Cookie: auth=...`, `Accept: text/html`. Response HTML is scanned with regex `_build/assets/([^.]+)\.js` for bundle asset paths.
   - For each matched bundle: `GET https://opencode.ai/{bundlePath}` (no extra headers besides cookie) — response JS is scanned with regex `queryLiteSubscription_query\s*=\s*createServerReference\("([a-f0-9]{64})"\)` to extract the 64-hex-char server function id. Result cached process-wide.

2. **List workspaces** — `GET https://opencode.ai/_server?id=def39973159c7f0483d8793a822b8dbb10d067e12c65455fcb4608459ba0234f&args=%5B%5D` (that hex string is a hardcoded constant `WORKSPACES_FUNCTION_ID`, args = URL-encoded `[]`).
   - Headers: `Cookie: auth=...`, `Accept: application/json`, `X-Server-Id: <same function id>`, `X-Server-Instance: server-fn:2`.
   - Response body scanned with regex `id:"(wrk_[A-Za-z0-9]+)",name:"([^"]*)"` to pull `(workspaceId, name)` pairs — not decoded via the SolidStart parser, just regex over raw text.
   - 401/403 → thrown as "session cookie is invalid or expired."

3. **Fetch Go quota for a workspace** — `GET https://opencode.ai/_server?id={functionId}&args={encoded}` where `functionId` = the discovered `queryLiteSubscription` hash, and `args` = URL-encoded JSON array `["{workspaceId}"]`.
   - Headers: `Cookie: auth=...`, `Accept: application/json`, `X-Server-Id: {functionId}`, `X-Server-Instance: server-fn:1`, `Referer: https://opencode.ai/workspace/{workspaceId}/go`, `Origin: https://opencode.ai`.
   - Body parsed via `SolidStartValueParser` (see below), decoded into `OpenCodeQuota` via kotlinx.serialization `decodeFromJsonElement`.

4. **Fetch billing info** — `GET https://opencode.ai/_server?id=c83b78a614689c38ebee981f9b39a8b377716db85c1fd7dbab604adc02d3313d&args={encoded ["{workspaceId}"]}` (hardcoded `BILLING_INFO_FUNCTION_ID`, no discovery needed since it's a fixed constant, unlike the Go function id).
   - Headers same pattern, `Referer: https://opencode.ai/workspace/{workspaceId}/billing`.
   - 404 treated as non-fatal (endpoint hash rotated) → balance omitted, logged as warning. 401/403 → thrown as invalid/expired cookie.

5. **Zen proxy pass-through** (not a quota fetch, a local reverse-proxy for OpenAI-compatible chat requests) — upstream base `https://opencode.ai/zen/v1`, Bearer-auth using the separately-stored API key.

### Data models
`OpenCodeQuota` (`@Serializable data class`):
- `rollingUsage: OpenCodeUsageWindow?`
- `weeklyUsage: OpenCodeUsageWindow?`
- `monthlyUsage: OpenCodeUsageWindow?`
- `mine: Boolean = false` — whether this workspace belongs to the authenticated user
- `useBalance: Boolean = false`
- `availableBalance: Long?` (var, filled in from separate billing call, not from the Go quota payload itself)
- `fetchedAt: Instant?` (from `ProviderQuota` interface)
- `rawJson`, `rawGoJson`, `rawBillingJson: String?` (`@Transient`, not serialized, kept for raw-response display in settings UI)

`OpenCodeUsageWindow`:
- `status: String = "ok"` (`"rate-limited"` is the notable other value — exposed via `isRateLimited` getter)
- `resetInSec: Long = 0`
- `usagePercent: Int = 0`

`usageFraction()` = max of the three windows' `usagePercent`/100. `activityFraction()` = sum of all three /100.

`OpenCodeWorkspace` (plain, not serializable): `id: String`, `name: String`, `mine: Boolean`, `hasGoSubscription: Boolean`.

`OpenCodeBillingInfo` (internal `@Serializable`): `balance: Long?`.

**Workspace/eligibility selection logic:**
- `fetchWorkspaces()` calls `fetchQuota()` per workspace, sets `mine = quota.mine`, `hasGoSubscription = quota.hasUsageState()` (true if any of the 3 usage windows non-null).
- `discoverWorkspaceId()` iterates workspaces in list order, returns first whose quota `hasUsageState()` OR `hasAvailableBalance()` (balance != null) is true; treats 401/403/404/0 status per-workspace as skip-and-continue, other errors rethrow.
- Settings-panel preselection order when populating the dropdown: stored `openCodeWorkspaceId` from settings → first workspace with `mine && hasGoSubscription` → first with `hasGoSubscription` → first workspace at all.
- `OpenCodeQuotaProvider` caches the resolved workspace id for 30 minutes (`WORKSPACE_CACHE_TTL_MS`), resets both workspace-id cache and the static function-id cache whenever the stored cookie changes, or on retryable failures (status 0/401/403, or a parse failure) it clears caches and retries fetch exactly once before surfacing the error.

### SolidStartValueParser (custom wire format)
The response body for `/_server` calls is **not JSON** — it's raw JS emitted by SolidStart's server-function serialization, of the shape:
```
$R[0]=$R[1]=$R[2]=[{key:"rollingUsage",...},...],$R[3]=...
```
`OpenCodeQuotaClient.parseRootObject()` locates the literal marker `"$R[0]="` in the body (`ROOT_ASSIGNMENT_MARKER`), then instantiates `SolidStartValueParser(body, indexAfterMarker)` and calls `parseValue()`.

Grammar handled by the hand-rolled recursive-descent parser (`parseValue()` dispatches on the current char):
- `{` → object: unquoted-or-quoted keys (`parseObjectKey()` accepts either a `"quoted"` string or a bare identifier of `[A-Za-z0-9_]+`), `:` separator, comma-separated `key: value` pairs, terminated by `}`.
- `[` → array: comma-separated values terminated by `]`.
- `"` → string, with standard JSON escapes (`\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t`, `\uXXXX`).
- `-`/digit → number (supports optional leading `-`, integer digits, optional `.` fraction, optional `e`/`E` exponent) — always kept as a `JsonPrimitive` string-of-digits (no float coercion in the parser itself).
- `!` → SolidStart's compact booleans: `!0` → `true`, `!1` → `false` (also tolerates literal `true`/`false` after `!`, though that combination doesn't appear in practice).
- `t`/`f` → bare `true`/`false` identifiers (fallback path, e.g. when not bang-encoded).
- `n` → either `null` or `new Date("...")` — the latter is special-cased: skips `new Date("` (9 chars), parses the quoted string, expects closing `)`, and represents the date as a plain `JsonPrimitive` string (ISO string as given, not converted to a real date type).
- `$` → reference expression `$R[n]` or `$R[n]=value`: parses `$`, `R`, `[`, a numeric index, `]`. If followed by `=`, parses the assigned value, stores it in the `references: MutableMap<Int, JsonElement>` keyed by index, and returns that value (this is how `$R[0]=$R[1]=$R[2]=[...]` chains resolve — each assignment both stores and returns, so the whole chain of refs ends up pointing at the same object). If NOT followed by `=`, looks up the already-stored value by index and returns it (this is the back-reference/de-dup mechanism — SolidStart reuses `$R[n]` without a fresh `=` when the same object instance is referenced again elsewhere in the payload); throws `"Reference $R[n] used before assignment"` if the index isn't in the map yet. String-keyed references (`$R["..."]`) are explicitly rejected as unsupported in this payload shape.

Concrete example (not lifted verbatim from a test — inferred from the parser/marker constants, since no fixture files were found in the read set): a realistic raw body looks like
```
$R[0]=$R[1]={rollingUsage:$R[2]={status:"ok",resetInSec:1800,usagePercent:42},weeklyUsage:null,monthlyUsage:null,mine:!0,useBalance:!1}
```
which parses to the `JsonObject` `{"rollingUsage": {"status":"ok","resetInSec":1800,"usagePercent":42}, "weeklyUsage": null, "monthlyUsage": null, "mine": true, "useBalance": false}`, then `kotlinx.serialization` decodes that into `OpenCodeQuota`. The chained `$R[0]=$R[1]={...}` form means "assign the object to slot 1, and slot 0 is itself just a reference/alias to slot 1's value" — both assignment forms return their value up the recursive call chain so the outer `parseRootObject()` always gets the fully-resolved object regardless of how many `$R[n]=` hops preceded it.

The `isNullQuotaResponse()` special-case treats a body of `$R[0]= null` / `$R[0]=null` / ending in `,null)` as "no Go subscription for this workspace" rather than a parse error, returning an empty `OpenCodeQuota()` instead of throwing.

### Quirks / notable
- Function-id discovery (scraping the Go page + JS bundle for the `queryLiteSubscription` hash) is the only provider in the whole codebase that reverse-engineers a frontend bundle to find its own API contract — everything else uses a fixed documented/stable endpoint. The billing-info function id, by contrast, is a hardcoded constant (apparently stable enough not to need discovery), with a resilient 404-as-non-fatal fallback for when it does rotate.
- `clearCachedFunctionId()` is a static/companion-level cache shared across all `OpenCodeQuotaClient` instances process-wide, reset whenever the session cookie changes or a retryable failure occurs.
- Workspace list is parsed by regex directly on the raw SolidStart body text, not through `SolidStartValueParser` — presumably because the shape there is simpler/flatter and regex was cheaper than writing a full traversal.