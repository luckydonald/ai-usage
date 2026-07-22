"""Real-browser end-to-end test for the click-to-pin chart tooltip overlay.

Unlike the frontend unit test (`frontend/src/components/UsageChart.test.ts`), which
mocks `echarts/core` entirely, this test drives the actual built frontend (real
echarts, real DOM) inside a real Chromium tab, talking to a real backend listening
on a real TCP socket with seeded sample data. It exists because the unit test's
mocked `echarts` instance can't catch a bug in how the real echarts API is called
(see the `convertFromPixel` finder-shape bug this test guards against) — only a
real browser against the real library does.

Requires `frontend/dist` to be built (`corepack yarn@4.9.2 build`) and the
`playwright` extra with its Chromium browser installed (`uv sync --extra browser`,
`uv run playwright install chromium`); skips cleanly if either is missing, since
this is a heavier opt-in check, not part of the default `uv run pytest` run.
"""

import base64
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai_usage.models import Metric, ProviderFetchResult, Usage
from tests.e2e_support import FRONTEND_DIST, running_app, skip_unless_frontend_built
from tests.test_storage import temporary_paths


@pytest.mark.asyncio
async def test_chart_click_pins_tooltip_overlay(tmp_path, monkeypatch) -> None:
    skip_unless_frontend_built()

    monkeypatch.setenv("AI_USAGE_CREDENTIAL_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    paths = replace(temporary_paths(tmp_path), frontend=FRONTEND_DIST)

    async with running_app(paths) as (runtime, base_url):
        await runtime.initialize()
        now = datetime.now(UTC)
        await runtime.history.append_result(
            ProviderFetchResult(
                service="claude",
                provider="statusline",
                account_id="account",
                fetched_at=now,
                metrics=[
                    Metric(key="five-hours", name="Five hours", usage=Usage(percentage=30), observed_at=now - timedelta(minutes=55)),
                ],
            )
        )
        await runtime.history.append_result(
            ProviderFetchResult(
                service="claude",
                provider="statusline",
                account_id="account",
                fetched_at=now,
                metrics=[
                    Metric(key="five-hours", name="Five hours", usage=Usage(percentage=70), observed_at=now - timedelta(minutes=5)),
                ],
            )
        )

        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base_url)
                canvas = page.locator(".usage-chart canvas")
                await canvas.wait_for(state="visible")
                box = await canvas.bounding_box()
                assert box is not None
                await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

                overlay = page.locator(".tooltip-overlay")
                await overlay.wait_for(state="visible")
                overlay_text = await overlay.inner_text()
                assert "Five hours" in overlay_text

                await page.locator(".pinned-tooltip-close").click()
                await overlay.wait_for(state="hidden")
            finally:
                await browser.close()
            # end try
        # end async with
    # end async with
# end def
