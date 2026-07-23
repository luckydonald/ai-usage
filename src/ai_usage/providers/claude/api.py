"""Claude private web API provider (claude.ai/api/*)."""

import logging
from datetime import UTC, datetime
from typing import Any

from curl_cffi.requests import AsyncSession
from pydantic import BaseModel, ValidationError

from ai_usage.icons import IconRef
from ai_usage.models import (
    AccountConfig,
    AccountIdentity,
    Metric,
    ProviderFetchResult,
    SubscriptionStatus,
    Usage,
)
from ai_usage.providers.base import (
    ConfigurationField,
    Provider,
    ProviderError,
    canonical_login,
)
from ai_usage.webview_login import capture_cookies_via_webview

LOGGER = logging.getLogger(__name__)

AUTH_ERROR_STATUS_CODES = frozenset({401, 403})


def reauth_hint(account_id: str) -> str:
    return f"re-authenticate with: ai-usage provider login --account {account_id}"
# end def


def describe_fetch_failure(exception: Exception, account_id: str) -> str:
    """Append a re-auth hint when an exception looks like an expired/blocked session."""
    response = getattr(exception, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in AUTH_ERROR_STATUS_CODES:
        return f"{exception} — session likely expired or blocked; {reauth_hint(account_id)}"
    # end if
    return str(exception)
# end def


async def get_json(
    client: AsyncSession,
    path: str,
    account_id: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET a Claude endpoint, logging the outgoing request and raising a labeled error on failure."""
    LOGGER.debug("GET %s params=%s", path, params)
    response = await client.get(path, params=params)
    if response.status_code >= 400:
        exception = RuntimeError(f"HTTP Error {response.status_code}")
        exception.response = response
        raise ProviderError(
            f"GET {path} failed: {describe_fetch_failure(exception, account_id)}"
        )
    # end if
    return response.json()
# end def


# The claude.ai web app's promo banner ("Your limits are temporarily boosted...") isn't part
# of any documented API — it's a GrowthBook remote-config feature flag fetched via the web
# app's own bootstrap endpoint. `19186470` is that flag's key (a djb2 hash of its real,
# unpublished name); hardcoded since there's no way to derive or verify it other than by its
# distinctive content (see ai/plans/009_fix-the-chart-s-remount-reanimate-bug-add-a-real-vertical-sl.md
# for how this was found, and why it can't be resolved dynamically).
CLAUDE_WEB_PROMO_FEATURE_KEY = "19186470"


def extract_claude_web_notes(app_start_payload: dict[str, Any]) -> list[str]:
    features = app_start_payload.get("org_growthbook", {}).get("features", {})
    feature = features.get(CLAUDE_WEB_PROMO_FEATURE_KEY)
    if not isinstance(feature, dict):
        return []
    # end if
    default_value = feature.get("defaultValue")
    if not isinstance(default_value, dict):
        return []
    # end if
    text = default_value.get("en-US") or next(iter(default_value.values()), None)
    return [text] if isinstance(text, str) and text else []
# end def


class ClaudeUsageWindowPayload(BaseModel):
    utilization: float | None = None
    resets_at: datetime | None = None
# end class


class ClaudeUsagePayload(BaseModel):
    five_hour: ClaudeUsageWindowPayload | None = None
    seven_day: ClaudeUsageWindowPayload | None = None
# end class


class ClaudeOrganizationPayload(BaseModel):
    uuid: str
    name: str | None = None
    billing_type: str | None = None
# end class


class ClaudeAccountPayload(BaseModel):
    email_address: str | None = None
    full_name: str | None = None
# end class


class ClaudeSubscriptionStatusPayload(BaseModel):
    status: str | None = None
    cancel_at_ts: datetime | None = None
# end class


def parse_claude_web_usage(payload: dict[str, Any], observed_at: datetime) -> list[Metric]:
    try:
        windows = ClaudeUsagePayload.model_validate(payload)
    except ValidationError as exception:
        LOGGER.warning(
            "Claude usage payload did not match the expected schema, falling back to raw "
            "field access: %s",
            exception,
        )
        windows = None
    # end try
    metrics: list[Metric] = []
    for source_key, metric_key, name, seconds in (
        ("five_hour", "five-hours", "Five hours", 5 * 3600),
        ("seven_day", "seven-days", "Seven days", 7 * 86400),
    ):
        try:
            if windows is not None:
                window = getattr(windows, source_key)
                utilization = window.utilization if window else None
                reset_at = window.resets_at if window else None
            else:
                raw_window = payload.get(source_key)
                raw_window = raw_window if isinstance(raw_window, dict) else {}
                utilization = raw_window.get("utilization")
                reset_text = raw_window.get("resets_at")
                reset_at = (
                    datetime.fromisoformat(reset_text) if isinstance(reset_text, str) else None
                )
            # end if
            if not isinstance(utilization, int | float):
                continue
            # end if
            metrics.append(
                Metric(
                    key=metric_key,
                    name=name,
                    usage=Usage(percentage=float(utilization)),
                    observed_at=observed_at,
                    reset_at=reset_at,
                    window_seconds=seconds,
                )
            )
        except (ValueError, TypeError) as exception:
            LOGGER.warning("could not parse Claude %s usage window: %s", source_key, exception)
        # end try
    # end for
    return metrics
# end def


class ClaudeWebUsageProvider(Provider):
    service = "claude"
    key = "web"
    display_name = "Claude private web API"
    icon = IconRef(set="solid", name="globe")
    configuration_fields = (
        ConfigurationField(
            key="org_id",
            label="Claude organization UUID",
            help="Auto-detected after login when the account belongs to a single organization.",
        ),
    )
    login_url = "https://claude.ai/login"

    def user_identity(self, account: AccountConfig, result: ProviderFetchResult) -> str:
        email = canonical_login(
            result.identity.email if result.identity else None, self.display_name
        )
        organization = canonical_login(account.options.get("org_id"), self.display_name)
        return email if email == organization else f"{email}|{organization}"
    # end def

    async def authenticate(self, options: dict[str, Any]) -> dict[str, Any] | None:
        del options
        # pywebview must run on the main thread (it raises WebViewException otherwise), so this
        # is a deliberate synchronous, blocking call rather than `asyncio.to_thread(...)`.
        cookies = capture_cookies_via_webview(self.login_url, self.display_name)
        return {"cookies": cookies} if cookies else None
    # end def

    async def discover_options(self, credential: dict[str, Any] | None) -> dict[str, Any]:
        cookies = (credential or {}).get("cookies") or {}
        if not cookies:
            LOGGER.warning("could not auto-detect Claude organization: no cookies were captured")
            return {}
        # end if
        try:
            # claude.ai sits behind Cloudflare (see CodexWebUsageProvider for the full story) —
            # impersonate a real Chrome TLS fingerprint so cf_clearance is honored.
            async with AsyncSession(
                timeout=20, cookies=cookies, base_url="https://claude.ai", impersonate="chrome",
            ) as client:
                response = await client.get("/api/organizations")
                response.raise_for_status()
                organizations = response.json()
            # end async with
        except Exception as exception:  # noqa: BLE001
            LOGGER.warning("could not auto-detect Claude organization: %s", exception)
            return {}
        # end try
        if not organizations:
            LOGGER.warning(
                "could not auto-detect Claude organization: /api/organizations returned no "
                "organizations for the captured cookies (%d cookie(s): %s)",
                len(cookies),
                ", ".join(sorted(cookies)),
            )
            return {}
        # end if
        if len(organizations) > 1:
            LOGGER.warning(
                "found %d Claude organizations, defaulting to the first (%s); pass --org-id "
                "explicitly to pick a different one (%s)",
                len(organizations),
                organizations[0].get("name"),
                ", ".join(f"{org.get('name')}={org.get('uuid')}" for org in organizations),
            )
        # end if
        return {"org_id": organizations[0]["uuid"]}
    # end def

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        org_id = str(account.options.get("org_id") or "")
        if not org_id:
            raise ProviderError("Claude web provider requires an 'org_id' option")
        # end if
        cookies = (credential or {}).get("cookies", {})
        headers = (credential or {}).get("headers", {})
        observed = datetime.now(UTC)
        raw_payload: dict[str, Any] = {}
        async with AsyncSession(
            timeout=20, cookies=cookies, headers=headers, base_url="https://claude.ai",
            impersonate="chrome",
        ) as client:
            usage_payload = await get_json(client, f"/api/organizations/{org_id}/usage", account.id)
            raw_payload["usage"] = usage_payload
            metrics = parse_claude_web_usage(usage_payload, observed)
            if not metrics:
                raise ProviderError("Claude usage response did not contain any usage windows")
            # end if

            organization: ClaudeOrganizationPayload | None = None
            try:
                organizations_payload = await get_json(client, "/api/organizations", account.id)
                raw_payload["organizations"] = organizations_payload
                match = next(
                    (org for org in organizations_payload if org.get("uuid") == org_id), None
                )
                organization = (
                    ClaudeOrganizationPayload.model_validate(match) if match is not None else None
                )
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning(
                    "could not fetch Claude organization info: %s",
                    describe_fetch_failure(exception, account.id),
                )
            # end try

            account_info: ClaudeAccountPayload | None = None
            try:
                account_payload = await get_json(client, "/api/account", account.id)
                raw_payload["account"] = account_payload
                account_info = ClaudeAccountPayload.model_validate(account_payload)
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning(
                    "could not fetch Claude account info: %s",
                    describe_fetch_failure(exception, account.id),
                )
            # end try

            subscription_info: ClaudeSubscriptionStatusPayload | None = None
            try:
                status_payload = await get_json(
                    client, f"/api/organizations/{org_id}/subscription_status", account.id
                )
                raw_payload["subscription_status"] = status_payload
                subscription_info = ClaudeSubscriptionStatusPayload.model_validate(status_payload)
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning(
                    "could not fetch Claude subscription status: %s",
                    describe_fetch_failure(exception, account.id),
                )
            # end try

            notes: list[str] = []
            try:
                app_start_payload = await get_json(
                    client,
                    f"/edge-api/bootstrap/{org_id}/app_start",
                    account.id,
                    params={
                        "statsig_hashing_algorithm": "djb2",
                        "growthbook_format": "sdk",
                        "include_system_prompts": "false",
                    },
                )
                raw_payload["app_start"] = app_start_payload
                notes = extract_claude_web_notes(app_start_payload)
            except Exception as exception:  # noqa: BLE001
                LOGGER.warning(
                    "could not fetch Claude app_start bootstrap: %s",
                    describe_fetch_failure(exception, account.id),
                )
            # end try
        # end with

        identity = None
        if organization is not None or account_info is not None:
            identity = AccountIdentity(
                name=organization.name if organization is not None else None,
                email=account_info.email_address if account_info is not None else None,
            )
        # end if
        subscription = None
        if organization is not None or subscription_info is not None:
            subscription = SubscriptionStatus(
                plan_type=organization.billing_type if organization is not None else None,
                status=subscription_info.status if subscription_info is not None else None,
                cancel_at=subscription_info.cancel_at_ts if subscription_info is not None else None,
            )
        # end if
        return ProviderFetchResult(
            service=self.service,
            provider=self.key,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            identity=identity,
            subscription=subscription,
            raw_payload=raw_payload,
            notes=notes,
        )
    # end def
# end class
