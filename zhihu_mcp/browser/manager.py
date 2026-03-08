"""Browser lifecycle manager with Playwright persistent context and stealth."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from zhihu_mcp.config import BrowserConfig
from .stealth import STEALTH_SCRIPT, ADVANCED_STEALTH_SCRIPT

logger = logging.getLogger(__name__)

# Workaround: macOS may block /var/folders temp dir
if sys.platform == "darwin" and "TMPDIR" not in os.environ:
    os.environ["TMPDIR"] = "/tmp"


class BrowserManager:
    """Manages Playwright browser with persistent context for Zhihu interaction.

    Mirrors the architecture of xiaohongshu-mcp's browser.NewBrowser():
    - Creates browser instance with cookie loading
    - Provides pages for actions to use
    - Handles cleanup on close

    Incorporates zhihu_monitor's stealth and anti-bot evasion.
    """

    def __init__(self, config: BrowserConfig, cookies_path: str = "cookies.json"):
        self.config = config
        self.cookies_path = cookies_path
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._is_persistent = False

    async def start(self) -> "BrowserManager":
        """Start browser, inject stealth scripts, load cookies.

        Returns self for chaining. After start(), use new_page() to get pages.
        """
        self.playwright = await async_playwright().start()

        # Try persistent context first, fall back to non-persistent
        try:
            await self._launch_persistent()
        except Exception as e:
            logger.warning(f"Persistent context failed ({e}), falling back to non-persistent")
            await self._launch_non_persistent()

        # Inject stealth scripts
        await self.context.add_init_script(STEALTH_SCRIPT)
        if self.config.stealth_level == "advanced":
            logger.info("Injecting advanced stealth script")
            await self.context.add_init_script(ADVANCED_STEALTH_SCRIPT)

        # Load cookies from file
        await self._load_cookies()

        return self

    async def _launch_persistent(self) -> None:
        """Launch persistent browser context (preserves session across runs)."""
        user_data_dir = Path(self.config.user_data_dir)

        self.context = await self.playwright.chromium.launch_persistent_context(
            headless=self.config.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--window-size=1920,1080",
                "--proxy-bypass-list=*.zhihu.com,zhihu.com,*.zhimg.com",
            ],
            user_data_dir=str(user_data_dir),
            viewport={
                "width": self.config.viewport.width,
                "height": self.config.viewport.height,
            },
            ignore_https_errors=True,
            user_agent=self.config.user_agent,
            ignore_default_args=["--enable-automation"],
        )
        self._is_persistent = True

    async def _launch_non_persistent(self) -> None:
        """Launch non-persistent browser context (fallback)."""
        self.browser = await self.playwright.chromium.launch(
            headless=self.config.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--window-size=1920,1080",
                "--proxy-bypass-list=*.zhihu.com,zhihu.com,*.zhimg.com",
            ],
            ignore_default_args=["--enable-automation"],
        )
        self.context = await self.browser.new_context(
            viewport={
                "width": self.config.viewport.width,
                "height": self.config.viewport.height,
            },
            user_agent=self.config.user_agent,
            ignore_https_errors=True,
        )
        self._is_persistent = False

    async def _load_cookies(self) -> None:
        """Load cookies from JSON file into browser context.

        Mirrors xiaohongshu-mcp's browser.go cookie loading:
        reads cookies.json and injects into context.
        """
        cookie_path = Path(self.cookies_path)
        if not cookie_path.exists():
            logger.debug(f"No cookie file found at {cookie_path}")
            return

        try:
            with open(cookie_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            if isinstance(cookies, list) and cookies:
                await self.context.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} cookies from {cookie_path}")
            else:
                logger.debug("Cookie file is empty or not a list")
        except Exception as e:
            logger.warning(f"Failed to load cookies from {cookie_path}: {e}")

    async def new_page(self) -> Page:
        """Create a new page in the browser context.

        Mirrors xiaohongshu-mcp's browser.NewPage().
        """
        if not self.context:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self.context.new_page()

    async def save_cookies(self) -> None:
        """Save current context cookies to file.

        Mirrors xiaohongshu-mcp's saveCookies() function:
        extracts all cookies from browser and writes to cookies.json.
        """
        if not self.context:
            return

        try:
            all_cookies = await self.context.cookies()
            # Filter to zhihu-related cookies
            zhihu_cookies = [
                c for c in all_cookies
                if "zhihu" in c.get("domain", "")
            ]

            if not zhihu_cookies:
                logger.debug("No Zhihu cookies to save")
                return

            save_list = []
            for c in zhihu_cookies:
                save_list.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c.get("path", "/"),
                    "expires": c.get("expires", -1),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "sameSite": c.get("sameSite", "Lax"),
                })

            with open(self.cookies_path, "w", encoding="utf-8") as f:
                json.dump(save_list, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved {len(save_list)} cookies to {self.cookies_path}")
        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")

    async def warmup_session(self, page: Page) -> None:
        """Visit Zhihu homepage to warm up session and handle anti-bot challenges.

        Zhihu's anti-bot detects fresh browser contexts. Visiting the homepage
        first establishes a fingerprint and handles potential security challenges.
        """
        try:
            logger.info("Warming up session via homepage visit...")
            await page.goto(
                "https://www.zhihu.com",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(2)

            current_url = page.url
            title = await page.title()

            if "unhuman" in current_url or "安全验证" in title:
                logger.warning("Security challenge detected during warmup")
                await self._solve_security_challenge(page)
                logger.info("Warmup interaction complete")
            else:
                logger.info(f"Warmup complete: title='{title[:50]}'")
        except Exception as e:
            logger.warning(f"Warmup failed (non-fatal): {e}")

    async def _solve_security_challenge(self, page: Page) -> bool:
        """Try to solve Zhihu's anti-bot verification challenge."""
        try:
            verify_btn = await page.query_selector(
                'button:has-text("开始验证"), '
                'a:has-text("开始验证"), '
                'div:has-text("开始验证"):not(:has(div)), '
                '[class*="verify"], [class*="Verify"]'
            )

            if verify_btn:
                logger.info("Found verify button, clicking...")
                await verify_btn.click()
                await asyncio.sleep(5)

                current_url = page.url
                title = await page.title()
                if "unhuman" not in current_url and "安全验证" not in title:
                    logger.info("Security challenge passed")
                    return True

                await asyncio.sleep(5)
                current_url = page.url
                title = await page.title()
                if "unhuman" not in current_url and "安全验证" not in title:
                    return True

            # Try "进入知乎" button
            enter_btn = await page.query_selector(
                'a:has-text("进入知乎"), button:has-text("进入知乎")'
            )
            if enter_btn:
                logger.info("Found '进入知乎' button, clicking...")
                await enter_btn.click()
                await asyncio.sleep(3)
                if "unhuman" not in page.url:
                    return True

            logger.warning("Could not solve verification challenge")
            return False
        except Exception as e:
            logger.warning(f"Error solving security challenge: {e}")
            return False

    async def close(self) -> None:
        """Close browser and cleanup.

        Mirrors xiaohongshu-mcp's defer b.Close() / page.Close() pattern.
        """
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        if self.playwright:
            await self.playwright.stop()
