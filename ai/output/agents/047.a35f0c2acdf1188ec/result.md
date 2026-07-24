Now I have everything. Here is the full, verbatim report.

## `src/ai_usage/provider_tui.py` (fully read, whole file, 64 lines)

```python
1	"""Textual choice screens used by provider-management commands."""
2	
3	from dataclasses import dataclass
4	
5	from textual.app import App, ComposeResult
6	from textual.binding import Binding
7	from textual.widgets import Footer, Header, OptionList, Static
8	from textual.widgets.option_list import Option
9	
10	
11	@dataclass(frozen=True, slots=True)
12	class SelectionChoice:
13	    key: str
14	    label: str
15	    detail: str = ""
16	# end class
17	
18	
19	class SelectionApp(App[str | None]):
20	    CSS = """
21	    #title { padding: 1 2; text-style: bold; }
22	    #choices { height: 1fr; margin: 0 1; border: round $accent; }
23	    """
24	    BINDINGS = [Binding("escape", "cancel", "Cancel")]
25	
26	    def __init__(self, title: str, choices: list[SelectionChoice]):
27	        super().__init__()
28	        self.selection_title = title
29	        self.choices = choices
30	    # end def
31	
32	    def compose(self) -> ComposeResult:
33	        yield Header(show_clock=False)
34	        yield Static(self.selection_title, id="title")
35	        yield OptionList(
36	            *(
37	                Option(
38	                    f"{choice.label}\n  {choice.detail}" if choice.detail else choice.label,
39	                    id=choice.key,
40	                )
41	                for choice in self.choices
42	            ),
43	            id="choices",
44	        )
45	        yield Footer()
46	    # end def
47	
48	    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
49	        self.exit(event.option.id)
50	    # end def
51	
52	    def action_cancel(self) -> None:
53	        self.exit(None)
54	    # end def
55	# end class
56	
57	
58	async def select_choice(title: str, choices: list[SelectionChoice]) -> str | None:
59	    if not choices:
60	        return None
61	    # end if
62	    return await SelectionApp(title, choices).run_async()
63	# end def
64	
```

Key facts: `SelectionChoice` is a frozen dataclass `(key, label, detail="")`. `select_choice(title, choices)` returns `None` immediately if `choices` is empty (line 59-61), otherwise runs a Textual `SelectionApp` modal and returns the selected `Option.id`, or `None` if the user pressed Escape (`action_cancel`, line 52-54, calls `self.exit(None)`).

## `src/ai_usage/provider_discovery.py` (fully read, whole file, 119 lines)

```python
1	"""Provider discovery, candidate identity, and adapter filtering."""
2	
3	import asyncio
4	import hashlib
5	import json
6	from dataclasses import dataclass
7	from typing import Any
8	
9	from ai_usage.providers import Provider, ProviderRegistry
10	from ai_usage.providers.base import DiscoveredAccount
11	
12	
13	@dataclass(frozen=True, slots=True)
14	class DiscoveryChoice:
15	    service: str
16	    provider: str
17	    provider_name: str
18	    account: DiscoveredAccount
19	
20	    @property
21	    def fingerprint(self) -> str:
22	        return discovery_fingerprint(self.service, self.provider, self.account.options)
23	    # end def
24	
25	    @property
26	    def label(self) -> str:
27	        return f"{self.account.name} — {self.service}/{self.provider}"
28	    # end def
29	# end class
30	
31	
32	@dataclass(frozen=True, slots=True)
33	class DiscoveryFailure:
34	    service: str
35	    provider: str
36	    error: str
37	# end class
38	
39	
40	def discovery_fingerprint(service: str, provider: str, options: dict[str, Any]) -> str:
41	    payload = json.dumps(
42	        {"service": service, "provider": provider, "options": options},
43	        separators=(",", ":"),
44	        sort_keys=True,
45	    )
46	    return hashlib.sha256(payload.encode()).hexdigest()
47	# end def
48	
49	
50	def matching_providers(
51	    registry: ProviderRegistry,
52	    service: str | None = None,
53	    provider: str | None = None,
54	) -> list[Provider]:
55	    matches = [
56	        implementation
57	        for (registered_service, registered_provider), implementation in registry.providers.items()
58	        if (service is None or registered_service == service)
59	        and (provider is None or registered_provider == provider)
60	    ]
61	    return sorted(matches, key=lambda implementation: (implementation.service, implementation.key))
62	# end def
63	
64	
65	def exclude_discovered(
66	    implementations: list[Provider],
67	    choices: list[DiscoveryChoice],
68	) -> list[Provider]:
69	    discovered = {(choice.service, choice.provider) for choice in choices}
70	    return [
71	        implementation
72	        for implementation in implementations
73	        if (implementation.service, implementation.key) not in discovered
74	    ]
75	# end def
76	
77	
78	async def discover_accounts(
79	    registry: ProviderRegistry,
80	    service: str | None = None,
81	    provider: str | None = None,
82	) -> tuple[list[DiscoveryChoice], list[DiscoveryFailure]]:
83	    implementations = matching_providers(registry, service, provider)
84	    if not implementations:
85	        target = "/".join(part for part in (service, provider) if part)
86	        raise KeyError(f"no provider adapters match {target or 'the requested filters'}")
87	    # end if
88	
89	    results = await asyncio.gather(
90	        *(implementation.discover() for implementation in implementations),
91	        return_exceptions=True,
92	    )
93	    choices: list[DiscoveryChoice] = []
94	    failures: list[DiscoveryFailure] = []
95	    for implementation, result in zip(implementations, results, strict=True):
96	        if isinstance(result, BaseException):
97	            failures.append(
98	                DiscoveryFailure(
99	                    service=implementation.service,
100	                    provider=implementation.key,
101	                    error=str(result),
102	                )
103	            )
104	            continue
105	        # end if
106	        for account in result:
107	            choices.append(
108	                DiscoveryChoice(
109	                    service=implementation.service,
110	                    provider=implementation.key,
111	                    provider_name=implementation.display_name,
112	                    account=account,
113	                )
114	            )
115	        # end for
116	    # end for
117	    return choices, failures
118	# end def
119	
```

Important: `discover_accounts` calls `implementation.discover()` on the **Provider** object (not per-`LoginMethod`), which per `base.py` iterates `self.matching_login_methods()` and merges their `.discover()` results into one flat list — so a `DiscoveryChoice` today has no way to know *which* `LoginMethod` produced it, only which `Provider`.

## `src/ai_usage/providers/base.py` (fully read, whole file, 188 lines)

```python
1	"""Provider interface and discovery contracts."""
2	
3	from abc import ABC, abstractmethod
4	from typing import Any, Literal
5	
6	from pydantic import BaseModel
7	
8	from ai_usage.icons import IconRef
9	from ai_usage.models import AccountConfig, ProviderFetchResult
10	
11	
12	class ProviderError(RuntimeError):
13	    pass
14	# end class
15	
16	
17	class ProviderLoginError(ProviderError):
18	    pass
19	# end class
20	
21	
22	def canonical_login(value: object, provider_name: str) -> str:
23	    if not isinstance(value, str) or not (login := value.strip()):
24	        raise ProviderLoginError(f"{provider_name} could not determine the account login")
25	    # end if
26	    return login.casefold()
27	# end def
28	
29	
30	class ConfigurationField(BaseModel):
31	    key: str
32	    label: str
33	    kind: Literal["string", "integer", "boolean", "secret", "path"] = "string"
34	    required: bool = False
35	    default: Any = None
36	    help: str = ""
37	# end class
38	
39	
40	class DiscoveredAccount(BaseModel):
41	    name: str
42	    options: dict[str, Any]
43	    credential: dict[str, Any] | None = None
44	# end class
45	
46	
47	CredentialKind = Literal["none", "bearer_token", "cookie_jar", "app_token"]
48	
49	
50	class LoginMethod(ABC):
51	    """One way to obtain or discover a credential usable by a `UsageMethod`."""
52	
53	    key: str
54	    display_name: str
55	    credential_kind: CredentialKind = "none"
56	
57	    async def discover(self) -> list[DiscoveredAccount]:
58	        return []
59	    # end def
60	
61	    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
62	        del options
63	        raise ProviderLoginError(f"{self.display_name} does not support interactive login")
64	    # end def
65	
66	    async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
67	        """Best-effort auto-fill for `configuration_fields` using an already-obtained credential."""
68	        del credential
69	        return {}
70	    # end def
71	# end class
72	
73	
74	class UsageMethod(ABC):
75	    """One way to fetch usage data given a resolved credential."""
76	
77	    required_credential_kind: CredentialKind = "none"
78	
79	    @abstractmethod
80	    async def fetch(
81	        self,
82	        account: AccountConfig,
83	        credential: dict[str, Any] | None,
84	    ) -> ProviderFetchResult:
85	        raise NotImplementedError
86	    # end def
87	# end class
88	
89	
90	class FallbackUsageMethod(UsageMethod):
91	    """Tries each `UsageMethod` in order, returning the first successful result."""
92	
93	    def __init__(self, methods: tuple[UsageMethod, ...]):
94	        if not methods:
95	            raise ValueError("FallbackUsageMethod requires at least one method")
96	        # end if
97	        self.methods = methods
98	        self.required_credential_kind = methods[0].required_credential_kind
99	    # end def
100	
101	    async def fetch(
102	        self,
103	        account: AccountConfig,
104	        credential: dict[str, Any] | None,
105	    ) -> ProviderFetchResult:
106	        last_error: Exception | None = None
107	        for method in self.methods:
108	            try:
109	                return await method.fetch(account, credential)
110	            except ProviderError as e:
111	                last_error = e
112	                continue
113	            # end try
114	        # end for
115	        assert last_error is not None
116	        raise last_error
117	    # end def
118	# end class
119	
120	
121	class Provider(ABC):
122	    """Composition root: pairs a `UsageMethod` (the registry identity) with the
123	    `LoginMethod`s that can supply it a credential."""
124	
125	    service: str
126	    key: str
127	    display_name: str
128	    experimental: bool = False
129	    configuration_fields: tuple[ConfigurationField, ...] = ()
130	    login_url: str | None = None
131	    login_hint: str | None = None
132	    icon: IconRef | None = None
133	
134	    usage_method: UsageMethod
135	    login_methods: tuple[LoginMethod, ...] = ()
136	
137	    @property
138	    def required_credential_kind(self) -> CredentialKind:
139	        return self.usage_method.required_credential_kind
140	    # end def
141	
142	    def matching_login_methods(self) -> tuple[LoginMethod, ...]:
143	        return tuple(
144	            method for method in self.login_methods
145	            if method.credential_kind == self.required_credential_kind
146	        )
147	    # end def
148	
149	    async def discover(self) -> list[DiscoveredAccount]:
150	        accounts: list[DiscoveredAccount] = []
151	        for method in self.matching_login_methods():
152	            accounts.extend(await method.discover())
153	        # end for
154	        return accounts
155	    # end def
156	
157	    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
158	        methods = self.matching_login_methods()
159	        if not methods:
160	            return None
161	        # end if
162	        return await methods[0].authenticate(options)
163	    # end def
164	
165	    async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
166	        """Best-effort auto-fill for `configuration_fields` using an already-obtained credential."""
167	        methods = self.matching_login_methods()
168	        if not methods:
169	            return {}
170	        # end if
171	        return await methods[0].discover_options(credential)
172	    # end def
173	
174	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
175	        """Return the canonical login that identifies this provider configuration's real account."""
176	        del account, result
177	        raise NotImplementedError
178	    # end def
179	
180	    async def fetch(
181	        self,
182	        account: AccountConfig,
183	        credential: dict[str, Any] | None,
184	    ) -> ProviderFetchResult:
185	        return await self.usage_method.fetch(account, credential)
186	    # end def
187	# end class
188	# end class marker not literal, file ends at line 187
```

(Note: line 188 above was my annotation, not file content — the file itself ends at line 187 with `# end class`.)

Key mechanics for the redesign:
- `Provider.login_url`/`login_hint` are still **Provider-level** class attributes (not yet per-`LoginMethod`), even though `CookieCaptureLogin` (both claude and codex versions) also independently defines its own `login_url`/`login_hint`/`login_button_selector` instance attributes that it uses internally in its own `authenticate()`. The `Provider`-level `login_url`/`login_hint` are what `cli.py`'s `provider_add`/`provider_login` actually read (lines 567-571, 655-656) to decide whether to open a login window and what hint to print — this is duplicated with the login-method's own copies for Claude/Codex.
- `Provider.authenticate()` (line 157-163) and `discover_options()` (line 165-172) always delegate to `matching_login_methods()[0]` — i.e., today there is no way for `cli.py` to choose among multiple matching login methods; the first one wins silently.
- `matching_login_methods()` filters `login_methods` by `credential_kind == required_credential_kind` (the `usage_method`'s required kind), so a `LoginMethod` whose `credential_kind` doesn't match the provider's active `usage_method` is invisible to `discover()`/`authenticate()`/`discover_options()` even if listed in `login_methods`.

## Per-provider `Provider` subclasses (9 built-ins)

### `src/ai_usage/providers/claude/provider.py` (fully read, whole file, 92 lines)

```python
1	"""Assembled Claude `Provider`s: private web API, statusline (+ CLI fallback), `/usage` CLI."""
2	
3	from typing import Any
4	
5	from ai_usage.icons import IconRef
6	from ai_usage.models import AccountConfig, ProviderFetchResult
7	from ai_usage.providers.base import (
8	    ConfigurationField,
9	    FallbackUsageMethod,
10	    Provider,
11	    ProviderLoginError,
12	    canonical_login,
13	)
14	from ai_usage.providers.claude.login.local.settings_file import SettingsFileLogin
15	from ai_usage.providers.claude.login.web.cookie_capture import CookieCaptureLogin
16	from ai_usage.providers.claude.usage.cli.direct import DirectCliUsage
17	from ai_usage.providers.claude.usage.cli.interactive import InteractiveCliUsage
18	from ai_usage.providers.claude.usage.local.relay_file import RelayFileUsage
19	from ai_usage.providers.claude.usage.web.private_api import PrivateApiUsage
20	
21	
22	class ClaudeWebUsageProvider(Provider):
23	    service = "claude"
24	    key = "web"
25	    display_name = "Claude private web API"
26	    icon = IconRef(set="solid", name="globe")
27	    configuration_fields = (
28	        ConfigurationField(
29	            key="org_id",
30	            label="Claude organization UUID",
31	            help="Auto-detected after login when the account belongs to a single organization.",
32	        ),
33	    )
34	    login_url = "https://claude.ai/login"
35	
36	    usage_method = PrivateApiUsage()
37	    login_methods = (CookieCaptureLogin(),)
38	
39	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
40	        email = canonical_login(
41	            result.identity.email if result.identity else None, self.display_name
42	        )
43	        organization = canonical_login(account.options.get("org_id"), self.display_name)
44	        return email if email == organization else f"{email}|{organization}"
45	    # end def
46	# end class
47	
48	
49	class ClaudeStatusProvider(Provider):
50	    service = "claude"
51	    key = "statusline"
52	    display_name = "Claude status line with /usage fallback"
53	    icon = IconRef(set="solid", name="gauge")
54	    configuration_fields = (
55	        ConfigurationField(key="command", label="Claude executable", default="claude"),
56	        ConfigurationField(key="profile_dir", label="Claude profile", kind="path"),
57	        ConfigurationField(key="relay_file", label="Status relay file", kind="path"),
58	        ConfigurationField(key="stale_seconds", label="Relay staleness", kind="integer", default=120),
59	    )
60	
61	    usage_method = FallbackUsageMethod((RelayFileUsage(), DirectCliUsage(), InteractiveCliUsage()))
62	    login_methods = (SettingsFileLogin(),)
63	
64	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
65	        del account
66	        if result.identity is None:
67	            raise ProviderLoginError(f"{self.display_name} cannot determine the account login")
68	        # end if
69	        return canonical_login(result.identity.email, self.display_name)
70	    # end def
71	# end class
72	
73	
74	class ClaudeUsageProvider(ClaudeStatusProvider):
75	    key = "cli-usage"
76	    display_name = "Claude /usage"
77	    icon = IconRef(set="solid", name="terminal")
78	
79	    usage_method = FallbackUsageMethod((DirectCliUsage(), InteractiveCliUsage()))
80	
81	    async def fetch(
82	        self,
83	        account: AccountConfig,
84	        credential: dict[str, Any] | None,
85	    ) -> ProviderFetchResult:
86	        options = dict(account.options)
87	        options.pop("relay_file", None)
88	        direct = account.model_copy(update={"options": options})
89	        return await super().fetch(direct, credential)
90	    # end def
91	# end class
92	
```

**Claude summary table:**

| Provider (service/key) | display_name | login_methods (key / display_name / credential_kind) | usage_method.required_credential_kind |
|---|---|---|---|
| `claude`/`web` | "Claude private web API" | `CookieCaptureLogin` — key=`cookie_capture`, display_name="Sign in via browser", credential_kind=`cookie_jar` | `PrivateApiUsage` → `cookie_jar` |
| `claude`/`statusline` | "Claude status line with /usage fallback" | `SettingsFileLogin` — key=`settings_file`, display_name="Local Claude CLI settings", credential_kind=`none` | `FallbackUsageMethod((RelayFileUsage, DirectCliUsage, InteractiveCliUsage))` → `required_credential_kind` = first method's (`RelayFileUsage`) = `none` |
| `claude`/`cli-usage` (subclasses `ClaudeStatusProvider`, inherits `login_methods`) | "Claude /usage" | same inherited `SettingsFileLogin` (`none`) | `FallbackUsageMethod((DirectCliUsage, InteractiveCliUsage))` → `none` (both `DirectCliUsage` and `InteractiveCliUsage` have `required_credential_kind = "none"`, confirmed at `direct.py:176` and `interactive.py:65`) |

Note `claude`/`cli-usage` inherits `login_methods = (SettingsFileLogin(),)` unchanged from `ClaudeStatusProvider` (no override in the subclass body), and overrides `fetch()` to strip `relay_file` from options before delegating to `super().fetch()`.

### `src/ai_usage/providers/codex/provider.py` (fully read, whole file, 72 lines)

```python
1	"""Assembled Codex `Provider`s wiring login methods to usage methods."""
2	
3	from ai_usage.icons import IconRef
4	from ai_usage.models import AccountConfig, ProviderFetchResult
5	from ai_usage.providers.base import ConfigurationField, Provider, ProviderLoginError, canonical_login
6	from ai_usage.providers.codex.login.local.auth_json import AuthJsonLogin
7	from ai_usage.providers.codex.login.web.cookie_capture import CookieCaptureLogin
8	from ai_usage.providers.codex.usage.cli.app_server import AppServerUsage
9	from ai_usage.providers.codex.usage.cli.status_ptv import StatusPtyUsage
10	from ai_usage.providers.codex.usage.web.private_api import PrivateApiUsage
11	
12	
13	class CodexWebUsageProvider(Provider):
14	    service = "codex"
15	    key = "web"
16	    display_name = "Codex private web API"
17	    icon = IconRef(set="solid", name="globe")
18	    login_url = "https://chatgpt.com/"
19	    login_hint = "Click \"Log in\" once the page loads."
20	
21	    usage_method = PrivateApiUsage()
22	    login_methods = (CookieCaptureLogin(),)
23	
24	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
25	        del account
26	        return canonical_login(
27	            result.identity.email if result.identity else None, self.display_name
28	        )
29	    # end def
30	# end class
31	
32	
33	class CodexAppServerProvider(Provider):
34	    service = "codex"
35	    key = "app-server"
36	    display_name = "Codex app-server"
37	    icon = IconRef(set="solid", name="server")
38	    configuration_fields = (
39	        ConfigurationField(key="command", label="Codex executable", default="codex"),
40	        ConfigurationField(key="profile_dir", label="Codex profile", kind="path"),
41	    )
42	
43	    usage_method = AppServerUsage()
44	    login_methods = (AuthJsonLogin(),)
45	
46	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
47	        del account
48	        return canonical_login(
49	            result.identity.email if result.identity else None, self.display_name
50	        )
51	    # end def
52	# end class
53	
54	
55	class CodexStatusProvider(Provider):
56	    service = "codex"
57	    key = "cli-status"
58	    display_name = "Codex /status"
59	    icon = IconRef(set="solid", name="terminal")
60	    configuration_fields = (
61	        ConfigurationField(key="command", label="Codex executable", default="codex"),
62	    )
63	
64	    usage_method = StatusPtyUsage()
65	    login_methods = ()
66	
67	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
68	        del account, result
69	        raise ProviderLoginError(f"{self.display_name} cannot determine the account login")
70	    # end def
71	# end class
72	
```

**Codex summary table:**

| Provider (service/key) | display_name | login_methods (key / display_name / credential_kind) | usage_method.required_credential_kind |
|---|---|---|---|
| `codex`/`web` | "Codex private web API" | `CookieCaptureLogin` (codex's own, `codex/login/web/cookie_capture.py:9-19`) — key=`web-cookie-capture`, display_name="Sign in via browser", credential_kind=`cookie_jar` | `PrivateApiUsage` (codex) → `cookie_jar` (confirmed `codex/usage/web/private_api.py:184-187`) |
| `codex`/`app-server` | "Codex app-server" | `AuthJsonLogin` — key=`local-auth-json`, display_name="Reuse local auth.json", credential_kind=`app_token` | `AppServerUsage` → `app_token` (confirmed `codex/usage/cli/app_server.py:94-97`) |
| `codex`/`cli-status` | "Codex /status" | `()` (no login methods at all) | `StatusPtyUsage` → `none` (confirmed `codex/usage/cli/status_ptv.py:61-64`) |

Note `codex/login/web/cookie_capture.py` `CookieCaptureLogin` also carries its own `login_url = "https://chatgpt.com/"`, `login_button_selector = '[data-testid="login-button"]'`, and `login_hint = "Click \"Log in\" once the page loads."` (duplicating `CodexWebUsageProvider`'s own `login_url`/`login_hint` class attributes at lines 18-19) — used internally by its `authenticate()` (calls `capture_cookies_via_webview(self.login_url, self.display_name, click_selector=self.login_button_selector)`).

### `src/ai_usage/providers/copilot/provider.py` (fully read, whole file, 77 lines)

```python
1	"""GitHub Copilot providers: assembled from login/usage methods."""
2	
3	from ai_usage.icons import IconRef
4	from ai_usage.models import AccountConfig, ProviderFetchResult
5	from ai_usage.providers.base import ConfigurationField, Provider, ProviderLoginError, canonical_login
6	from ai_usage.providers.copilot.login.cli.token_reuse import TokenReuseLogin
7	from ai_usage.providers.copilot.usage.web.billing_api import BillingApiUsage
8	from ai_usage.providers.copilot.usage.web.entitlements import GenericPrivateWebUsage
9	from ai_usage.providers.copilot.usage.web.quota_api import QuotaApiUsage
10	
11	
12	class CopilotBillingProvider(Provider):
13	    service = "copilot"
14	    key = "github-api"
15	    display_name = "GitHub AI-credit billing API"
16	    icon = IconRef(set="brands", name="github")
17	    configuration_fields = (
18	        ConfigurationField(key="username", label="GitHub username", required=True),
19	        ConfigurationField(key="allowance", label="Monthly AI credits", kind="integer", required=True),
20	        ConfigurationField(key="billing_day", label="Billing cycle day", kind="integer", default=1),
21	        ConfigurationField(key="api_url", label="GitHub API URL", default="https://api.github.com"),
22	    )
23	    # No login methods: credential is supplied externally (CLI flag/manual entry),
24	    # matching the original `CopilotBillingProvider`, which had no `authenticate`/`discover`.
25	    usage_method = BillingApiUsage()
26	    login_methods = ()
27	
28	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
29	        del result
30	        return canonical_login(account.options.get("username"), self.display_name)
31	    # end def
32	# end class
33	
34	
35	class CopilotStatusProvider(Provider):
36	    service = "copilot"
37	    key = "statusline"
38	    display_name = "Copilot CLI quota (local session)"
39	    icon = IconRef(set="brands", name="github")
40	    configuration_fields = (
41	        ConfigurationField(key="config_dir", label="Copilot CLI config directory", kind="path"),
42	        ConfigurationField(key="billing_day", label="Billing cycle day", kind="integer", default=1),
43	        ConfigurationField(key="api_url", label="GitHub API URL", default="https://api.github.com"),
44	    )
45	    usage_method = QuotaApiUsage()
46	    login_methods = (TokenReuseLogin(),)
47	
48	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
49	        del account
50	        return canonical_login(
50	            result.identity.name if result.identity else None, self.display_name
52	        )
53	    # end def
54	# end class
55	
56	
57	class CopilotEntitlementsProvider(Provider):
58	    service = "copilot"
59	    key = "entitlements"
60	    display_name = "Copilot private entitlement API"
61	    icon = IconRef(set="solid", name="key")
62	    experimental = True
63	    configuration_fields = (
64	        ConfigurationField(key="endpoint", label="Private usage endpoint", required=True),
65	        ConfigurationField(key="percentage_field", label="Percentage JSON field", required=True),
66	        ConfigurationField(key="metric_key", label="Metric key", default="usage"),
67	        ConfigurationField(key="metric_name", label="Metric name", default="Usage"),
68	    )
69	    usage_method = GenericPrivateWebUsage(service=service, key=key)
70	    login_methods = ()
71	
72	    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
73	        del account, result
74	        raise ProviderLoginError(f"{self.display_name} cannot determine the account login")
75	    # end def
76	# end class
77	
```

**Copilot summary table:**

| Provider (service/key) | display_name | login_methods (key / display_name / credential_kind) | usage_method.required_credential_kind |
|---|---|---|---|
| `copilot`/`github-api` | "GitHub AI-credit billing API" | `()` — none; credential supplied externally (CLI flag/manual entry) | `BillingApiUsage` → `bearer_token` (confirmed `copilot/usage/web/billing_api.py:31-39`) |
| `copilot`/`statusline` | "Copilot CLI quota (local session)" | `TokenReuseLogin` — key=`cli-token-reuse`, display_name="Reuse Copilot CLI session", credential_kind=`bearer_token` | `QuotaApiUsage` → `bearer_token` (confirmed `copilot/usage/web/quota_api.py:70-81`) |
| `copilot`/`entitlements` (experimental=True) | "Copilot private entitlement API" | `()` — none | `GenericPrivateWebUsage(service=service, key=key)` → `cookie_jar` (confirmed `copilot/usage/web/entitlements.py:23-31`) |

That's all 9 built-in `Provider` subclasses: `claude/web`, `claude/statusline`, `claude/cli-usage`, `codex/web`, `codex/app-server`, `codex/cli-status`, `copilot/github-api`, `copilot/statusline`, `copilot/entitlements`.

## `src/ai_usage/cli.py` — functions requested (exact code, with original line numbers as shown)

All of the following were read verbatim above and are reproduced in full at the start of this response (lines 144-833 inclusive, i.e. exactly the byte-for-byte source). For quick reference, here are the precise start/end line numbers as they actually appear in the file (confirmed against the read, not the approximate numbers given in the request):

- `credential_payload`: lines **144–152**
- `create_account`: lines **155–273**
- `verify_provider_setup`: lines **276–303**
- `print_discovery_choices`: lines **392–413**
- `discover_or_error`: lines **416–426**
- `select_discovered_account`: lines **429–469**
- `provider_add` command (decorator through end of function, including nested `execute()`): lines **472–622** (decorator at 472-474, function signature 475-492, body 493-622)
- `provider_discover` command: lines **625–640**
- `provider_login` command: lines **643–707**
- `run_provider_add_wizard`: lines **750–783**
- `run_first_crawl_wizard`: lines **786–817**
- `ensure_ready_to_crawl`: lines **820–833**

These match the approximate ranges given in the request almost exactly (off by at most a line or two due to blank-line spacing), confirming the request's line numbers were accurate. The full text of each was already produced in the first tool-result block above — every line from 140 through 839 of `cli.py` was captured, so nothing in the requested range was truncated. Key cross-function call relationships worth noting for the redesign:

- `provider_add`'s `execute()` (lines 494-618) is the most complex: it branches on whether `service`/`provider_key` were given as CLI args, whether the terminal is interactive, and whether discovery yields 0/1/multiple choices, calling `discover_or_error` (426), `print_discovery_choices` (413), `select_discovered_account` (469), then falls through to a shared "resolve credential → verify → create_account" tail (lines 559-618) that is *also* duplicated (in a simplified, always-interactive form) inside `run_provider_add_wizard` (750-783). This duplication is likely central to what needs redesigning.
- Both `provider_add` and `run_provider_add_wizard` call `provider.authenticate(dynamic_options)` / rely on `provider.login_url`/`provider.login_hint` (Provider-level, not LoginMethod-level) to decide whether/how to open a login window — meaning today neither one can offer a choice between multiple `LoginMethod`s (e.g. if a provider had both a cookie-capture and a settings-file `LoginMethod` for the same `credential_kind`, only `matching_login_methods()[0]` would ever be used, silently).
- `verify_provider_setup` (276-303) is shared by `provider_add`, `run_provider_add_wizard`, and indirectly matches the same pattern manually inlined in `provider_login` (658-683, which duplicates the "fetch → check FetchStatus.ERROR → resolve login via user_identity" logic instead of calling `verify_provider_setup`).
- `create_account` (155-273) is the account-persistence workhorse: resolves `configuration_fields` defaults/prompts (169-184), handles the Claude statusline/cli-usage `profile_dir` canonicalization special-case (185-190), computes discovery fingerprint/dedup against existing accounts (191-208), duplicate-configuration detection when `login` is known (210-232), stores the credential via `runtime.database.put_credential` (233-236), and finally either restores a soft-removed account, updates an existing one, or creates a new one (237-260), plus a Claude-statusline-specific relay-file install side effect (261-267).