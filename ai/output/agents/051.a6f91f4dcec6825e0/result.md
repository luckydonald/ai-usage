Now I have everything needed. Here is the implementation plan.

## Implementation Plan: Z.ai, MiniMax, Cline, OpenRouter providers

### Confirmed architecture facts (from reading the real code)

- `LoginMethod.authenticate(options)` is called by the CLI with the full responsibility of *interactively* obtaining a credential — it's fine for it to do blocking prompts itself (`CookieCaptureLogin.authenticate` blocks on a webview; nothing currently does `click.prompt`, but `create_account()` already does `click.prompt(field.label, hide_input=field.kind == "secret")` for plain `configuration_fields`, so the established idiom for "ask the user to type/paste a secret" is a hidden `click.prompt`). There is **no existing manual-paste `LoginMethod`** to copy verbatim — the four new ones need a new, shared class.
- `credential_kind`/`required_credential_kind` must match between `Provider.usage_method` and the `LoginMethod`s wired into `login_methods` (`Provider.matching_login_methods()` filters by exact kind equality). All four new providers fit `credential_kind="bearer_token"` (a bare API key/token dict, no cookies).
- `--secret-json`/`--secret-file` CLI flags bypass `LoginMethod.authenticate()` entirely (`cli.py:600-604`) — useful as an alternative non-interactive path, no extra code needed, it's generic.
- `discover_options()` on the `LoginMethod` (or provider) is the place to auto-fill `configuration_fields` right after obtaining a credential (e.g. Claude's org auto-detect). For Z.ai/Cline/OpenRouter there's nothing to auto-detect. For MiniMax the region is itself picked *before* the key is even entered (it changes which URL to hit), so it must be a `ConfigurationField` prompted via the normal wizard mechanism, not something derivable from the credential.
- `user_identity()` is mandatory (raises `NotImplementedError` → CLI error otherwise) and should return an account login string; for these vendors, use whatever the "me"/subscription payload calls the account (Z.ai: none guaranteed → fall back to using the API key's own account id or a fixed constant + the plan name; MiniMax: `current_subscribe_title`/plan name isn't a login, so use a deterministic placeholder derived from something stable, e.g. hash of key, matching how Copilot's `CodexStatusProvider`/`CopilotEntitlementsProvider` raise `ProviderLoginError` when they truly cannot determine one — **open question**, see risks).
- `GenericPrivateWebUsage` in `copilot/usage/web/entitlements.py` requires `credential_kind="cookie_jar"` (cookies+headers bundle) and is explicitly experimental/single-consumer; it does **not** fit these four providers (which use bare bearer tokens, not cookies) as-is. It's a candidate to generalize later but not a drop-in.
- HTTP client choice: none of these 4 vendor APIs are documented as Cloudflare-fronted, so plain `httpx.AsyncClient` (like Copilot) is the right default; only fall back to `curl_cffi.requests.AsyncSession(impersonate="chrome")` if a provider is later found to 403/challenge with httpx.

### Shared code: `providers/_shared/`

Promote a small shared module (new directory, matches the `entitlements.py` docstring's own suggestion of "or a new `providers/_shared/` module"):

- **`src/ai_usage/providers/_shared/__init__.py`**
- **`src/ai_usage/providers/_shared/static_api_key.py`** — `StaticApiKeyLogin(LoginMethod)`:
  - `key = "paste-api-key"`, `display_name` configurable via constructor, `credential_kind = "bearer_token"`.
  - Constructor takes `display_name: str`, `prompt_label: str = "API key"`, and an optional `validate: Callable[[str], Awaitable[None]] | None` (raises `ProviderLoginError` on invalid key, e.g. calling a lightweight "who am I" endpoint) so each vendor can plug in its own cheap validation call without duplicating the prompt/trim/empty-check logic.
  - `authenticate(options)`: `del options`; `click.prompt(self.prompt_label, hide_input=True)`; strip; raise `ProviderLoginError` if empty; run `validate` if given; return `{"token": key}`.
  - No `discover()` (nothing to auto-detect on disk/env for these 4 — unlike Copilot's env-var reuse). Each provider can still add its own env-var-reuse subclass later without touching this base.
  - This one class is reused, with different constructor args, by all 4 providers' `login/` submodules (one thin `login/local/api_key.py` per provider instantiating it, to keep the per-provider directory shape consistent with the existing convention of one file per concern — or, simpler, each provider's `provider.py` can just instantiate `StaticApiKeyLogin(...)` directly, skipping a per-provider login file since there's no vendor-specific logic to isolate). Recommendation: skip the extra per-provider `login/` file where `StaticApiKeyLogin` needs zero vendor-specific code, and only add a dedicated `login/*.py` file for MiniMax where the region field interacts with authentication (see below).

### 1. Z.ai — `src/ai_usage/providers/zai/`

- `__init__.py`, `provider.py`, `usage/__init__.py`, `usage/web/__init__.py`, `usage/web/private_api.py`.
- **`usage/web/private_api.py`**: `ZaiUsage(UsageMethod)`, `service="zai"`, `key="api"`, `required_credential_kind="bearer_token"`.
  - `fetch()`: `httpx.AsyncClient(base_url="https://api.z.ai", timeout=20)`, header `Authorization: Bearer {token}`.
  - GET `/api/biz/subscription/list` first: if `success is False` and message contains `"coding plan"`/`"不存在"` → raise `ProviderError("no active Z.ai coding plan")` (this is the expected "no plan" signal, not a fetch failure — still surfaces as an error to the user per `ProviderError` semantics elsewhere). If HTTP 401/403 → raise `ProviderError("Z.ai API key is invalid")`. Else pick first/active subscription entry (`productName`, `status`) into `SubscriptionStatus(plan_type=productName, status=status)`.
  - GET `/api/monitor/usage/quota/limit`: parse `data.limits`. Separate `TOKENS_LIMIT` entries, sort by computed period `number * unit_to_ms(unit)` ascending; shortest → `session` metric key, second-shortest → `weekly` metric key (helper `zai_unit_period_ms(unit: int, number: int) -> int` with the mapping `{1:"days",3:"hours",5:"minutes",6:"weeks"}`). `TIME_LIMIT` entries → `web-search` metric. Each metric: `MinMaxUsage(current=currentValue or (number-remaining), maximum=number, unit=unit_label)` (need to confirm which field is "used" — spec gives both `usage` and `currentValue`; use `currentValue` as current, `remaining` cross-checked, prefer whichever is present), `reset_at` from `nextResetTime` (need to confirm epoch ms vs iso — treat as epoch ms like MiniMax's ambiguity, or ISO string; must handle both defensively).
  - Combine both calls' results into one `ProviderFetchResult` (subscription info as `result.subscription`, limits as `result.metrics`); raise `ProviderError` if `metrics` ends up empty.
- **`provider.py`**: `ZaiProvider(Provider)`, `service="zai"`, `key="api"`, `configuration_fields=()` (nothing beyond the key itself — no region/org needed), `usage_method=ZaiUsage()`, `login_methods=(StaticApiKeyLogin(display_name="Sign in with Z.ai API key", prompt_label="Z.ai API key"),)`. `user_identity()`: since there's no username/email in either payload per the spec, use `canonical_login(result.subscription.plan_type if result.subscription else None, ...)` as a *last-resort* pseudo-login, or raise `ProviderLoginError` if truly nothing identifies the account — flagged as an open question below since a single Z.ai API key with no email in these two endpoints can't be told apart from another key on the same plan tier without a third "who am I" call (may need to probe for a `/api/biz/user` or similar profile endpoint not in the spec — recommend checking Z.ai docs before finalizing `user_identity`).

### 2. MiniMax — `src/ai_usage/providers/minimax/`

- `__init__.py`, `provider.py`, `login/local/api_key.py` (region-aware, since region must be picked *before* the key can be validated against the right base URL), `usage/__init__.py`, `usage/web/private_api.py`.
- **`login/local/api_key.py`**: `MiniMaxApiKeyLogin(LoginMethod)` — a MiniMax-specific subclass (not the bare shared one) because `authenticate(options)` needs `options["region"]` to pick the right validation endpoint. `credential_kind="bearer_token"`. `authenticate()`: prompt for key via `click.prompt(hide_input=True)`, then do a lightweight validation GET against the *first* URL of the appropriate region's fallback chain (see below) — but only to catch a typo'd key at add-time; the real fallback-chain logic still belongs in the usage method since it must run on every fetch, not just at login. Returns `{"token": key}`.
- **`provider.py`**: `configuration_fields = (ConfigurationField(key="region", label="Region", required=True, help="global or cn"),)` — plain string field, prompted via the generic `create_account()` `click.prompt` path (no special CLI UI needed, matches instructions that no CLI changes are required). `usage_method=MiniMaxUsage()`.
- **`usage/web/private_api.py`**: `MiniMaxUsage(UsageMethod)`, `required_credential_kind="bearer_token"`.
  - `MINIMAX_ENDPOINTS = {"global": (three URLs...), "cn": (two URLs...)}` built from `account.options["region"]` (casefold, default `"global"`).
  - `fetch()`: iterate the region's URL tuple with `httpx.AsyncClient`, `Authorization: Bearer {token}`; on HTTP 401/403 → raise `ProviderError` immediately (per spec, stop entirely); on non-200 (and not 401/403) or `base_resp.status_code != 0` → try next URL; if all exhausted → raise `ProviderError("MiniMax coding-plan endpoint unavailable in all fallback URLs")`.
  - Parse `model_remains[]`: for each entry, resolve "used"/"remaining" via a priority-ordered field lookup — helper `minimax_pick_field(entry, *names)` returning the first present of `current_interval_usage_count`, then `..._remaining_count`, then `..._remains_count`; if none present, `used = total - remaining` computed from whichever total/remaining pair exists. Helper `minimax_normalize_timestamp(value)`: `value * 1000 if value < 10_000_000_000 else value` (spec's <10B-seconds heuristic) before converting to `datetime`.
  - Build one `Metric` per `model_remains` entry, keyed by a slugified `plan_name`/`plan`/`current_subscribe_title` (whichever is present, in that priority), `MinMaxUsage(current=used, maximum=total, unit="requests")`, `reset_at` from `end_time` (normalized).
- **Open question flagged for the user**: the spec doesn't give a canonical plan-name→display-name table; recommend just titleizing whatever field is present rather than inventing a lookup table, to avoid silently mismapping unseen plan names.

### 3. Cline — `src/ai_usage/providers/cline/`

- `__init__.py`, `provider.py`, `usage/__init__.py`, `usage/web/private_api.py`.
- **`usage/web/private_api.py`**: `ClineUsage(UsageMethod)`, base `https://api.cline.bot/api/v1/`, `httpx.AsyncClient`, `Authorization: Bearer {token}`.
  - Fetch `/users/me`, `/users/balance`, `/users/usages`, `/users/plan/usage-limits` concurrently via `asyncio.gather` with each wrapped so one endpoint's failure doesn't kill the others ("best-effort combine" per spec) — mirrors none of the existing providers exactly (all current usage methods hit exactly one or two endpoints and treat any non-200 as fatal), so this is new: use `asyncio.gather(*, return_exceptions=True)` and only raise `ProviderError` if **all four** fail; otherwise build whatever `Metric`s the successful responses support (balance → `MinMaxUsage`/`Usage` percentage if a limit exists, else raw balance as a metric with no maximum; usages → per-model or per-period metrics if the payload has an array; usage-limits → the authoritative max, cross-referenced against balance for `current`).
  - `identity = AccountIdentity(...)` from `/users/me` (email/name field, exact key TBD from live response — flagged as open question, no schema given in spec beyond endpoint URLs).
- **`provider.py`**: `login_methods=(StaticApiKeyLogin(display_name="Sign in with Cline API key"),)`.

### 4. OpenRouter — `src/ai_usage/providers/openrouter/`

- `__init__.py`, `provider.py`, `usage/__init__.py`, `usage/web/private_api.py`.
- **`usage/web/private_api.py`**: `OpenRouterUsage(UsageMethod)`, base `https://openrouter.ai/`, `Authorization: Bearer {provisioning_key}`.
  - GET `/api/v1/credits` (or `/api/v1/auth/key` as fallback if `/credits` 404s — try `/credits` first since it directly names the concept and matches the `{data:{...}}` envelope pattern OpenRouter uses elsewhere): parse `data.total_credits` / `data.total_usage` (typical OpenRouter credits shape) into `MinMaxUsage(current=total_usage, maximum=total_credits, unit="USD")`. If instead only `/auth/key` shape (`data.limit`, `data.usage`, `data.limit_remaining`) is available, use `limit`/`usage` the same way.
  - **This endpoint shape is not confirmed against current OpenRouter docs in this read-only pass** — flagged explicitly below as the top risk item; recommend a quick live-doc check or a manual `curl` against `https://openrouter.ai/api/v1/credits` with a real key before writing the parser, since the two candidate shapes (`credits` vs `auth/key`) have different field names and this determines the whole parsing function.
- **`provider.py`**: `login_methods=(StaticApiKeyLogin(display_name="Sign in with OpenRouter provisioning key", prompt_label="OpenRouter provisioning key"),)`.

### Registry wiring — `src/ai_usage/providers/registry.py` diff

```python
from ai_usage.providers.zai.provider import ZaiProvider
from ai_usage.providers.minimax.provider import MiniMaxProvider
from ai_usage.providers.cline.provider import ClineProvider
from ai_usage.providers.openrouter.provider import OpenRouterProvider
...
def built_in_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in (
        CodexAppServerProvider(),
        CodexStatusProvider(),
        ClaudeStatusProvider(),
        ClaudeUsageProvider(),
        CopilotBillingProvider(),
        CopilotStatusProvider(),
        CodexWebUsageProvider(),
        ClaudeWebUsageProvider(),
        CopilotEntitlementsProvider(),
        ZaiProvider(),
        MiniMaxProvider(),
        ClineProvider(),
        OpenRouterProvider(),
    ):
        registry.register(provider)
```

No `cli.py` changes needed — the generic wizard (`select_provider`, `resolve_login_method`, `run_provider_add_wizard`, `create_account`) already drives any `Provider` with `login_methods` + `configuration_fields` populated correctly, including MiniMax's plain `region` field via the existing `click.prompt` fallback in `create_account()`.

### Tests

Add to `tests/test_providers.py` (or new `tests/test_zai.py` etc. if preferred — existing convention is one flat `test_providers.py` covering all vendors plus per-vendor helper unit tests like `test_billing_reset_clamps_short_month`) using the existing `respx`/`FakeCurlSession` patterns already in that file for httpx-mocked endpoint tests, one test per: successful fetch/parse, no-plan/empty-subscription case (Z.ai), region fallback chain exhaustion + 401 short-circuit (MiniMax), partial-endpoint-failure best-effort combine (Cline), and whichever OpenRouter shape gets confirmed.

### Risks / open questions

1. **OpenRouter endpoint shape is unconfirmed** — biggest risk; `/api/v1/credits` vs `/api/v1/auth/key` have different field names (`total_credits/total_usage` vs `limit/usage/limit_remaining`); needs a live check before implementation, not something to guess from training data alone.
2. **Z.ai `user_identity()`** — neither given endpoint returns an email/username; may need an undocumented third endpoint, or the provider may have to raise `ProviderLoginError` (like `CopilotEntitlementsProvider`/`CodexStatusProvider` do) if no stable identity is derivable, which would make Z.ai's `provider add` wizard fail at the `verify_provider_setup` step — needs product decision.
3. **MiniMax plan-name-from-limit heuristic** — spec gives no canonical table mapping `plan`/`plan_name`/`current_subscribe_title` values to a display taxonomy; recommend just using whichever field is present verbatim rather than a lookup table that will go stale.
4. **Z.ai `nextResetTime` / MiniMax `end_time` unit ambiguity** — need defensive parsing (try ISO-8601 string, fall back to epoch ms/seconds heuristic) since the spec doesn't pin down the exact representation per field.
5. **Cline "best-effort combine of 4 endpoints"** is a new pattern not seen elsewhere in the codebase (existing usage methods are single- or dual-endpoint, all-or-nothing); the `asyncio.gather(..., return_exceptions=True)` partial-success approach should be reviewed against how `ProviderFetchResult.notes`/`status` are meant to communicate partial degradation (check `FetchStatus` enum values beyond `SUCCESS`/`ERROR` before deciding whether partial-success should be `SUCCESS` with a `notes` entry, or a distinct status).
6. **`GenericPrivateWebUsage` reuse** — does not fit any of these 4 as-is (wrong `credential_kind`); do not force-fit it, but its dotted-path-percentage extraction idea could inspire a *new*, bearer-token-flavored generic helper in `_shared/` if a 5th similar provider shows up later.

### Critical Files for Implementation
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/base.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/registry.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/copilot/login/cli/token_reuse.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/providers/copilot/usage/web/billing_api.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/models.py
- /home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py