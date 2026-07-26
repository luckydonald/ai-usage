"""Ollama Cloud usage method: HTML-scrape ollama.com/settings (the only non-JSON provider)."""

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from ai_usage.models import AccountConfig, Metric, ProviderFetchResult, SubscriptionStatus, Usage
from ai_usage.providers.base import ProviderError, UsageMethod

LOGGER = logging.getLogger(__name__)

SETTINGS_URL = "https://ollama.com/settings"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)
PLAN_VALUES = frozenset({"free", "pro", "max"})
WIDTH_PATTERN = re.compile(r"width:\s*([0-9.]+)%")
WINDOW_LABELS = (("session", "Session usage"), ("weekly", "Weekly usage"))


def build_ollama_cookie_header(session_cookie: str, cf_clearance: str | None) -> str:
    parts = [f"__Secure-session={session_cookie}"]
    if cf_clearance:
        parts.append(f"cf_clearance={cf_clearance}")
    # end if
    return "; ".join(parts)
# end def


def extract_ollama_plan(soup: BeautifulSoup) -> str | None:
    for heading in soup.find_all("h2"):
        if "cloud usage" not in heading.get_text(strip=True).lower():
            continue
        # end if
        section = heading.parent
        if isinstance(section, Tag):
            span = section.select_one("span.capitalize")
            if span:
                value = span.get_text(strip=True).lower()
                if value in PLAN_VALUES:
                    return value
                # end if
            # end if
        # end if
    # end for
    for span in soup.select("span.capitalize"):
        value = span.get_text(strip=True).lower()
        if value in PLAN_VALUES:
            return value
        # end if
    # end for
    return None
# end def


def _find_window_block(soup: BeautifulSoup, label: str) -> Tag | None:
    for span in soup.select("span.text-sm"):
        if span.get_text(strip=True) != label:
            continue
        # end if
        node: Tag | None = span
        for _ in range(6):
            node = node.parent if isinstance(node, Tag) else None
            if node is None:
                break
            # end if
            has_bar = node.select_one("[style*=\"width:\"]") is not None
            has_time = node.select_one("[data-time]") is not None
            if has_bar and has_time:
                return node
            # end if
        # end for
    # end for
    return None
# end def


def extract_ollama_usage_percentage(soup: BeautifulSoup, label: str) -> float | None:
    block = _find_window_block(soup, label)
    if block is None:
        return None
    # end if
    bar = block.select_one("[style*=\"width:\"]")
    if bar is None:
        return None
    # end if
    match = WIDTH_PATTERN.search(bar.get("style") or "")
    return float(match.group(1)) if match else None
# end def


def extract_ollama_reset_at(soup: BeautifulSoup, label: str) -> datetime | None:
    block = _find_window_block(soup, label)
    if block is None:
        return None
    # end if
    element = block.select_one("[data-time]")
    if element is None:
        return None
    # end if
    try:
        return datetime.fromisoformat(element["data-time"])
    except (ValueError, KeyError):
        return None
    # end try
# end def


def parse_ollama_settings_html(html: str, observed_at: datetime) -> list[Metric]:
    soup = BeautifulSoup(html, "html.parser")
    metrics: list[Metric] = []
    for metric_key, label in WINDOW_LABELS:
        percentage = extract_ollama_usage_percentage(soup, label)
        if percentage is None:
            continue
        # end if
        metrics.append(
            Metric(
                key=metric_key,
                name=label,
                usage=Usage(percentage=max(0.0, min(100.0, percentage))),
                observed_at=observed_at,
                reset_at=extract_ollama_reset_at(soup, label),
            )
        )
    # end for
    return metrics
# end def


class SettingsScrapeUsage(UsageMethod):
    """The only HTML-scraping usage method in the codebase — fragile by nature, coupled to
    ollama.com's current frontend markup. Fails loudly rather than silently reporting 0%."""

    required_credential_kind = "cookie_jar"

    async def fetch(
        self,
        account: AccountConfig,
        credential: dict[str, Any] | None,
    ) -> ProviderFetchResult:
        cookies = (credential or {}).get("cookies") or {}
        session_cookie = cookies.get("__Secure-session")
        if not session_cookie:
            raise ProviderError("Ollama session cookie (__Secure-session) is missing")
        # end if
        headers = {
            "Cookie": build_ollama_cookie_header(session_cookie, cookies.get("cf_clearance")),
            "Accept": "text/html",
            "User-Agent": USER_AGENT,
        }
        observed = datetime.now(UTC)
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            response = await client.get(SETTINGS_URL)
        # end async with
        if response.status_code in (401, 403):
            raise ProviderError("Ollama session cookie is invalid or expired")
        # end if
        if response.status_code != 200:
            raise ProviderError(f"Ollama /settings returned HTTP {response.status_code}")
        # end if

        html = response.text
        metrics = parse_ollama_settings_html(html, observed)
        if not metrics:
            raise ProviderError(
                "Could not parse Ollama quota from HTML — the settings page layout may have changed"
            )
        # end if

        soup = BeautifulSoup(html, "html.parser")
        plan = extract_ollama_plan(soup)

        return ProviderFetchResult(
            service=account.service,
            provider=account.provider,
            account_id=account.id,
            fetched_at=observed,
            metrics=metrics,
            subscription=SubscriptionStatus(plan_type=plan) if plan is not None else None,
            raw_payload={"html": html},
        )
    # end def
# end class
