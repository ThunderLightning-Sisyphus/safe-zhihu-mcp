"""Zhihu activity scraper — DOM extraction from user profile pages."""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


@dataclass
class ActivityCard:
    """A single activity from a Zhihu user's profile."""

    title: str
    link: str
    summary: str
    time: datetime
    author: str
    raw_time: str

    @property
    def unique_id(self) -> str:
        return f"{self.author}:{self.link}"


class ZhihuScraper:
    """Scraper for Zhihu user activity pages."""

    BASE_URL = "https://www.zhihu.com/people/{token}/activities"

    def __init__(self, page: Page):
        self.page = page

    async def fetch_activities(
        self, token: str, scroll_count: int = 1
    ) -> list[ActivityCard]:
        """Fetch activities for a user token."""
        url = self.BASE_URL.format(token=token)
        logger.info(f"Fetching activities from: {url}")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.page.goto(url, wait_until="networkidle", timeout=30000)
            except PlaywrightTimeout:
                logger.warning(f"Timeout loading {url}, retrying...")
                try:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeout:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                    break

            # Check for anti-bot challenge
            current_url = self.page.url
            title = await self.page.title()
            if "unhuman" in current_url or "安全验证" in title:
                logger.warning(f"Anti-bot challenge on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5 + attempt * 5)
                    continue
                break

            # Wait for content
            try:
                await self.page.wait_for_selector(
                    ".List-item, .ContentItem, [data-za-detail-view-id]",
                    timeout=10000,
                )
            except PlaywrightTimeout:
                await asyncio.sleep(3)

            break

        # Scroll to load more
        for _ in range(scroll_count):
            await self.page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await asyncio.sleep(1)

        cards = await self._parse_cards(token)
        logger.info(f"Found {len(cards)} activity cards for {token}")
        return cards

    async def _parse_cards(self, author_token: str) -> list[ActivityCard]:
        """Parse activity cards via JS evaluation."""
        activities_data = await self.page.evaluate("""
            () => {
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

                    // Title
                    const titleSels = [
                        '.ContentItem-title a', 'h2 a', 'h3 a',
                        'a[href*="/question/"]', 'a[href*="/p/"]', 'a[href*="/article/"]'
                    ];
                    for (const sel of titleSels) {
                        const elem = item.querySelector(sel);
                        if (elem && elem.textContent.trim().length > 5) {
                            activity.title = elem.textContent.trim();
                            activity.link = elem.href;
                            break;
                        }
                    }

                    // Summary
                    const contentSels = ['.RichText', '.ContentItem-content', '.RichContent-inner'];
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

                    // Time
                    const timeSels = ['.ContentItem-time', 'time', '.ContentItem-meta'];
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
            }
        """)

        cards = []
        for data in activities_data:
            try:
                cards.append(ActivityCard(
                    title=data.get("title", ""),
                    link=data.get("link", ""),
                    summary=data.get("summary", ""),
                    time=self._parse_time(data.get("time", "")),
                    author=author_token,
                    raw_time=data.get("time", ""),
                ))
            except Exception as e:
                logger.debug(f"Failed to create ActivityCard: {e}")

        return cards

    def _parse_time(self, time_str: str) -> datetime:
        """Parse Chinese time strings to datetime."""
        if not time_str:
            return datetime.now()

        time_str = time_str.strip()
        now = datetime.now()

        if "分钟前" in time_str:
            m = re.search(r"(\d+)", time_str)
            if m:
                return now - timedelta(minutes=int(m.group(1)))
        elif "小时前" in time_str:
            m = re.search(r"(\d+)", time_str)
            if m:
                return now - timedelta(hours=int(m.group(1)))
        elif "今天" in time_str:
            time_part = time_str.replace("今天", "").strip()
            if ":" in time_part:
                h, mi = map(int, time_part.split(":"))
                return now.replace(hour=h, minute=mi, second=0)
        elif "昨天" in time_str:
            time_part = time_str.replace("昨天", "").strip()
            yesterday = now - timedelta(days=1)
            if ":" in time_part:
                h, mi = map(int, time_part.split(":"))
                return yesterday.replace(hour=h, minute=mi, second=0)
            return yesterday
        elif re.match(r"\d{4}-\d{2}-\d{2}", time_str):
            try:
                return datetime.strptime(time_str[:10], "%Y-%m-%d")
            except ValueError:
                pass
        elif re.match(r"\d{1,2}-\d{1,2}", time_str):
            try:
                month, day = map(int, time_str.split("-"))
                return datetime(now.year, month, day)
            except ValueError:
                pass

        return now
