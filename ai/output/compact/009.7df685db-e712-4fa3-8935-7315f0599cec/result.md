<analysis>
Chronological review:

1. User invoked `/plan` with request to restructure `providers/` into login/usage packages. I explored via Explore agents, drafted plan, iterated per user feedback (drop back-compat, add usage-as-identity/login-as-pluggable design, add provider-add wizard design), got plan approved, then implemented via 3 parallel general-purpose agents (claude/codex/copilot subpackages), fixed remaining test regressions, ran full suite, committed via lplp style as `da98173`.

2. User then ran `/plan` again with args "build new `provider add`" — a continuation, scoped just to the wizard piece not yet done. I ran an Explore agent to get exact code of the relevant cli.py functions, provider_tui.py, provider_discovery.py, base.py, and per-provider provider.py files. Received exhaustive verbatim results.

3. I first wrote a full context-heavy plan (repeating already-done work). User rejected ExitPlanMode and said: "just new chages for build new `provider add`" — explicit feedback to trim the plan to only the new/remaining work, not repeat completed context. I rewrote the plan file to be lean, scoped only to the wizard changes. User approved via ExitPlanMode.

4. I began implementation: read cli.py lines 140-319 (credential_payload, create_account, verify_provider_setup) to prepare edits.

5. Then a system message arrived instructing me to STOP and produce ONLY a summary, no tool calls. This is the current turn — I must not call tools, just summarize.

Key technical state to preserve:
- Base abstractions already added to providers/base.py: LoginMethod, UsageMethod, FallbackUsageMethod, Provider (composition root with usage_method + login_methods, matching_login_methods() filtering by credential_kind).
- All three provider subpackages (claude, codex, copilot) restructured and committed.
- registry.py, tests updated and committed.
- Commit hash da98173 already made (message: "[backend] providers: ai: Run: Split provider login/usage into separate composable modules").
- Current task: implement the plan now at /home/user/.claude/plans/merry-purring-wozniak.md (rewritten, scoped only to wizard). This plan was approved by user via ExitPlanMode.
- I need to now implement: select_provider(), resolve_login_method(), rewrite select_discovered_account, wire into provider_add/run_provider_add_wizard/provider_login, update print_discovery_choices grouping.
- I had just read cli.py lines 140-319 as the last action before being told to stop and summarize — I have NOT yet made any edits for this second plan (wizard). No code changes yet for this phase.
- Must remember commit-with-lplp-style skill was activated earlier in session (skill invocation) — future commits should follow that style: write message to ai/git/pending-commit.md, `rm ai/git/pending-commit.md || echo 'was gone'` first, then `git commit -F ai/git/pending-commit.md`, stage only touched files explicitly (no git add -A/.), commit after every completed task.
- Caveman mode is active (full) throughout — terse style, but code/commits/PRs written normally per the caveman rules.
- No security-sensitive constraints beyond normal repo hygiene (never git add -A, review staged files, no secrets).

I need to capture exact plan file content (final version) since that's the authoritative source of truth for next steps, and exact line numbers/functions in cli.py that need editing, plus the exact code just read (lines 140-319) since that's the most immediate context.

Let me also capture the full picture of the base.py, provider.py files per-provider tables (login_methods, credential_kind, usage_method.required_credential_kind) gathered from the Explore agent, since these are essential for implementing resolve_login_method and select_provider correctly.

Also must capture provider_tui.py and provider_discovery.py contents (small, already quoted in full by the explore agent) since the plan explicitly reuses these unchanged.

Also note: the Explore agent's report also included exact cli.py line ranges for: credential_payload 144-152, create_account 155-273, verify_provider_setup 276-303, print_discovery_choices 392-413, discover_or_error 416-426, select_discovered_account 429-469, provider_add 472-622, provider_discover 625-640, provider_login 643-707, run_provider_add_wizard 750-783, run_first_crawl_wizard 786-817, ensure_ready_to_crawl 820-833. I have NOT yet read the actual body text of select_discovered_account/provider_add/provider_login/run_provider_add_wizard functions myself via Read tool (the Explore agent read them and reported "verbatim" but oddly the report said "reproduced in full at the start of this response" yet the tool result shown to me only contained the tables and file dumps for provider_tui.py, provider_discovery.py, base.py, and the three provider.py files — the actual cli.py function bodies text seems to have been truncated/not shown in what I received). I should note this gap: I have exact line numbers but NOT the exact verbatim code for select_discovered_account/provider_add/provider_login/run_provider_add_wizard/run_first_crawl_wizard/ensure_ready_to_crawl/print_discovery_choices/discover_or_error — I will need to Read those directly from cli.py when resuming.

I have read cli.py lines 140-319 directly myself (via Read tool), which covers: credential_payload, create_account, verify_provider_setup. I do NOT yet have direct reads of lines 320-833 (print_discovery_choices onward through ensure_ready_to_crawl) — need to Read those next.

Now write the summary.
</analysis>

<summary>
1. Primary Request and Intent:
   - Original request: restructure `src/ai_usage/providers/` (parser files) into well-separated packages per concern: `providers/<provider>/login/<type>/<method>.py` (e.g. `providers/codex/login/local/auth_json.py`) and `providers/<provider>/usage/<type>/<method>.py` (e.g. `providers/copilot/usage/cli/statusline.py`). Types: `local`, `cli`, `api`, `user_input`, `web`, etc. Split all current providers into this shape; create base classes for a common interface if possible.
   - User clarified during planning: login is one of *several* alternative ways to acquire a token/credential for the *same* API call — login and usage (the actual API-calling "provider") are decoupled concerns. The usage/crawler side is the unique identity per account (one usage/API parser per online account), login is auxiliary and in principle swappable (though the user called full swappability across providers "probably unrealistic" / "bonus points").
   - User explicitly said: "I don't think we need the `__init__` import compat... we control all imports... shape is generally something we can freely change... We should not try to keep legacy stuff around." → No backward-compatibility shims; every import site is in-repo and can be updated directly.
   - User explicitly asked to also plan out the new `ai-usage provider add` wizard flow (pick provider → pick category/usage-method → determine credential need → pick login source if multiple exist) so the login/usage split isn't done twice, and because it "aims in reducing legacy adapter code."
   - After the structural refactor plan was approved and implemented (see below), user invoked `/plan` again with args "build new `provider add`" — asking to plan (and then presumably implement) the CLI wizard rewrite specifically, as a follow-up/continuation task.
   - Critical user feedback during this second planning pass: after I wrote a plan that repeated already-completed context, user rejected `ExitPlanMode` and said verbatim: **"just new chages for build new `provider add`"** — meaning the plan file should contain *only* the new/remaining work (the wizard), not restate the already-done and already-committed login/usage split. I rewrote the plan accordingly (see Files section) and the user approved it via `ExitPlanMode`.
   - Current explicit task: implement the approved wizard-rewrite plan in `cli.py`.

2. Key Technical Concepts:
   - `Provider` composition pattern: `Provider` = `usage_method: UsageMethod` (registry identity, keyed by `service`+`key`) + `login_methods: tuple[LoginMethod, ...]` (auxiliary, filtered by `credential_kind`/`required_credential_kind` matching).
   - `LoginMethod(ABC)`: `key`, `display_name`, `credential_kind: CredentialKind` (`"none"|"bearer_token"|"cookie_jar"|"app_token"`), `discover()`, `authenticate(options)`, `discover_options(credential)`.
   - `UsageMethod(ABC)`: `required_credential_kind`, abstract `fetch(account, credential)`.
   - `FallbackUsageMethod(UsageMethod)`: tries an ordered tuple of `UsageMethod`s, catching `ProviderError`, used for Claude statusline's relay-file → direct-CLI → PTY-interactive fallback chain.
   - `Provider.matching_login_methods()`: filters `login_methods` by `credential_kind == required_credential_kind`; `Provider.discover/authenticate/discover_options` delegate to `matching_login_methods()[0]` only (no multi-choice today).
   - lplp commit style (skill `commit-with-lplp-style`, activated this session): commit after every completed task; write message to `ai/git/pending-commit.md` (after `rm ai/git/pending-commit.md || echo 'was gone'`), commit with `git commit -F ai/git/pending-commit.md`; message format `[where] component-or-topic: ai: Run: <summary>.` + body; stage explicit file paths only, never `git add -A`/`.`; fold known auto-commit patterns (`ai: updated prompt`, `ai: save decision`, `ai: agent ... results`, `ai: record memory`, plan-saves) into the preceding code commit by default, but never rewrite already-committed history without asking first.
   - Caveman mode (full) active throughout — terse responses; code/commits/security explanations written normally.
   - Plan-mode workflow: Explore agents for read-only research, plan file at `/home/user/.claude/plans/merry-purring-wozniak.md`, `ExitPlanMode` for approval, `AskUserQuestion` for clarifying choices only (not approval).
   - Textual-based TUI: `provider_tui.py`'s `select_choice(title, choices) -> str | None` and `SelectionChoice(key, label, detail="")` — the only "prompt library" in the project; reused, no new dependency.
   - `ai-usage` CLI (`cli.py`) built with `typer`/`click`.

3. Files and Code Sections:

   - **`/home/user/git/luckydonald/ai-usage/src/ai_usage/providers/base.py`** (edited, committed) — now 187 lines. Final content (as reconfirmed by the Explore agent's full read):
     ```python
     """Provider interface and discovery contracts."""

     from abc import ABC, abstractmethod
     from typing import Any, Literal

     from pydantic import BaseModel

     from ai_usage.icons import IconRef
     from ai_usage.models import AccountConfig, ProviderFetchResult


     class ProviderError(RuntimeError):
         pass
     # end class


     class ProviderLoginError(ProviderError):
         pass
     # end class


     def canonical_login(value: object, provider_name: str) -> str:
         if not isinstance(value, str) or not (login := value.strip()):
             raise ProviderLoginError(f"{provider_name} could not determine the account login")
         # end if
         return login.casefold()
     # end def


     class ConfigurationField(BaseModel):
         key: str
         label: str
         kind: Literal["string", "integer", "boolean", "secret", "path"] = "string"
         required: bool = False
         default: Any = None
         help: str = ""
     # end class


     class DiscoveredAccount(BaseModel):
         name: str
         options: dict[str, Any]
         credential: dict[str, Any] | None = None
     # end class


     CredentialKind = Literal["none", "bearer_token", "cookie_jar", "app_token"]


     class LoginMethod(ABC):
         """One way to obtain or discover a credential usable by a `UsageMethod`."""

         key: str
         display_name: str
         credential_kind: CredentialKind = "none"

         async def discover(self) -> list[DiscoveredAccount]:
             return []
         # end def

         async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
             del options
             raise ProviderLoginError(f"{self.display_name} does not support interactive login")
         # end def

         async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
             """Best-effort auto-fill for `configuration_fields` using an already-obtained credential."""
             del credential
             return {}
         # end def
     # end class


     class UsageMethod(ABC):
         """One way to fetch usage data given a resolved credential."""

         required_credential_kind: CredentialKind = "none"

         @abstractmethod
         async def fetch(
             self,
             account: AccountConfig,
             credential: dict[str, Any] | None,
         ) -> ProviderFetchResult:
             raise NotImplementedError
         # end def
     # end class


     class FallbackUsageMethod(UsageMethod):
         """Tries each `UsageMethod` in order, returning the first successful result."""

         def __init__(self, methods: tuple[UsageMethod, ...]):
             if not methods:
                 raise ValueError("FallbackUsageMethod requires at least one method")
             # end if
             self.methods = methods
             self.required_credential_kind = methods[0].required_credential_kind
         # end def

         async def fetch(
             self,
             account: AccountConfig,
             credential: dict[str, Any] | None,
         ) -> ProviderFetchResult:
             last_error: Exception | None = None
             for method in self.methods:
                 try:
                     return await method.fetch(account, credential)
                 except ProviderError as e:
                     last_error = e
                     continue
                 # end try
             # end for
             assert last_error is not None
             raise last_error
         # end def
     # end class


     class Provider(ABC):
         """Composition root: pairs a `UsageMethod` (the registry identity) with the
         `LoginMethod`s that can supply it a credential."""

         service: str
         key: str
         display_name: str
         experimental: bool = False
         configuration_fields: tuple[ConfigurationField, ...] = ()
         login_url: str | None = None
         login_hint: str | None = None
         icon: IconRef | None = None

         usage_method: UsageMethod
         login_methods: tuple[LoginMethod, ...] = ()

         @property
         def required_credential_kind(self) -> CredentialKind:
             return self.usage_method.required_credential_kind
         # end def

         def matching_login_methods(self) -> tuple[LoginMethod, ...]:
             return tuple(
                 method for method in self.login_methods
                 if method.credential_kind == self.required_credential_kind
             )
         # end def

         async def discover(self) -> list[DiscoveredAccount]:
             accounts: list[DiscoveredAccount] = []
             for method in self.matching_login_methods():
                 accounts.extend(await method.discover())
             # end for
             return accounts
         # end def

         async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
             methods = self.matching_login_methods()
             if not methods:
                 return None
             # end if
             return await methods[0].authenticate(options)
         # end def

         async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
             """Best-effort auto-fill for `configuration_fields` using an already-obtained credential."""
             methods = self.matching_login_methods()
             if not methods:
                 return {}
             # end if
             return await methods[0].discover_options(credential)
         # end def

         def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
             """Return the canonical login that identifies this provider configuration's real account."""
             del account, result
             raise NotImplementedError
         # end def

         async def fetch(
             self,
             account: AccountConfig,
             credential: dict[str, Any] | None,
         ) -> ProviderFetchResult:
             return await self.usage_method.fetch(account, credential)
         # end def
     # end class
     ```
     Important: `Provider.login_url`/`login_hint` are still Provider-level class attributes, duplicated in spirit by each `LoginMethod`'s own `login_url`/`login_hint`/`login_button_selector` (used internally by that method's own `authenticate()`). This duplication is intentionally left unresolved per the new plan (out of scope).

   - **`src/ai_usage/providers/claude/provider.py`** (new, committed) — assembles `ClaudeWebUsageProvider` (service=`claude`,key=`web`, `usage_method=PrivateApiUsage()`, `login_methods=(CookieCaptureLogin(),)`), `ClaudeStatusProvider` (key=`statusline`, `usage_method=FallbackUsageMethod((RelayFileUsage(), DirectCliUsage(), InteractiveCliUsage()))`, `login_methods=(SettingsFileLogin(),)`), `ClaudeUsageProvider(ClaudeStatusProvider)` (key=`cli-usage`, `usage_method=FallbackUsageMethod((DirectCliUsage(), InteractiveCliUsage()))`, overrides `fetch()` to strip `relay_file` option).

   - **`src/ai_usage/providers/codex/provider.py`** (new, committed) — `CodexWebUsageProvider` (key=`web`, `login_url="https://chatgpt.com/"`, `login_hint='Click "Log in" once the page loads.'`, `usage_method=PrivateApiUsage()`, `login_methods=(CookieCaptureLogin(),)` where that `CookieCaptureLogin` has `key="web-cookie-capture"`, `credential_kind="cookie_jar"`), `CodexAppServerProvider` (key=`app-server`, `usage_method=AppServerUsage()`, `login_methods=(AuthJsonLogin(),)` — `AuthJsonLogin.key="local-auth-json"`, `credential_kind="app_token"`; temp `auth.json` write for manually-supplied credentials intentionally kept inside `AppServerUsage.fetch`, not moved to login, because its lifetime must bracket the `AppServerClient` subprocess), `CodexStatusProvider` (key=`cli-status`, `usage_method=StatusPtyUsage()`, `login_methods=()`, `required_credential_kind="none"`).

   - **`src/ai_usage/providers/copilot/provider.py`** (new, committed) — `CopilotBillingProvider` (key=`github-api`, `login_methods=()`, credential supplied externally via flag/manual entry, `usage_method=BillingApiUsage()` → `required_credential_kind="bearer_token"`), `CopilotStatusProvider` (key=`statusline`, `usage_method=QuotaApiUsage()`, `login_methods=(TokenReuseLogin(),)` — `TokenReuseLogin.key="cli-token-reuse"`, `display_name="Reuse Copilot CLI session"`, `credential_kind="bearer_token"`; merges what used to be `CopilotStatusProvider.discover()` + inline `copilot_cli_credentials()` call inside `fetch()`), `CopilotEntitlementsProvider` (key=`entitlements`, `experimental=True`, `usage_method=GenericPrivateWebUsage(service=service, key=key)` → `required_credential_kind="cookie_jar"`, `login_methods=()`).

   - **`src/ai_usage/providers/registry.py`** (edited, committed) — imports now `from ai_usage.providers.claude import (ClaudeStatusProvider, ClaudeUsageProvider, ClaudeWebUsageProvider)` (claude package kept old names via its `__init__.py` re-export, since `cli.py`/`registry.py` were "off-limits" to the claude-splitting subagent at that time), `from ai_usage.providers.codex.provider import (...)`, `from ai_usage.providers.copilot.provider import (...)`. `built_in_registry()` order unchanged (verified identical to original `mane` order): `CodexAppServerProvider, CodexStatusProvider, ClaudeStatusProvider, ClaudeUsageProvider, CopilotBillingProvider, CopilotStatusProvider, CodexWebUsageProvider, ClaudeWebUsageProvider, CopilotEntitlementsProvider`.

   - **Deleted files** (committed): `providers/claude_cli.py`, `providers/claude_direct.py`, `providers/claude_interactive.py`, `providers/claude/api.py`, `providers/claude/status.py`, `providers/codex.py`, `providers/copilot.py`, `providers/web.py`.

   - **`tests/test_providers.py`** (edited) — import lines updated per-package; one behavioral fix made directly by me: `test_copilot_status_provider_fetch` changed from `result = await CopilotStatusProvider().fetch(account, None)` to:
     ```python
     token, login = copilot_cli_credentials(tmp_path)
     result = await CopilotStatusProvider().fetch(account, {"token": token, "login": login})
     ```
     (needed because credential resolution moved out of `fetch()` into `TokenReuseLogin`; `copilot_cli_credentials` already imported at top of file from `ai_usage.providers.copilot.login.cli.token_reuse`). Confirmed passing: `uv run pytest tests/test_providers.py -q` → 48 passed.

   - **`tests/test_provider_commands.py`** (edited by me directly, after subagents left some monkeypatch targets stale) — ran:
     ```bash
     sed -i \
       -e 's/ai_usage\.providers\.codex\.CodexWebUsageProvider/ai_usage.providers.codex.provider.CodexWebUsageProvider/g' \
       -e 's/ai_usage\.providers\.copilot\.CopilotBillingProvider/ai_usage.providers.copilot.provider.CopilotBillingProvider/g' \
       -e 's/ai_usage\.providers\.claude\.api\.capture_cookies_via_webview/ai_usage.providers.claude.login.web.cookie_capture.capture_cookies_via_webview/g' \
       tests/test_provider_commands.py
     ```
     Result: `uv run pytest tests/test_provider_commands.py -q` → 26 passed.

   - **Full suite result after refactor**: `uv run pytest tests/ -q` → 168 passed, 5 failed — all 5 confirmed **pre-existing** (identical failures reproduced on unmodified `mane` via `git stash -u`): `tests/test_api.py::test_api_catalog_latest_and_series` (icon dict keyed only by `provider.key` collides between `claude/statusline` "gauge" icon and `copilot/statusline` "github" icon — pre-existing bug, unrelated to refactor, in `src/ai_usage/api.py:130-134`: `provider_icons = {provider.key: provider.icon._asdict() for provider in state.providers.providers.values() if provider.icon is not None}`), and 4 in `tests/test_progress.py` (`test_fetch_and_crawl_report_progress`, `test_stale_result_is_not_treated_as_a_crawl_failure`, `test_crawler_records_and_reports_note_transitions_only_on_change`, `test_fetch_persists_identity_subscription_and_raw_payload`).

   - **Commit made**: `git commit -F ai/git/pending-commit.md` after staging explicit file list (no `git add -A`). Message:
     ```
     [backend] providers: ai: Run: Split provider login/usage into separate composable modules:

     Restructured `src/ai_usage/providers/` so login (how a credential is obtained) and usage (how the metrics API/CLI is actually called) are independent, composable objects instead of being tangled inside one `Provider` subclass per service.

     - Added `LoginMethod`/`UsageMethod`/`FallbackUsageMethod` to `providers/base.py`. `Provider` is now a thin composition root: `usage_method` (the registry identity, keyed by `service`/`key`) plus `login_methods` (matched by `credential_kind`/`required_credential_kind`).
     - Split `claude.py`/`claude_cli.py`/`claude_direct.py`/`claude_interactive.py`/`claude/api.py`/`claude/status.py` into `providers/claude/{login,usage}/<type>/<method>.py` + `provider.py`. Claude statusline's relay-file to direct-CLI to PTY-interactive fallback chain is now a `FallbackUsageMethod`.
     - Split `codex.py` into `providers/codex/{login,usage}/<type>/<method>.py` + `provider.py`. Kept the Codex app-server temp `auth.json` write scoped inside its `UsageMethod.fetch` (not moved to login) since its lifetime must bracket the app-server subprocess, not the login step.
     - Split `copilot.py` + `web.py` into `providers/copilot/{login,usage}/<type>/<method>.py` + `provider.py`. Copilot's `copilot_cli_credentials()` token lookup moved out of `fetch()` into `TokenReuseLogin`, so usage methods only ever receive an already-resolved credential.
     - Deleted the old flat modules once fully migrated; updated `registry.py` and test imports accordingly.
     - Fixed `tests/test_provider_commands.py` monkeypatch targets to the new module paths, and `tests/test_providers.py`'s Copilot fetch test to resolve a credential via the new login helper before calling `fetch`.
     - Full suite: 168 passed, only 5 pre-existing failures untouched by this change (confirmed identical on `mane` before this work: `test_api_catalog_latest_and_series` icon-key collision, 4 `test_progress.py` cases).

     Follow-up not done here: the `ai-usage provider add` wizard itself (chained service to usage-method to login-method prompts in `cli.py`) — only its import paths were fixed since existing tests didn't require the new prompt flow. The `credential_kind`/`required_credential_kind` metadata is in place for that follow-up.
     ```
     Committed as `da98173` on branch `mane`.

   - **`/home/user/.claude/plans/merry-purring-wozniak.md`** — rewritten (this is the current, approved, in-force plan) to be scoped *only* to the wizard follow-up (per explicit user feedback "just new chages for build new `provider add`"). Full final content:
     ```markdown
     # `provider add` wizard: service → usage-method → login-method

     ## Context

     Login/usage `Provider` split already landed (commit `da98173`). Left: `cli.py`'s add/login flow still picks a provider as one flat `service/key: display_name` list and always silently uses `matching_login_methods()[0]`. Rework it to chain: pick service → pick usage-method → resolve login-method (prompt only if >1 candidate).

     ## Changes

     ### 1. `select_provider(registry) -> Provider | None` (new helper in `cli.py`)

     1. `services = sorted({impl.service for impl in registry.providers.values()})` → `select_choice("Choose a provider", [SelectionChoice(s, s) for s in services])`. `None` → return `None`.
     2. `candidates = matching_providers(registry, service=chosen_service)`. If exactly one, auto-select it (no prompt). Else `select_choice("Choose how to fetch usage", [SelectionChoice(p.key, f"{p.display_name}{' [experimental]' if p.experimental else ''}") for p in candidates])`. `None` → return `None`.
     3. Return `registry.get(chosen_service, chosen_key)`.

     ### 2. `select_discovered_account` (cli.py:429-469) rewrite

     - If `service is None or provider_key is None`: call `select_provider(registry)` first; cancel propagates. Set `service, provider_key` from the result.
     - Then `discover_or_error(registry, service, provider_key)` — always scoped to the one resolved provider now (previously sometimes broad).
     - If discovered accounts exist: `select_choice("Choose an account to add", ...)` + trailing "Configure manually" entry (provider already fixed, no longer "…other provider").
     - If none discovered: skip straight to manual, no empty prompt.
     - When `service`/`provider_key` came in as CLI args, behavior is unchanged (no new prompts).

     ### 3. `resolve_login_method(provider) -> LoginMethod | None` (new helper)

     ```python
     async def resolve_login_method(provider: Provider) -> LoginMethod | None:
         matching = provider.matching_login_methods()
         if len(matching) <= 1:
             return matching[0] if matching else None
         choices = [SelectionChoice(m.key, m.display_name) for m in matching]
         key = await select_choice("Choose how to sign in", choices)
         return next((m for m in matching if m.key == key), None) if key else None
     ```

     Wire into every credential-resolution call site: `provider_add`'s `execute()` (~562-587), `run_provider_add_wizard` (750-783), `provider_login` (~659). When a method is resolved, call `method.authenticate(...)`/`method.discover_options(...)` directly (not the `Provider`-level delegators, which only ever reach `matching_login_methods()[0]`). When `resolve_login_method` returns `None` (0 matches, e.g. Copilot billing's externally-supplied credential), fall through to the existing `--secret-json`/`--secret-file`/manual-prompt path unchanged.

     Every built-in provider today has 0 or 1 matching login methods, so this is a no-op prompt-wise right now — it's the seam for a provider that later ships ≥2 alternatives per `credential_kind`, not speculative dead code (it's on the hot path of every add/login call).

     ### 4. `print_discovery_choices` (cli.py:392-413) — group by service

     Change the flat `{service}/{key}: {display_name}` listing to grouped-by-service (sort `matching_providers(registry)` by `(service, key)`, group with `itertools.groupby` or a plain dict):
     ```
     Manual provider adapters:
       claude:
         web: Claude private web API
         statusline: Claude status line with /usage fallback
       codex:
         ...
     ```

     ### Not touched

     `verify_provider_setup`, `create_account`, `provider_discovery.py` (`discover_accounts`/`matching_providers`/`exclude_discovered`/`DiscoveryChoice`), all `Provider`/`LoginMethod`/`UsageMethod` classes, `AccountConfig`. Pure `cli.py` orchestration change (plus maybe a small dataclass in `provider_tui.py`/`cli.py` if `select_discovered_account`'s new return shape needs one — decide during implementation). The `login_url`/`login_hint` duplication between `Provider` and each `LoginMethod` stays as-is, out of scope.

     ## Implementation steps

     1. Add `select_provider` and `resolve_login_method` to `cli.py`.
     2. Rewrite `select_discovered_account` per section 2.
     3. Wire `resolve_login_method` into `provider_add`, `run_provider_add_wizard`, `provider_login`.
     4. Update `print_discovery_choices` grouping per section 4.
     5. `uv run pytest tests/test_provider_commands.py tests/test_provider_discovery.py -q`; fix tests asserting the old flat "Manual provider adapters:" text or old single-prompt flow.
     6. Manually exercise `ai-usage provider add` for a no-login provider (`codex cli-status`) and a cookie-login provider (`codex web`): confirm the two new prompts (service, usage-method) appear before account/manual selection, and that `provider add codex app-server ...` given positionally still skips both prompts.

     ## Verification

     - `uv run pytest tests/ -q` — expect the same pre-existing 5 failures as before this whole effort (`test_api_catalog_latest_and_series`, 4× `test_progress.py`), zero new failures.
     - Manual run of `ai-usage provider add` (interactive) confirming chained prompts; `--no-input`/flag-only invocations stay non-interactive.
     ```
     User approved this plan via `ExitPlanMode`.

   - **`src/ai_usage/provider_tui.py`** (read only, unchanged, whole file — 64 lines): defines `SelectionChoice` (frozen dataclass: `key: str, label: str, detail: str = ""`), `SelectionApp(App[str|None])` (Textual modal, Escape → `self.exit(None)`), and `async def select_choice(title, choices) -> str | None` (returns `None` immediately if `choices` is empty, line 59-61).

   - **`src/ai_usage/provider_discovery.py`** (read only, unchanged, whole file — 119 lines): `DiscoveryChoice` (frozen dataclass: `service, provider, provider_name, account: DiscoveredAccount`, `.fingerprint` and `.label` properties), `DiscoveryFailure` (`service, provider, error`), `discovery_fingerprint(service, provider, options)`, `matching_providers(registry, service=None, provider=None) -> list[Provider]` (sorted by `(service, key)`), `exclude_discovered(implementations, choices)`, `async discover_accounts(registry, service=None, provider=None) -> tuple[list[DiscoveryChoice], list[DiscoveryFailure]]` (calls `implementation.discover()` per matching `Provider`, catches exceptions into `DiscoveryFailure`). Important: `discover_accounts` operates at the `Provider` level (merging all matching `LoginMethod.discover()` results), so `DiscoveryChoice` today has no way to know which specific `LoginMethod` produced a discovered account.

   - **`src/ai_usage/cli.py`** — the file to be edited next. Confirmed exact line ranges (from Explore agent, cross-checked): `credential_payload` 144-152, `create_account` 155-273, `verify_provider_setup` 276-303, `print_discovery_choices` 392-413, `discover_or_error` 416-426, `select_discovered_account` 429-469, `provider_add` command 472-622 (decorator 472-474, signature 475-492, body 493-622), `provider_discover` 625-640, `provider_login` 643-707, `run_provider_add_wizard` 750-783, `run_first_crawl_wizard` 786-817, `ensure_ready_to_crawl` 820-833.
     I personally re-read lines 140-319 directly via the `Read` tool (not just via the Explore agent's report) immediately before this summary was requested — full verbatim content:
     ```python
     140	    return parsed
     141	# end def
     142	
     143	
     144	def credential_payload(secret_json: str | None, secret_file: Path | None) -> str | None:
     145	    if secret_json and secret_file:
     146	        raise click.UsageError("use either --secret-json or --secret-file, not both")
     147	    # end if
     148	    if secret_file:
     149	        return secret_file.read_text(encoding="utf-8")
     150	    # end if
     151	    return secret_json
     152	# end def
     153	
     154	
     155	async def create_account(
     156	    runtime: Runtime,
     157	    service: str,
     158	    provider_key: str,
     159	    name: str | None,
     160	    credential: dict[str, Any] | None,
     161	    no_input: bool,
     162	    dynamic_options: dict[str, Any],
     163	    discovered: DiscoveryChoice | None = None,
     164	    login: str | None = None,
     165	) -> tuple[AccountConfig, Literal["added", "existing", "restored"]]:
     166	    provider = runtime.providers.get(service, provider_key)
     167	    options = dict(discovered.account.options) if discovered else {}
     168	    options.update(dynamic_options)
     169	    for field in provider.configuration_fields:
     170	        if field.key not in options and field.default is not None:
     171	            options[field.key] = field.default
     172	        # end if
     173	        if field.key not in options and field.required:
     174	            if no_input:
     175	                raise click.UsageError(f"missing required option --{field.key.replace('_', '-')}")
     176	            # end if
     177	            options[field.key] = click.prompt(field.label, hide_input=field.kind == "secret")
     178	        # end if
     179	        if field.kind == "integer" and field.key in options:
     180	            options[field.key] = int(options[field.key])
     181	        elif field.kind == "boolean" and field.key in options:
     182	            options[field.key] = str(options[field.key]).casefold() in {"1", "true", "yes", "on"}
     183	        # end if
     184	    # end for
     185	    if service == "claude" and provider_key in {"statusline", "cli-usage"}:
     186	        profile_dir = options.get("profile_dir")
     187	        options["profile_dir"] = canonical_claude_profile_dir(
     188	            str(profile_dir) if profile_dir else None
     189	        )
     190	    # end if
     191	    fingerprint = discovered.fingerprint if discovered else None
     192	    existing = (
     193	        runtime.config.find_discovered_account(
     194	            service,
     195	            provider_key,
     196	            fingerprint,
     197	            discovered.account.options,
     198	        )
     199	        if fingerprint and discovered
     200	        else None
     201	    )
     202	    if existing and existing.removed_at is None:
     203	        if existing.discovery_fingerprint is None:
     204	            existing = existing.model_copy(update={"discovery_fingerprint": fingerprint})
     205	            runtime.config.save_account(existing)
     206	        # end if
     207	        return existing, "existing"
     208	    # end if
     209	    account_name = name or (discovered.account.name if discovered else provider.display_name)
     210	    if login is not None:
     211	        candidate = AccountConfig(
     212	            id="pending",
     213	            service=service,
     214	            provider=provider_key,
     215	            name=account_name,
     216	            login=login,
     217	            options=options,
     218	        )
     219	        duplicates = [
     220	            account
     221	            for account in runtime.config.list_accounts(False)
     222	            if account.id != (existing.id if existing else None)
     223	            and account.login is not None
     224	            and configuration_key(account) == configuration_key(candidate)
     225	        ]
     226	        if duplicates:
     227	            raise click.ClickException(
     228	                "a configuration already exists for this service, account, organization, and parser: "
     229	                + ", ".join(account.id for account in duplicates)
     230	            )
     231	        # end if
     232	    # end if
     233	    credential_id: str | None = None
     234	    if credential:
     235	        credential_id = await runtime.database.put_credential(provider_key, account_name, credential)
     236	    # end if
     237	    if existing:
     238	        account = existing.model_copy(
     239	            update={
     240	                "name": account_name,
     241	                "enabled": True,
     242	                "removed_at": None,
     243	                "credential_id": credential_id,
     244	                "options": options,
     245	                "discovery_fingerprint": fingerprint,
     246	            }
     247	        )
     248	        runtime.config.save_account(account)
     249	        action: Literal["added", "existing", "restored"] = "restored"
     250	    else:
     251	        account = runtime.config.create_account(
     252	            service,
     253	            provider_key,
     254	            account_name,
     255	            credential_id,
     256	            options,
     257	            discovery_fingerprint=fingerprint,
     258	        )
     259	        action = "added"
     260	    # end if
     261	    if account.service == "claude" and account.provider == "statusline":
     262	        account.options.setdefault(
     263	            "relay_file", str(runtime.paths.local / "relay" / f"{account.id}.json")
     264	        )
     265	        runtime.config.save_account(account)
     266	        install_status_relay(account, runtime.paths.local)
     267	    # end if
     268	    if login is not None and account.login != login:
     269	        account = account.model_copy(update={"login": login})
     270	        runtime.config.save_account(account)
     271	    # end if
     272	    return account, action
     273	# end def
     274	
     275	
     276	async def verify_provider_setup(
     277	    provider: Provider,
     278	    account: AccountConfig,
     279	    credential: dict[str, Any] | None,
     280	) -> tuple[ProviderFetchResult, str]:
     281	    try:
     282	        result = await provider.fetch(account, credential)
     283	    except ProviderError as exception:
     284	        raise click.ClickException(
     285	            f"{provider.display_name} setup fetch failed: {exception}"
     286	        ) from exception
     287	    # end try
     288	    if result.status == FetchStatus.ERROR:
     289	        raise click.ClickException(
     290	            f"{provider.display_name} setup fetch failed: {result.error}"
     291	        )
     292	    # end if
     293	    try:
     294	        login = provider.user_identity(account, result)
     295	    except NotImplementedError as exception:
     296	        raise click.ClickException(
     297	            f"{provider.display_name} does not implement account-login discovery"
     298	        ) from exception
     299	    except ProviderError as exception:
     300	        raise click.ClickException(str(exception)) from exception
     301	    # end try
     302	    return result, login
     303	# end def
     304	
     305	
     306	LOG_LEVELS = ("debug", "info", "warning", "error", "critical")


     309	def configure_logging(log_level: str) -> None:
     310	    # force=True: without it, basicConfig is a no-op whenever the root logger already has a
     311	    # handler (e.g. under pytest, or if something else configured logging first), silently
     312	    # dropping --log-level.
     313	    logging.basicConfig(
     314	        level=log_level.upper(),
     315	        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
     316	        stream=sys.stderr,
     317	        force=True,
     318	    )
     319	# end def
     ```
     I have **not yet** directly `Read` lines 320-833 of `cli.py` myself (covering `print_discovery_choices`, `discover_or_error`, `select_discovered_account`, `provider_add`, `provider_discover`, `provider_login`, `run_provider_add_wizard`, `run_first_crawl_wizard`, `ensure_ready_to_crawl`) — this is the next thing needed before making edits, since the Explore agent's report gave line numbers and cross-relationships but the actual verbatim code text for these functions was not delivered into my context in the tool result I received (only the tables/summaries and the other files' full text came through).
     Also relevant: `cli.py` imports at top include (from earlier read, lines 1-70): `from ai_usage.provider_discovery import (DiscoveryChoice, DiscoveryFailure, discover_accounts, exclude_discovered, matching_providers)`, `from ai_usage.provider_tui import SelectionChoice, select_choice`, `from ai_usage.providers import Provider, ProviderRegistry, built_in_registry`, `from ai_usage.providers.base import ProviderError`, `from ai_usage.providers.claude import (canonical_claude_profile_dir, install_status_relay, remove_status_relay, write_relay_payload)`.

4. Errors and fixes:
   - **Icon-collision test failure investigation**: `test_api.py::test_api_catalog_latest_and_series` failed asserting `provider_icons["statusline"]["name"] == "gauge"` but got `"github"`. Investigated by checking `built_in_registry()` order (unchanged from original) and then by running `git stash -u` to test against pristine `mane` — confirmed the exact same failure exists on unmodified code, so it's a pre-existing bug (dict keyed only by `provider.key`, colliding between two different services' providers that happen to share the same `key="statusline"`), unrelated to this refactor. Left as-is (out of scope).
   - **`test_progress.py` 4 failures**: same investigation via `git stash -u` — confirmed identical failures pre-exist on `mane` (fake `ChangingProvider` test fixture issues, `identity` field assertion, etc., all unrelated to the `Provider`/`LoginMethod`/`UsageMethod` refactor). Left as-is (out of scope).
   - **`test_providers.py::test_copilot_status_provider_fetch` regression** (real regression from moving credential resolution out of `fetch()`): fixed directly by resolving the credential via `copilot_cli_credentials(tmp_path)` before calling `fetch`, as shown above. Verified fix with `uv run pytest tests/test_providers.py -q` → 48 passed.
   - **Stale monkeypatch string paths in `test_provider_commands.py`** (subagents left `ai_usage.providers.codex.CodexWebUsageProvider`, `ai_usage.providers.copilot.CopilotBillingProvider`, `ai_usage.providers.claude.api.capture_cookies_via_webview` unfixed since they were told not to touch that shared test file outside their own scope): fixed via the `sed` command shown above, mapping to `ai_usage.providers.codex.provider.CodexWebUsageProvider`, `ai_usage.providers.copilot.provider.CopilotBillingProvider`, `ai_usage.providers.claude.login.web.cookie_capture.capture_cookies_via_webview`. Verified with `uv run pytest tests/test_provider_commands.py -q` → 26 passed. (Note: `ai_usage.providers.claude.ClaudeWebUsageProvider` paths did NOT need fixing since `providers/claude/__init__.py` re-exports the old names by design.)
   - **User rejected first draft of the second plan** (the wizard plan) because it repeated all the already-completed/committed structural-refactor context. Feedback: "just new chages for build new `provider add`". Fix: rewrote `/home/user/.claude/plans/merry-purring-wozniak.md` to contain only the new wizard-specific changes (see Files section above for final content), which the user then approved via `ExitPlanMode`.
   - **`ExitPlanMode` was rejected once earlier too** (mid-first-plan, before the "usage is identity, login is pluggable" design point was added) — user interrupted with clarifying feedback about login being one of several ways to get a credential for the same usage/API call; I incorporated that feedback into the plan (added the "Key design point: usage is the identity, login is pluggable" section, added `credential_kind` metadata) before re-attempting `ExitPlanMode`, which succeeded that time. Then user interrupted `ExitPlanMode` a second time asking to also plan the wizard flow — leading to the wizard section being added to plan 1 as well (later fully implemented as part of that same approved plan/commit, except the actual `cli.py` wizard code itself was explicitly deferred/not done, per the commit message's "Follow-up not done here" note) — and that deferred piece is exactly what plan 2 (current) now covers.

5. Problem Solving:
   - Resolved the ambiguity between "renaming for clarity" vs "back-compat" by following the user's explicit instruction: no back-compat shims needed anywhere in this refactor; every internal import site gets updated directly.
   - Resolved the login/usage coupling problem via the `LoginMethod`/`UsageMethod`/`Provider`-composition design, with `credential_kind` as the matching key between the two sides — this design decision is now load-bearing for the second (current) plan's `resolve_login_method` helper.
   - Resolved the "who owns generic HTTP+dotted-path fetch logic" ambiguity for `PrivateWebProvider`/`web.py` by having the copilot-splitting subagent make the call to keep it as `GenericPrivateWebUsage` in `copilot/usage/web/entitlements.py` (not promoted to `providers/base.py`) since it has exactly one consumer today; documented as a deliberate, revisitable choice.
   - Resolved the Codex app-server temp-file credential materialization question (whether it belongs in login-time or usage-time) by keeping it in `AppServerUsage.fetch` (usage side) since its lifetime must bracket the subprocess call, not the login step — documented rationale preserved in code comments/docstring.
   - Ongoing/ahead: the actual `cli.py` implementation of plan 2 (service→usage-method→login-method wizard) has not yet begun beyond reading `credential_payload`/`create_account`/`verify_provider_setup` (lines 140-319) for context. No edits made yet to `cli.py` for this second plan.

6. All user messages (verbatim, non-tool-result turns only):
   - "I want to restructure the parser files, namely everything under @src/ai_usage/providers/ like the following, splitting it in well separated packages with their own concerns: `providers/<provider>/login/<type>/<method>.py` (e.g. `providers/codex/login/local/auth_json.py`), `providers/<provider>/usage/<type>/<method>.py` (e.g. `providers/copilot/usage/cli/statusline.py`). Type would be probably like `local`, `cli`, `api`, `user_input`, `web`, and so on. Adapt if needed. Split all the current providers into those, and feel free to create base classes which support those, if we can find a common interface for that." (via `/plan` command args)
   - "The idea is that there's often multiple ways to 'log in' - to aquire a token needed for an api endpoint. Read a local file might be an alternative to do an login with the browser and capture some specific cookies. This is not technically part of the provider, which would be the same, calling the API in both cases." (answer to an AskUserQuestion about composition vs mixin approach)
   - "Maybe we should plan out both the new `fetch`/crawling, and the new `add`, too, to make sure we don't face insufficiencies there later. And it's needed anyways, and probably aims in reducing legacy adapter code." (rejecting first ExitPlanMode attempt, asking to expand scope of plan 1 to include the wizard design)
   - "I don't think we need the `__init__` import compat, as we control all imports of this project, the shape is generally something we can freely change if beneficial. We should not try to keep legacy stuff around. ; The goal is to also be more flexable in creation workflow (`ai-usage provider add`), possibly first selecting a provider (e.g. claude), then a parser category (cli), then the actual implementation, if there are multiple (e.g. /usage or statusline). Based on this it would now know which logins are availabe for that (here: none needed, cli is logged in). To give an example for that, let's assume that the choice was provider codex → category api → parser web (there could also be the api used by the cli for example). Now we need specific headers for that (probably some `Authentification: Bearer <...>`) for that, which we can retrieve from multiple sources so the selection would ask which auth source (local cli file, interactive browser login, …) and guide you to any required setup steps of that, and later provide the lookup steps for the actual crawl, too. ; So im the end we have the auth side (here: login) and the crawl side (here: usage), which combined make up a specific 'provider' in the old sense. Bonus points if the login could later be switched out with another, but that's probably unrealistic? Still, the unique constraint so to speak is basically on the crawler (usage) side. You should only have one api parser per online account. (but then, there's the whole feature for merging data based on that account login identifier (email/username). ; it's a bit confusing, huh." (rejecting second ExitPlanMode attempt, refining the design)
   - (Implicit approval of plan 1 via ExitPlanMode acceptance — no further text message, just tool result "User has approved your plan.")
   - `/caveman:cavecrew` slash command (loaded a reference skill, no explicit new instruction beyond what's in the skill body)
   - `/caveman:caveman` slash command: "Switch to caveman mode. If no level specified, use full. Respond terse like smart caveman — drop articles, filler, pleasantries. Fragments OK. Technical terms exact. Code unchanged. Pattern: [thing] [action] [reason]. [next step]."
   - `/commit-with-lplp-style` slash command (loaded the lplp commit-style skill, activating it for the session)
   - `/plan` command with args: "build new `provider add`" — starting the second planning pass for the wizard.
   - "just new chages for build new `provider add`" (rejecting the second plan's first draft, demanding it be scoped to only new work, not repeat already-done context)
   - (Implicit approval of the rewritten plan 2 via ExitPlanMode acceptance — tool result "User has approved your plan.")
   - A system/harness message then instructed: "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools... create a detailed summary..." — this is the current turn, not a user content request, but is the operative instruction for this response.

7. Pending Tasks:
   - Implement the approved plan 2 (`/home/user/.claude/plans/merry-purring-wozniak.md`, current content quoted in full above) in `src/ai_usage/cli.py`:
     1. Add `select_provider(registry) -> Provider | None` helper.
     2. Add `resolve_login_method(provider) -> LoginMethod | None` helper.
     3. Rewrite `select_discovered_account` (currently lines ~429-469) per plan section 2.
     4. Wire `resolve_login_method` into `provider_add`'s `execute()` (~562-587), `run_provider_add_wizard` (~750-783), and `provider_login` (~659).
     5. Update `print_discovery_choices` (~392-413) to group the "Manual provider adapters:" listing by service.
     6. Run `uv run pytest tests/test_provider_commands.py tests/test_provider_discovery.py -q`; fix any tests asserting the old flat text or old single-prompt flow.
     7. Manually exercise `ai-usage provider add` for `codex cli-status` (no login) and `codex web` (cookie login) to confirm new prompt chain; confirm `provider add codex app-server ...` (positional args) still skips prompts.
     8. Run full `uv run pytest tests/ -q` and confirm only the same 5 pre-existing failures remain, zero new failures.
     9. Per the active lplp commit-style skill: commit this work as its own commit (new commit, not amending `da98173`) once complete, following the `ai/git/pending-commit.md` → `git commit -F` procedure, staging only the files actually touched.

8. Current Work:
   Immediately before this summary was requested, I was beginning the implementation phase of the approved wizard plan. I had just executed:
   ```
   Read /home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py, offset=140, limit=180
   ```
   which returned lines 140-319 of `cli.py` (verbatim content reproduced in full in section 3 above), covering `credential_payload`, `create_account`, and `verify_provider_setup`. This was preparatory reading to understand the exact code shape before making the planned edits — I had not yet read lines 320+ (which contain `print_discovery_choices`, `discover_or_error`, `select_discovered_account`, `provider_add`, `provider_discover`, `provider_login`, `run_provider_add_wizard`, `run_first_crawl_wizard`, `ensure_ready_to_crawl` — the actual functions the plan requires editing), and had made **zero edits** to `cli.py` for this second plan. No other files were touched in this phase.

9. Optional Next Step:
   Continue reading `src/ai_usage/cli.py` starting around line 320 through at least line 833 (to capture `print_discovery_choices`, `discover_or_error`, `select_discovered_account`, `provider_add`, `provider_discover`, `provider_login`, `run_provider_add_wizard`, `run_first_crawl_wizard`, `ensure_ready_to_crawl` verbatim), then begin implementing the plan's step 1 ("Add `select_provider` and `resolve_login_method` to `cli.py`") followed by step 2 ("Rewrite `select_discovered_account` per section 2") — directly continuing the implementation work that was in progress. This is explicitly the user-approved next task per the plan: *"## Implementation steps: 1. Add `select_provider` and `resolve_login_method` to `cli.py`. 2. Rewrite `select_discovered_account` per section 2. 3. Wire `resolve_login_method` into `provider_add`, `run_provider_add_wizard`, `provider_login`. 4. Update `print_discovery_choices` grouping per section 4. 5. `uv run pytest tests/test_provider_commands.py tests/test_provider_discovery.py -q`..."*
</summary>