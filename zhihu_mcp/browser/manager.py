"""Sandboxed persistent browser lifecycle for read-only Zhihu access."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from zhihu_mcp.config import BrowserConfig
from zhihu_mcp.security import is_allowed_navigation

logger = logging.getLogger(__name__)


class BrowserManager:
    """Use a dedicated profile; never read or export another browser's cookies."""

    def __init__(self, config: BrowserConfig):
        self.config = config
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None

    async def start(self, *, interactive: bool = False) -> "BrowserManager":
        self.playwright = await async_playwright().start()
        profile = Path(self.config.profile_dir).resolve()
        profile.mkdir(parents=True, exist_ok=True)
        options = dict(
            user_data_dir=str(profile),
            headless=False if interactive else self.config.headless,
            viewport={"width": self.config.viewport.width, "height": self.config.viewport.height},
            ignore_https_errors=False,
            accept_downloads=False,
            args=["--window-size=1440,960"],
        )
        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                channel=self.config.channel, **options
            )
        except Exception:
            logger.info("System browser channel unavailable; using Playwright Chromium")
            self.context = await self.playwright.chromium.launch_persistent_context(**options)
        return self

    async def new_page(self) -> Page:
        if self.context is None:
            raise RuntimeError("Browser not started")
        page = await self.context.new_page()
        page.set_default_navigation_timeout(self.config.navigation_timeout_ms)

        async def navigation_guard(frame):
            if frame == page.main_frame and frame.url and not is_allowed_navigation(frame.url):
                await page.close()

        page.on("framenavigated", navigation_guard)
        return page

    async def close(self) -> None:
        try:
            if self.context is not None:
                await self.context.close()
        finally:
            if self.playwright is not None:
                await self.playwright.stop()
            self.context = None
            self.playwright = None
