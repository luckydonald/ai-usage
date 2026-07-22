"""Real-browser end-to-end tests for the funnel filter chips persisting to `localStorage`.

Drives the actually-built frontend in a real Chromium tab against a real backend —
this is the only way to exercise real `localStorage` round-tripping across an actual
page reload, which a `happy-dom` unit test (`frontend/src/App.vue` has none) or a
mocked-`echarts` component test can't observe.

Requires `frontend/dist` to be built (`corepack yarn@4.9.2 build`) and the
`playwright` extra with its Chromium browser installed (`uv sync --extra browser`,
`uv run playwright install chromium`); skips cleanly if either is missing, since
this is a heavier opt-in check, not part of the default `uv run pytest` run.
"""

import base64
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from ai_usage.models import Metric, ProviderFetchResult, Usage
from tests.e2e_support import FRONTEND_DIST, running_app, skip_unless_frontend_built
from tests.test_storage import temporary_paths


def _write_account(paths, service: str, provider: str, account_id: str, name: str) -> None:
    directory = paths.services / service
    directory.mkdir(parents=True, exist_ok=True)
    data = {"id": account_id, "service": service, "provider": provider, "name": name, "enabled": True}
    (directory / f"{account_id}.yml").write_text(yaml.safe_dump(data), encoding="utf-8")
# end def


async def _seed(runtime) -> None:
    now = datetime.now(UTC)
    for service, provider, account in (("claude", "web", "acct-web"), ("codex", "app-server", "acct-codex")):
        await runtime.history.append_result(
            ProviderFetchResult(
                service=service,
                provider=provider,
                account_id=account,
                fetched_at=now,
                metrics=[Metric(key="five-hours", name="Five hours", usage=Usage(percentage=42), observed_at=now)],
            )
        )
    # end for
# end def


class _SeriesRequestLog:
    """Collects every `/api/v1/series` request URL fired on the page.

    A stale/invalid filter drives the frontend's auto-widen retry loop (it keeps trying wider
    time ranges when a series page comes back empty), which fires several `series` requests in a
    row — capturing just "the next matching request" can race and grab one from mid-retry.
    Recording all of them and asserting on the *last* one is what's actually reliable.
    """

    def __init__(self, page) -> None:
        self.urls: list[str] = []
        page.on("request", self._on_request)
    # end def

    def _on_request(self, request) -> None:
        if "/api/v1/series" in request.url:
            self.urls.append(request.url)
        # end if
    # end def

    async def wait_for_settled(self, page) -> None:
        # The auto-widen retry loop fires its requests back-to-back with no user-visible signal
        # to await on; a short fixed wait is the simplest way to let it run to completion.
        await page.wait_for_timeout(500)
    # end def

    def last_query(self) -> dict[str, list[str]]:
        assert self.urls, "no /api/v1/series request was observed"
        return parse_qs(urlparse(self.urls[-1]).query)
    # end def
# end class


@pytest.mark.asyncio
async def test_service_filter_selection_survives_a_page_reload(tmp_path, monkeypatch) -> None:
    skip_unless_frontend_built()

    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = replace(temporary_paths(tmp_path), frontend=FRONTEND_DIST)
    _write_account(paths, "claude", "web", "acct-web", "Claude web")
    _write_account(paths, "codex", "app-server", "acct-codex", "Codex app server")

    async with running_app(paths) as (runtime, base_url):
        await runtime.initialize()
        await _seed(runtime)

        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base_url)
                codex_chip = page.locator(".chip").filter(has_text="codex").first
                await codex_chip.wait_for(state="visible")
                await codex_chip.click()
                await page.wait_for_function("document.querySelectorAll('.chip.active').length > 0")

                stored = await page.evaluate("localStorage.getItem('ai-usage-filters')")
                assert stored is not None
                assert json.loads(stored)["services"] == ["codex"]

                requests = _SeriesRequestLog(page)
                await page.reload()
                await requests.wait_for_settled(page)
                assert requests.last_query().get("service") == ["codex"]

                codex_chip = page.locator(".chip").filter(has_text="codex").first
                await codex_chip.wait_for(state="visible")
                await page.wait_for_function("document.querySelectorAll('.chip.active').length > 0")
                assert "active" in (await codex_chip.get_attribute("class") or "")
            finally:
                await browser.close()
            # end try
        # end async with
    # end async with
# end def


@pytest.mark.asyncio
async def test_stale_filter_from_an_older_catalog_is_pruned_instead_of_hiding_everything(tmp_path, monkeypatch) -> None:
    skip_unless_frontend_built()

    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = replace(temporary_paths(tmp_path), frontend=FRONTEND_DIST)
    _write_account(paths, "claude", "web", "acct-web", "Claude web")

    async with running_app(paths) as (runtime, base_url):
        await runtime.initialize()
        await _seed(runtime)

        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base_url)
                # A service that no longer exists in this catalog (e.g. an account removed since
                # the value was stored) must not silently filter the chart down to nothing.
                await page.evaluate(
                    "localStorage.setItem('ai-usage-filters', JSON.stringify("
                    "{services: ['long-removed-service'], providers: [], accounts: [], metrics: []}))"
                )

                requests = _SeriesRequestLog(page)
                await page.reload()
                await requests.wait_for_settled(page)
                assert "service" not in requests.last_query()

                stored = await page.evaluate("localStorage.getItem('ai-usage-filters')")
                assert json.loads(stored)["services"] == []
            finally:
                await browser.close()
            # end try
        # end async with
    # end async with
# end def
