"""Pinchtab HTTP client — alternative browser backend for Zhihu scraping.

Pinchtab is a standalone Go binary that runs Chrome via CDP with superior
anti-detection (Sec-Ch-Ua patching, native fingerprinting). It exposes an
HTTP API for browser control, which this module wraps.

The PinchtabScraper implements the same interface as ZhihuScraper
(fetch_activities → list[ActivityCard]) so it can be used as a drop-in
replacement in mcp_server.py.
"""

import asyncio
import logging
from typing import Optional, List

import aiohttp

from scraper import ActivityCard, ZhihuScraper

logger = logging.getLogger(__name__)

# Shared JS extraction script (same logic as ZhihuScraper._parse_cards)
_EXTRACT_JS = """
(() => {
    const results = [];
    const selectors = [
        '.List-item', '.ContentItem', '[data-za-detail-view-id]',
        '.ActivityItem', '.ProfileActivity-listItem'
    ];

    let items = [];
    for (const sel of selectors) {
        items = document.querySelectorAll(sel);
        if (items.length > 0) break;
    }

    items.forEach((item, index) => {
        if (index >= 20) return;
        const activity = {};

        const titleSels = [
            '.ContentItem-title a', 'h2 a', 'h3 a', '.ActivityItem-title a',
            'a[data-za-detail-view-element-name]', '.RichContent-title a',
            '.ContentItem-title', 'a[href*="/question/"]',
            'a[href*="/p/"]', 'a[href*="/article/"]'
        ];
        for (const sel of titleSels) {
            const elem = item.querySelector(sel);
            if (elem && elem.textContent.trim().length > 5) {
                activity.title = elem.textContent.trim();
                activity.link = elem.href;
                break;
            }
        }

        const contentSels = [
            '.RichText', '.ContentItem-content',
            '.ActivityItem-content', '.RichContent-inner'
        ];
        for (const sel of contentSels) {
            const elem = item.querySelector(sel);
            if (elem) {
                const text = elem.textContent.trim();
                if (text.length > 20) {
                    activity.summary = text.substring(0, 300);
                    break;
                }
            }
        }

        const timeSels = [
            '.ContentItem-time', '.ActivityItem-time', 'time',
            '.ContentItem-meta', '.ActivityItem-meta'
        ];
        for (const sel of timeSels) {
            const elem = item.querySelector(sel);
            if (elem) {
                const text = elem.textContent.trim();
                if (/\\d{1,2}[:\\-]\\d{2}|今天|昨天|小时前|分钟前|\\d{4}-\\d{2}-\\d{2}/.test(text)) {
                    activity.time = text;
                    break;
                }
            }
        }

        if (activity.title) results.push(activity);
    });
    return results;
})()
"""


class PinchtabScraper:
    """Scraper using Pinchtab HTTP API as browser backend."""

    BASE_URL = "https://www.zhihu.com/people/{token}/activities"

    def __init__(
        self,
        pinchtab_url: str,
        profile: str = "zhihu",
        headless: bool = True,
    ):
        self.pinchtab_url = pinchtab_url.rstrip("/")
        self.profile = profile
        self.headless = headless
        self.instance_port: Optional[int] = None
        # For time parsing, reuse ZhihuScraper's logic
        self._time_parser = ZhihuScraper.__new__(ZhihuScraper)

    async def _ensure_instance(self) -> str:
        """Ensure the Pinchtab profile is running. Returns instance base URL."""
        if self.instance_port:
            return f"http://localhost:{self.instance_port}"

        logger.info(f"Starting Pinchtab instance for profile: {self.profile}")

        async with aiohttp.ClientSession() as session:
            # Check for already running instance
            try:
                resp = await session.get(
                    f"{self.pinchtab_url}/instances",
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                if resp.status == 200:
                    instances = await resp.json()
                    for inst in instances:
                        if inst.get("name") != self.profile:
                            continue
                        if inst.get("status") == "running" and inst.get("port"):
                            self.instance_port = inst["port"]
                            logger.info(
                                f"Connected to running Pinchtab on port {self.instance_port}"
                            )
                            return f"http://localhost:{self.instance_port}"
                        if inst.get("status") in ("error", "exited", "stopped"):
                            logger.warning(f"Flushing stale profile '{self.profile}'")
                            try:
                                await session.post(
                                    f"{self.pinchtab_url}/stop/{self.profile}",
                                    timeout=aiohttp.ClientTimeout(total=10),
                                )
                            except Exception:
                                pass
                            await asyncio.sleep(1)
            except asyncio.TimeoutError:
                logger.warning("Timeout checking Pinchtab instances")

            # Start the profile
            target_port = "9869" if self.headless else "9868"
            try:
                resp = await session.post(
                    f"{self.pinchtab_url}/start/{self.profile}",
                    json={"headless": self.headless, "port": target_port},
                    timeout=aiohttp.ClientTimeout(total=15),
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Timeout starting Pinchtab profile '{self.profile}'"
                )

            if resp.status not in (200, 201):
                text = await resp.text()
                raise RuntimeError(f"Pinchtab start failed: {text}")

            # Poll until running
            for _ in range(30):
                await asyncio.sleep(0.5)
                poll_resp = await session.get(f"{self.pinchtab_url}/instances")
                if poll_resp.status == 200:
                    for inst in await poll_resp.json():
                        if (
                            inst.get("name") == self.profile
                            and inst.get("status") == "running"
                            and inst.get("port")
                        ):
                            self.instance_port = inst["port"]
                            logger.info(
                                f"Started Pinchtab '{self.profile}' on port {self.instance_port}"
                            )
                            return f"http://localhost:{self.instance_port}"

            raise RuntimeError("Pinchtab profile never finished starting")

    async def fetch_activities(
        self, token: str, scroll_count: int = 1
    ) -> List[ActivityCard]:
        """Fetch activities via Pinchtab HTTP API."""
        instance_url = await self._ensure_instance()
        target_url = self.BASE_URL.format(token=token)

        logger.info(f"Pinchtab fetching: {target_url}")

        async with aiohttp.ClientSession() as session:
            # Navigate
            try:
                nav_resp = await session.post(
                    f"{instance_url}/navigate",
                    json={"url": target_url, "waitNav": True, "newTab": True},
                    timeout=aiohttp.ClientTimeout(total=45),
                )
            except asyncio.TimeoutError:
                raise RuntimeError(f"Timeout navigating to {target_url}")

            if nav_resp.status != 200:
                logger.error(f"Navigation failed: {await nav_resp.text()}")
                return []

            nav_data = await nav_resp.json()
            tab_id = nav_data.get("tabId", "")

            try:
                await asyncio.sleep(5)

                # Check for security challenge
                try:
                    title_resp = await session.post(
                        f"{instance_url}/evaluate",
                        json={"tabId": tab_id, "expression": "document.title"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    )
                    if title_resp.status == 200:
                        title = (await title_resp.json()).get("result", "")
                        if isinstance(title, str) and "安全验证" in title:
                            logger.warning("Pinchtab hit anti-bot challenge!")
                            raise RuntimeError("Security challenge in Pinchtab")
                except asyncio.TimeoutError:
                    logger.warning("Timeout checking page title")

                # Extract activities
                try:
                    parse_resp = await session.post(
                        f"{instance_url}/evaluate",
                        json={"tabId": tab_id, "expression": _EXTRACT_JS},
                        timeout=aiohttp.ClientTimeout(total=20),
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError("Timeout on DOM extraction")

                if parse_resp.status != 200:
                    logger.error(f"Extraction failed: {await parse_resp.text()}")
                    return []

                activities_data = (await parse_resp.json()).get("result", [])
                if not isinstance(activities_data, list):
                    activities_data = []

                cards = []
                for data in activities_data:
                    try:
                        cards.append(ActivityCard(
                            title=data.get("title", ""),
                            link=data.get("link", ""),
                            summary=data.get("summary", ""),
                            time=self._time_parser._parse_time(data.get("time", "")),
                            author=token,
                            raw_time=data.get("time", ""),
                        ))
                    except Exception as e:
                        logger.debug(f"Failed to create ActivityCard: {e}")

                logger.info(f"Pinchtab found {len(cards)} cards for {token}")
                return cards

            finally:
                # Close the tab
                if tab_id:
                    try:
                        await session.post(
                            f"{instance_url}/tab",
                            json={"action": "close", "tabId": tab_id},
                            timeout=aiohttp.ClientTimeout(total=5),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to close tab: {e}")
