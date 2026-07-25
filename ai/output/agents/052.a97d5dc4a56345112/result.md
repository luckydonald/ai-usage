# Implementation Plan: 4 New Providers + 2 Shared OAuth Helpers

## Architecture confirmed from source

- `LoginMethod` (`src/ai_usage/providers/base.py:50`): `key`, `display_name`, `credential_kind: "none"|"bearer_token"|"cookie_jar"|"app_token"`, `discover() -> list[DiscoveredAccount]`, `authenticate(options) -> dict|None`, `discover_options(credential) -> dict`.
- `UsageMethod` (`base.py:74`): `required_credential_kind`, abstract `fetch(account, credential) -> ProviderFetchResult`.
- `FallbackUsageMethod` (`base.py:90`): tries each method's `fetch()` in order, catching `ProviderError` only (not arbitrary exceptions) and returning the first success; its own `required_credential_kind` is taken from `methods[0]`.
- `Provider` (`base.py:121`): `service`, `key`, `display_name`, `configuration_fields`, `login_url`, `login_hint`, `icon: IconRef|None`, `usage_method`, `login_methods` tuple, `matching_login_methods()` filters login methods by `credential_kind == required_credential_kind`, abstract `user_identity(account, result) -> str`.
- `ProviderFetchResult` (`src/ai_usage/models.py:105`): `service, provider, account_id, fetched_at, status, metrics: list[Metric], error, identity: AccountIdentity|None, subscription: SubscriptionStatus|None, raw_payload: dict[str, Any]|None, notes: list[str]`.
- `Metric.usage` is `Usage(percentage)` or `MinMaxUsage(current, maximum, unit)` (discriminated union). Both are viable for the fixed-window providers here.
- Registry (`registry.py`): flat `built_in_registry()` list of provider instances + `entry_points(group="ai_usage.providers")`.
- `capture_cookies_via_webview(url, title, click_selector=None) -> dict[str,str]` (`src/ai_usage/webview_login.py:93`) is synchronous/blocking, must be called from `LoginMethod.authenticate()` directly (not via `asyncio.to_thread`), navigates via `webview.create_window`, snapshots cookies on same-domain loads, detects "logged in" by domain-leave-and-return or path change off the initial path. It already spoofs a Safari UA and sets `private_mode=False` for WAF/localStorage compat.
- Existing `CookieCaptureLogin` classes (Claude, Codex) are ~20-30 line thin wrappers: `key`, `display_name`, `credential_kind = "cookie_jar"`, optional `login_url`/`login_button_selector`/`login_hint`, `authenticate()` just calls `capture_cookies_via_webview(...)` and returns `{"cookies": cookies} if cookies else None`. Claude's also implements `discover_options()` to auto-fill `org_id` via a follow-up API call.
- HTTP pattern for Cloudflare-fronted vendors: `curl_cffi.requests.AsyncSession(impersonate="chrome", cookies=..., headers=..., base_url=..., timeout=20)`; `get_json()`/`describe_fetch_failure()` helpers in `claude/usage/web/private_api.py:25-58` label 401/403 as "session likely expired" with a `reauth_hint`. This pattern (or a shared version of it) should be reused for Cursor's web path.
- CLI login flow (`cli.py` lines ~605-620, 686-745, ~810-845) is plain `click.echo` (no rich/Console anywhere in the codebase) and calls `login_method.authenticate(dynamic_options)` awaited directly inside the async CLI command — so a device-flow `authenticate()` can `click.echo()` the `user_code`/`verification_uri` and then `await asyncio.sleep()`-poll in a loop; no CLI restructuring is needed, this is a good fit as-is.
- No PKCE, device-flow, or HTML-scraping code exists anywhere in the repo today — all three are genuine firsts. No `bs4`/`lxml`/`selectolax` dependency exists (checked `pyproject.toml`); only `httpx`, `curl-cffi`, `pydantic`, `sqlalchemy`, etc. are present.
- There is no `providers/_shared/` directory yet — closest existing analogue is per-provider `_shared.py` (e.g. `claude/_shared.py`). A new cross-provider `providers/_shared/` package should be created for the two OAuth helpers since they're used by two unrelated providers (xAI, Moonshot) and don't belong under either's namespace.
- Tests: no per-file test layout — a single `tests/test_providers.py` (34KB) covers parsers/logic for all providers via `respx` (for httpx) or a hand-rolled `FakeCurlResponse`/fake `AsyncSession` (curl_cffi has no transport-mock hook, confirmed in file header). New provider parsing logic should follow this same single-file convention (or add `tests/test_provider_cursor.py` etc. if preferred — matches no strict existing per-provider split, either works, but staying in `test_providers.py` matches current convention most closely).

---

## Shared OAuth helper 1: PKCE + local-loopback-listener (for SuperGrok)

**New file:** `src/ai_usage/providers/_shared/__init__.py` (new package) and `src/ai_usage/providers/_shared/oauth_pkce.py`.

Public API:

```python
@dataclass(frozen=True)
class PkceExchange:
    access_token: str
    refresh_token: str | None
    id_token: str | None
    expires_in: int | None
    raw: dict[str, Any]

async def run_pkce_login(
    *,
    authorization_endpoint: str,
    token_endpoint: str,
    client_id: str,
    redirect_uri: str,          # must be http://127.0.0.1:<port>/<path>
    scopes: Sequence[str],
    extra_authorize_params: dict[str, str] | None = None,
    callback_timeout: float = 300.0,
) -> PkceExchange:
    """Blocking-until-complete: opens the system browser to the authorize URL (via
    `webbrowser.open`), starts a short-lived `http.server.HTTPServer` bound to the
    redirect_uri's host:port/path to catch `?code=...&state=...`, verifies `state`,
    exchanges the code (with `code_verifier`) for tokens via POST to `token_endpoint`
    (httpx.AsyncClient — xAI's endpoint is not Cloudflare-fronted per requirements),
    and returns them. Raises ProviderError on timeout, state mismatch, or non-2xx
    token response."""
```

Internals:
- `code_verifier`: `secrets.token_urlsafe(64)` (trimmed/regenerated to RFC 7636's 43-128 char charset if needed).
- `code_challenge = base64url(sha256(code_verifier))`, `code_challenge_method=S256`.
- `state`: `secrets.token_urlsafe(16)`.
- Local server: run `http.server.HTTPServer` in a background thread (`threading.Thread(daemon=True)`), a custom `BaseHTTPRequestHandler` that parses the query string off `self.path`, stashes `(code, state)` into a `queue.Queue()` or a mutable dict guarded by a lock, writes a minimal "you can close this tab" HTML response, then the main coroutine does `await asyncio.wait_for(asyncio.to_thread(queue.get), timeout=callback_timeout)` — this is the async-friendly way to bridge the synchronous `http.server` blocking accept-loop into the running event loop without needing `asyncio.start_server` (keeps the same "we're not on the main GUI thread" caution as `webview_login.py`, but here there's no GTK/webview constraint, so plain threading is fine).
- `webbrowser.open(authorize_url)` opens the *system* default browser (not pywebview) — this is a deliberate difference from cookie-jar logins: it needs a full OAuth authorize+consent+redirect round trip a webview's stripped-down window may mishandle for popup-based IdP flows, and xAI's `auth.x.ai` is a full OAuth AS, not a bespoke SPA.
- Token exchange: `httpx.AsyncClient().post(token_endpoint, data={"grant_type":"authorization_code","code":code,"redirect_uri":redirect_uri,"client_id":client_id,"code_verifier":code_verifier})`.
- Port binding: fixed port from `redirect_uri` (56121 for xAI) — if the port is already in use, `HTTPServer()` raises `OSError`; the helper should catch and re-raise as `ProviderError` with a clear "port 56121 already in use — is another instance of ai-usage (or another PKCE login) already running?" message. This is a real, flagged risk (see Risks section).

### SuperGrok (xAI) provider — thin wrapper preferred

**New directory:** `src/ai_usage/providers/supergrok/`
```
supergrok/__init__.py
supergrok/provider.py
supergrok/login/__init__.py
supergrok/login/web/__init__.py
supergrok/login/web/pkce_login.py      # thin wrapper around _shared/oauth_pkce.py
supergrok/usage/__init__.py
supergrok/usage/web/__init__.py
supergrok/usage/web/billing_api.py
```

`pkce_login.py`:
```python
class PkceLogin(LoginMethod):
    key = "oauth-pkce"
    display_name = "Sign in via browser (xAI OAuth)"
    credential_kind = "bearer_token"

    async def authenticate(self, options):
        del options
        exchange = await run_pkce_login(
            authorization_endpoint="https://auth.x.ai/oauth2/authorize",
            token_endpoint="https://auth.x.ai/oauth2/token",
            client_id="b1a00492-073a-47ea-816f-4c329264a828",
            redirect_uri="http://127.0.0.1:56121/callback",
            scopes=["openid","profile","email","offline_access","grok-cli:access","api:access"],
        )
        return {"token": exchange.access_token, "refresh_token": exchange.refresh_token}
```
This is a genuine thin wrapper — no xAI-specific PKCE logic beyond the constants, matching the "thin wrapper preferred" guidance.

`usage/web/billing_api.py` — `BillingApiUsage(UsageMethod)`, `required_credential_kind = "bearer_token"`:
- `httpx.AsyncClient` (not curl_cffi — `cli-chat-proxy.grok.com` is a plain API host per spec, no Cloudflare-fronting mentioned).
- `GET https://cli-chat-proxy.grok.com/v1/billing?format=credits` with headers `Authorization: Bearer <token>`, `X-XAI-Token-Auth: xai-grok-cli`.
- Best-effort `GET .../settings` for plan display name (wrapped in try/except like Claude's `/api/account` best-effort calls).
- Manual parsing (root may be `{config:{...}}` or `{billing:{config:{...}}}`): write a small `def extract_billing_config(payload: dict) -> dict` that does `payload.get("billing", payload).get("config", {})` and normalizes both shapes into one dict before building `Metric`s — do NOT use a strict pydantic model here since the root shape is genuinely ambiguous per the spec; fall back to raw dict `.get()` walks (mirrors the `windows is None` fallback branch pattern in `parse_claude_web_usage`).
- Build `Usage(percentage=...)` or `MinMaxUsage(current=used_credits, maximum=total_credits, unit="credits")` depending on what `config` actually contains (need to verify exact field names against a live response — flagged as an open question below, since the spec only gives the two possible root shapes, not the leaf field names).

`provider.py`:
```python
class SuperGrokBillingProvider(Provider):
    service = "supergrok"
    key = "web"
    display_name = "SuperGrok (xAI) billing"
    login_url = "https://auth.x.ai/oauth2/authorize"
    usage_method = BillingApiUsage()
    login_methods = (PkceLogin(),)

    def user_identity(self, account, result):
        # xAI's billing/settings response likely has no email; fall back to account_id or
        # a settings-derived display name if discovered — needs live-response confirmation.
        ...
```

**registry.py diff:** import `SuperGrokBillingProvider` from `ai_usage.providers.supergrok.provider`; add to the `built_in_registry()` tuple.

---

## Shared OAuth helper 2: Device Authorization Flow (RFC 8628) (for Kimi)

**New file:** `src/ai_usage/providers/_shared/oauth_device_flow.py`.

Public API:
```python
@dataclass(frozen=True)
class DeviceFlowTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    raw: dict[str, Any]

async def run_device_flow_login(
    *,
    device_authorization_endpoint: str,
    token_endpoint: str,
    client_id: str,
    scope: str | None = None,
    display_prompt: Callable[[str, str], None] = _default_click_echo_prompt,
    poll_timeout: float = 600.0,
) -> DeviceFlowTokens:
    """POST client_id(+scope) to device_authorization_endpoint; call display_prompt(user_code,
    verification_uri) once (default impl does `click.echo(f"Go to {verification_uri} and enter
    code {user_code}")` plus `webbrowser.open(verification_uri_complete or verification_uri)`);
    then poll token_endpoint on `interval` seconds (RFC 8628 grant_type
    urn:ietf:params:oauth:grant-type:device_code) until success/expired_token/timeout, honoring
    `authorization_pending` (keep polling) and `slow_down` (increase interval +5s per spec).
    Raises ProviderError on expired_token/access_denied/timeout."""
```

- `display_prompt` is injectable specifically so `_shared` doesn't hard-depend on `click` (keeps it usable from tests / non-CLI contexts) — default implementation lives in the same module and uses `click.echo`, matching the CLI's existing plain-echo style (confirmed no rich/Console usage anywhere in `cli.py`).
- Uses `httpx.AsyncClient` for both the device-authorization POST and the polling POSTs — `auth.kimi.com` isn't described as Cloudflare-fronted.
- Polling loop: `await asyncio.sleep(interval)` between attempts — this fits naturally in the CLI's async flow (`login_method.authenticate()` is `await`ed directly from an async click command per `cli.py:614`/`708`/`818`), no special CLI plumbing needed. The "does the CLI even support this mid-wizard" question is thus answered: yes, structurally, since `authenticate()` is just an arbitrary async coroutine the CLI awaits and lets do console I/O — but see UX risk below.

### Kimi (Moonshot) provider — thin wrapper preferred

**New directory:** `src/ai_usage/providers/kimi/`
```
kimi/__init__.py
kimi/provider.py
kimi/login/__init__.py
kimi/login/web/__init__.py
kimi/login/web/device_flow_login.py     # thin wrapper around _shared/oauth_device_flow.py
kimi/usage/__init__.py
kimi/usage/web/__init__.py
kimi/usage/web/usages_api.py
```

`device_flow_login.py`:
```python
class DeviceFlowLogin(LoginMethod):
    key = "oauth-device-flow"
    display_name = "Sign in via device code (Kimi)"
    credential_kind = "bearer_token"

    async def authenticate(self, options):
        del options
        tokens = await run_device_flow_login(
            device_authorization_endpoint="https://auth.kimi.com/api/oauth/device_authorization",
            token_endpoint="https://auth.kimi.com/api/oauth/token",
            client_id="17e5f671-d194-4dfb-9706-5516cb48c098",
        )
        return {"token": tokens.access_token, "refresh_token": tokens.refresh_token}
```

`usages_api.py` — `UsagesApiUsage(UsageMethod)`, `required_credential_kind = "bearer_token"`:
- `GET https://api.kimi.com/coding/v1/usages` with `Authorization: Bearer <token>` via plain `httpx.AsyncClient`.
- Parse `limits: [{window: {duration, timeUnit}, detail: {limit, remaining, resetTime}}]`. Since `limit`/`remaining` are **strings**, define:
```python
def kimi_session_window(limits: list[dict]) -> dict | None:
    for entry in limits:
        window = entry.get("window") or {}
        if window.get("duration") == 300 and window.get("timeUnit") == "TIME_UNIT_MINUTE":
            return entry
    return limits[0] if limits else None

def kimi_used_amount(detail: dict) -> float:
    limit = float(detail.get("limit", "0") or 0)
    remaining = float(detail.get("remaining", "0") or 0)
    return max(0.0, limit - remaining)
```
- Build one `Metric` per relevant window (at minimum the session window; optionally iterate and emit one `Metric` per entry in `limits`, keyed by `duration`+`timeUnit`, similar to Codex's multi-window `parse_rate_limits`).
- `reset_at = datetime.fromisoformat(detail["resetTime"])` guarded/try-except like other providers' timestamp parsing.
- `identity/subscription`: `user.membership.level` → `SubscriptionStatus(plan_type=...)`.

`provider.py`:
```python
class KimiUsageProvider(Provider):
    service = "kimi"
    key = "web"
    display_name = "Kimi (Moonshot) coding usage"
    login_url = "https://auth.kimi.com/api/oauth/device_authorization"
    usage_method = UsagesApiUsage()
    login_methods = (DeviceFlowLogin(),)

    def user_identity(self, account, result):
        ...  # Kimi's /usages payload doesn't obviously include email; may need to fall back to
             # account_id-derived login, or a best-effort separate profile endpoint (open question)
```

**registry.py diff:** import `KimiUsageProvider`, add to tuple.

---

## Provider 1: Cursor (cookie_jar, `FallbackUsageMethod`)

**Directory:** `src/ai_usage/providers/cursor/`
```
cursor/__init__.py
cursor/provider.py
cursor/login/__init__.py
cursor/login/web/__init__.py
cursor/login/web/cookie_capture.py
cursor/usage/__init__.py
cursor/usage/web/__init__.py
cursor/usage/web/private_api.py     # REST path (cursor.com/api/*)
cursor/usage/web/grpc_json.py       # api2.cursor.sh gRPC-JSON path
```

**Login** (`cookie_capture.py`) — same shape as Claude/Codex's `CookieCaptureLogin` (credential_kind="cookie_jar"), targeting `https://cursor.com/login` (or homepage + `click_selector` if `/login` doesn't render standalone — needs live verification, flagged below). No `discover_options` needed unless Cursor exposes a multi-workspace concept analogous to Claude's org — spec doesn't mention one, so omit for v1.

**Session token parsing helper** (co-located in `usage/web/private_api.py` or a small `cursor/_shared.py`):
```python
def extract_cursor_bearer_token(cookies: dict[str, str]) -> str | None:
    raw = cookies.get("WorkosCursorSessionToken") or cookies.get("cursor_session")  # exact
        # cookie name needs live confirmation — spec says "compound userId::accessToken JWT"
        # but doesn't name the cookie key; treat as an open question, not a guess to hardcode
        # confidently.
    if not raw:
        return None
    decoded = urllib.parse.unquote(raw)
    if "::" in decoded:
        _, _, token = decoded.rpartition("::")
    else:
        token = decoded
    return token if token.startswith("eyJ") else None
```
This matches the requested "URL-decode, split on `::`, take JWT (or whole value if `startswith('eyJ')`)" spec precisely.

**Usage — web path** (`private_api.py`), `required_credential_kind = "cookie_jar"`:
- `curl_cffi.requests.AsyncSession(impersonate="chrome", cookies=cookies, base_url="https://cursor.com")` (cursor.com is plausibly Cloudflare-fronted like claude.ai/chatgpt.com — using curl_cffi defensively per the existing pattern rather than plain httpx).
- `GET /api/usage-summary` (primary), best-effort `GET /api/auth/me`, then `GET /api/usage?user=<id>` using the id from `/api/auth/me` if available.
- Money fields in cents → divide by 100 when building `Metric`/`SubscriptionStatus` (e.g. `MinMaxUsage(current=cents/100, maximum=cents/100, unit="USD")` if usage is dollar-based, or `Usage(percentage=...)` if it's already a ratio — needs confirming against the real payload shape, flagged below).
- Raise `ProviderError` (not swallow) if `/api/usage-summary` itself fails, so `FallbackUsageMethod` moves on to the gRPC path — this is the intended fallback trigger.

**Usage — gRPC-JSON path** (`grpc_json.py`), `required_credential_kind = "cookie_jar"`:
- Extract bearer token from cookies via `extract_cursor_bearer_token`; if `None`, raise `ProviderError` immediately (so this leg also fails cleanly for `FallbackUsageMethod` chaining, though it's already the last method).
- `curl_cffi.requests.AsyncSession(impersonate="chrome", base_url="https://api2.cursor.sh")`, `Authorization: Bearer <jwt>`.
- `POST /aiserver.v1.DashboardService/GetCurrentPeriodUsage` with body `"{}"` (note: literal JSON string `"{}"`, i.e. Connect/gRPC-JSON transcoding style — `content-type: application/json`, body is the empty-message JSON, per spec).
- Best-effort `POST .../GetPlanInfo`, best-effort `GET /auth/full_stripe_profile`.
- Same cents→dollars conversion for money fields.

**Provider wiring** (`provider.py`):
```python
class CursorUsageProvider(Provider):
    service = "cursor"
    key = "web"
    display_name = "Cursor usage"
    login_url = "https://cursor.com/login"
    usage_method = FallbackUsageMethod((PrivateApiUsage(), GrpcJsonUsage()))
    login_methods = (CookieCaptureLogin(),)

    def user_identity(self, account, result):
        return canonical_login(result.identity.email if result.identity else None, self.display_name)
```
Note: `FallbackUsageMethod.required_credential_kind` is taken from `methods[0]` (`base.py:98`) — both Cursor legs use `"cookie_jar"` so this is consistent; unlike Claude's status-provider fallback chain (which mixes credential kinds across CLI methods), Cursor's two legs share one credential kind, which is the simpler/safer case for `FallbackUsageMethod`.

**registry.py diff:** import `CursorUsageProvider`, add to tuple.

---

## Provider 2: Ollama Cloud (cookie_jar, HTML scraping — first in codebase)

**Directory:** `src/ai_usage/providers/ollama/`
```
ollama/__init__.py
ollama/provider.py
ollama/login/__init__.py
ollama/login/web/__init__.py
ollama/login/web/cookie_capture.py
ollama/usage/__init__.py
ollama/usage/web/__init__.py
ollama/usage/web/settings_scrape.py
```

**Login** (`cookie_capture.py`): same `CookieCaptureLogin` shape, `credential_kind="cookie_jar"`, target `https://ollama.com` (or `/signin`, needs live confirmation of the actual login URL/flow), capturing `__Secure-session` (required) and `cf_clearance` (optional secondary, best-effort — don't fail login if absent, just include if present).

**New dependency required:** no HTML parser exists in the project. Recommend `selectolax` (fast, small, no libxml2 system dependency headache, good CSS-selector `.css_first()`/`.css()` API well-suited to "find `<span class='text-sm'>` then walk up to the nearest progress-bar `style` attribute" traversal) over `beautifulsoup4` (heavier, slower) or `lxml` (needs a C toolchain / system libxml2, which conflicts with the project's otherwise pure-Python-wheel-friendly dependency list — curl-cffi and pygobject are the only two existing "heavy" deps, and pygobject is already gated behind the optional `browser` extra). Add `selectolax>=0.3` to `pyproject.toml`'s core `dependencies` list (not an extra, since Ollama's usage *fetch* — not login — needs it, and fetch has no analogous optional-extra precedent in this codebase; login-only deps like `pywebview` are behind `browser` because *login* is optional at fetch time, but here parsing IS the fetch).

**Usage** (`settings_scrape.py`), `required_credential_kind = "cookie_jar"`:
- `httpx.AsyncClient(cookies=cookies)` for `GET https://ollama.com/settings` — spec doesn't mention Cloudflare-fronting for ollama.com's authenticated settings page, so default to plain httpx first; if live testing shows 403s, escalate to curl_cffi `impersonate="chrome"` (flag as an open question/fallback path to verify).
- Parse HTML with `selectolax.parser.HTMLParser(response.text)`.
- Plan extraction (nested `class="capitalize"` span inside an `<h2>` "Cloud Usage" section):
```python
def extract_ollama_plan(tree: HTMLParser) -> str | None:
    for h2 in tree.css("h2"):
        if "cloud usage" in (h2.text() or "").lower():
            section = h2.parent  # walk up to the section wrapping both h2 and the plan span
            span = section.css_first("span.capitalize") if section else None
            return span.text().strip() if span else None
    return None
```
- Usage percentage (progress-bar `style` attr, regex `width:\s*([0-9.]+)%`, walking up from a labeled `<span class="text-sm">`):
```python
WIDTH_PATTERN = re.compile(r"width:\s*([0-9.]+)%")

def extract_ollama_usage_percentage(tree: HTMLParser, label: str) -> float | None:
    for span in tree.css("span.text-sm"):
        if label.lower() not in (span.text() or "").lower():
            continue
        node = span
        for _ in range(6):  # bounded upward walk — avoid unbounded traversal into <body>
            node = node.parent
            if node is None:
                break
            bar = node.css_first("[style*='width']")
            if bar is not None:
                match = WIDTH_PATTERN.search(bar.attributes.get("style") or "")
                if match:
                    return float(match.group(1))
        return None
    return None
```
Called once for `"Session usage"` and once for `"Weekly usage"`.
- Reset time: `[data-time]` attribute holding an ISO instant — `tree.css_first("[data-time]")` (scoped to the relevant usage block, same upward-walk pattern), `datetime.fromisoformat(node.attributes["data-time"])`.
- Build `Metric(usage=Usage(percentage=...), ...)` for session and weekly windows.
- `raw_payload={"html": response.text}` — per the requirement that `ProviderFetchResult.raw_payload` (typed `dict[str, Any] | None`) can hold the raw HTML string same as other providers store raw JSON; this is schema-compatible since the field has no JSON-specific constraint, just `dict[str, Any]`.
- **This is flagged as an architectural first** — every other `UsageMethod.fetch()` in the codebase parses JSON API responses (either via pydantic models with raw-dict fallback, or manual `dict.get()` walks); this is the only one scraping rendered HTML, and CSS-class-based extraction (`capitalize`, `text-sm`) is inherently coupled to a specific frontend build's Tailwind-esque class names, which can change on any ollama.com frontend deploy with zero API-versioning signal. This fragility should be called out explicitly to the user/reviewer, and the parser should raise a clear `ProviderError` ("Ollama settings page layout changed — HTML scraping selectors need updating") rather than silently return zero/empty metrics, so failures are diagnosable rather than misread as "0% usage."

**Provider wiring** (`provider.py`):
```python
class OllamaCloudUsageProvider(Provider):
    service = "ollama"
    key = "web"
    display_name = "Ollama Cloud usage"
    login_url = "https://ollama.com"
    usage_method = SettingsScrapeUsage()
    login_methods = (CookieCaptureLogin(),)

    def user_identity(self, account, result):
        ...  # ollama.com/settings HTML may or may not expose an email/username element;
             # needs live-page confirmation — flagged as open question
```

**registry.py diff:** import `OllamaCloudUsageProvider`, add to tuple.

---

## Cross-cutting files to modify

- `src/ai_usage/providers/registry.py` — add 4 new imports + 4 new entries in `built_in_registry()`'s tuple.
- `pyproject.toml` — add `selectolax>=0.3` (or chosen HTML-parser) to `[project.dependencies]`.
- `tests/test_providers.py` — add parser-level unit tests for: `extract_cursor_bearer_token`, Cursor cents→dollar conversion, `kimi_session_window`/`kimi_used_amount`, Ollama's three extraction functions (with small inline HTML fixtures), xAI's `extract_billing_config` dual-shape normalizer. HTTP-level fetch tests via `respx` (httpx-based legs: Ollama, xAI, Kimi) and the `FakeCurlResponse`/fake-`AsyncSession` pattern (curl_cffi-based legs: Cursor).
- New: `tests/test_oauth_pkce.py` and `tests/test_oauth_device_flow.py` (or folded into `test_providers.py`) — test the loopback-server code-capture and the polling state machine (`authorization_pending`/`slow_down`/`expired_token`) with a fake token endpoint via `respx`, and a fake browser opener (inject a callable instead of really calling `webbrowser.open`/spawning a GUI) so these are pure-async, tty-independent, CI-safe tests, unlike the cookie-jar logins.

---

## Open questions / risks

1. **No-tty verification gap (project memory)**: Cursor's and Ollama's `capture_cookies_via_webview`-based login code cannot be manually smoke-tested in this environment (no tty, no GTK/WebKit display). Per project memory ("Native GUI needs a real run"), this must be verified by the user locally after implementation — mocks/unit tests can cover the cookie/token-parsing logic but not the actual webview lifecycle, click-selector auto-click, or Cloudflare/WAF behavior against the real cursor.com/ollama.com login pages.
2. **HTML-scraping fragility (Ollama)**: CSS-class-driven scraping (`capitalize`, `text-sm`) has no stability contract with ollama.com's frontend; any Tailwind/class-name refactor on their end silently breaks this provider. Recommend the parser fail loudly (raise `ProviderError`) rather than degrade to empty/zero metrics.
3. **Local loopback port 56121 (xAI PKCE)**: If another process (or a stale prior login attempt whose HTTP server didn't cleanly shut down) already holds that port, `HTTPServer()` bind will raise `OSError: [Errno 98] Address already in use`. The helper should catch this and surface a clear, actionable `ProviderError` rather than a raw traceback; consider adding a bind-retry-with-backoff only if `redirect_uri`'s port were configurable, but since xAI's registered `redirect_uri` is fixed to `56121`, the port itself cannot be changed — the only real mitigation is a clear error message plus ensuring the server thread is torn down (`server.shutdown()` + `server.server_close()`) promptly once the callback is received or the timeout fires, so a previous ai-usage run's login doesn't leave the port stuck.
4. **CLI mid-wizard device-flow display**: Confirmed the CLI's `authenticate()` call sites (`cli.py` ~614, ~708, ~818) are plain awaited coroutines inside async click commands with no rich/Console layer, so `click.echo()`-ing the `user_code`/`verification_uri` from inside `authenticate()` works structurally today. Only UX risk: `Provider.login_hint` (static, printed *before* `authenticate()` is even called, per `cli.py:610`/`704`/`814`) can't show the dynamic `user_code` — that must come from *inside* `run_device_flow_login`'s `display_prompt` call, which is fine, but means the "Opening a login window..." static message printed just before will look slightly odd for a device-flow (no window actually opens) — consider whether `Provider.login_hint` should be adjusted to something like "You'll be given a code to enter at a URL" for Kimi to avoid user confusion, or whether the CLI's generic "Opening a login window for..." message needs a device-flow-aware variant (a small CLI change, flagged as a possible scope addition, not strictly required to ship).
5. **Cursor cookie name and payload field names are unconfirmed** — the spec describes the *shape* (`userId::accessToken` JWT, cents-based money fields) but not the exact cookie key or JSON field names for `/api/usage-summary` / `GetCurrentPeriodUsage`. These need to be confirmed against a live authenticated response before finalizing `extract_cursor_bearer_token` and the money-field parsing; document this as a TODO with a fallback of trying a small set of plausible cookie names (`WorkosCursorSessionToken` is the name used by Cursor's desktop app per public community reverse-engineering, but should be verified).
6. **xAI billing/settings and Kimi `/usages` responses' identity fields are unconfirmed** — neither spec explicitly names an email/login field, so `user_identity()` for both `SuperGrokBillingProvider` and `KimiUsageProvider` may need to fall back to a non-email identity (e.g., a stable ID from the token's `id_token` JWT claims, or `account_id`) rather than `canonical_login(email, ...)` as used by Claude/Codex — needs live-response confirmation.
7. **FallbackUsageMethod only catches `ProviderError`** (`base.py:110`) — both Cursor usage legs (and any best-effort sub-calls within them) must consistently raise `ProviderError` (not bare `RuntimeError`/`httpx.HTTPStatusError`) on failure paths that should trigger the REST→gRPC fallback, mirroring how `get_json()` in Claude's private_api wraps HTTP failures into `ProviderError` before propagating.

### Critical Files for Implementation
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/base.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/registry.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/webview_login.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/claude/login/web/cookie_capture.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/claude/usage/web/private_api.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/codex/usage/web/private_api.py
- /home/user/git/luckydonald/ai-usage/pyproject.toml
- /home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py