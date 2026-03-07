"""Zhihu scraper — DOM extraction for activities, search, detail, comments, profiles."""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

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

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self, keyword: str, sort: str = "relevance", content_type: str = "all", count: int = 10
    ) -> List[dict]:
        """Search Zhihu content by keyword.

        Args:
            keyword: Search query
            sort: "relevance", "newest", or "most_upvoted"
            content_type: "all", "question", "article", "answer"
            count: Max results to return
        """
        sort_map = {"relevance": "default", "newest": "created_time", "most_upvoted": "upvoted_count"}
        sort_param = sort_map.get(sort, "default")
        url = f"https://www.zhihu.com/search?type=content&q={keyword}&sort={sort_param}"

        # Search is a SPA page — navigate and wait for results to render
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeout:
            pass
        try:
            await self.page.wait_for_selector('.SearchResult-Card', timeout=15000)
        except PlaywrightTimeout:
            logger.warning("Search results did not appear in time")
        await asyncio.sleep(1)

        results = await self.page.evaluate("""
            (maxCount) => {
                const results = [];
                const items = document.querySelectorAll('.SearchResult-Card');

                items.forEach((item, i) => {
                    if (i >= maxCount) return;
                    const result = {};

                    // Find first <a> with zhihu content href
                    const links = item.querySelectorAll('a[href]');
                    for (const a of links) {
                        const href = a.href || '';
                        if ((href.includes('/question/') || href.includes('/p/') || href.includes('/pub/'))
                            && a.textContent.trim().length > 2) {
                            result.title = a.textContent.trim();
                            result.link = href;
                            break;
                        }
                    }
                    // Fallback: h2 text without link
                    if (!result.title) {
                        const h2 = item.querySelector('h2');
                        if (h2) result.title = h2.textContent.trim();
                    }

                    if (result.link) {
                        if (result.link.includes('/question/') && result.link.includes('/answer/'))
                            result.type = 'answer';
                        else if (result.link.includes('/question/'))
                            result.type = 'question';
                        else if (result.link.includes('/p/') || result.link.includes('/article/'))
                            result.type = 'article';
                        else
                            result.type = 'other';
                    }

                    // Author: find UserLink-link with non-empty text inside AuthorInfo
                    const authorLinks = item.querySelectorAll('.AuthorInfo-content .UserLink-link');
                    for (const a of authorLinks) {
                        const t = a.textContent.trim();
                        if (t) { result.author = t; break; }
                    }

                    const excerptEl = item.querySelector('.RichText, .CopyrightRichText-richText');
                    if (excerptEl) result.excerpt = excerptEl.textContent.trim().substring(0, 300);

                    const voteEl = item.querySelector('button[aria-label*="赞同"]');
                    if (voteEl) {
                        const aria = voteEl.getAttribute('aria-label') || '';
                        const m = aria.match(/(\\d+)/);
                        if (m) result.upvotes = parseInt(m[1]);
                    }

                    if (result.title) results.push(result);
                });
                return results;
            }
        """, count)

        return results

    # ------------------------------------------------------------------
    # Question detail
    # ------------------------------------------------------------------

    async def get_question_detail(self, question_id: str) -> dict:
        """Get question detail: title, description, answer count, follower count."""
        url = f"https://www.zhihu.com/question/{question_id}"
        await self._navigate(url)

        return await self.page.evaluate("""
            () => {
                const result = {};

                const titleEl = document.querySelector('.QuestionHeader-title, h1[class*="QuestionHeader"]');
                if (titleEl) result.title = titleEl.textContent.trim();

                const descEl = document.querySelector('.QuestionRichText, .QuestionHeader-detail .RichText');
                if (descEl) result.description = descEl.textContent.trim();

                const metaEls = document.querySelectorAll('.NumberBoard-itemValue');
                if (metaEls.length >= 1) result.followers = metaEls[0]?.textContent?.trim();
                if (metaEls.length >= 2) result.views = metaEls[1]?.textContent?.trim();

                const ansCountEl = document.querySelector('.List-headerText span, h4.List-headerText');
                if (ansCountEl) {
                    const m = ansCountEl.textContent.match(/(\\d+)/);
                    if (m) result.answer_count = parseInt(m[1]);
                }

                const topicEls = document.querySelectorAll('.TopicLink .Popover div, .Tag-content');
                result.topics = Array.from(topicEls).map(el => el.textContent.trim()).filter(t => t);

                const answers = [];
                const ansItems = document.querySelectorAll('.AnswerItem');
                ansItems.forEach((item, i) => {
                    if (i >= 5) return;
                    const ans = {};
                    // Author: find UserLink-link with text inside AuthorInfo-content
                    const authorLinks = item.querySelectorAll('.AuthorInfo-content .UserLink-link');
                    for (const a of authorLinks) {
                        const t = a.textContent.trim();
                        if (t) { ans.author = t; break; }
                    }
                    const contentEl = item.querySelector('.RichContent-inner .RichText');
                    if (contentEl) ans.excerpt = contentEl.textContent.trim().substring(0, 200);
                    const voteEl = item.querySelector('button[aria-label*="赞同"]');
                    if (voteEl) {
                        const aria = voteEl.getAttribute('aria-label') || '';
                        const m = aria.match(/(\\d+)/);
                        if (m) ans.upvotes = parseInt(m[1]);
                    }
                    const linkEl = item.querySelector('a[href*="/answer/"]');
                    if (linkEl) {
                        const m2 = linkEl.href.match(/answer\\/(\\d+)/);
                        if (m2) ans.answer_id = m2[1];
                    }
                    if (ans.author || ans.excerpt) answers.push(ans);
                });
                result.answers = answers;
                result.question_id = window.location.pathname.match(/\\/question\\/(\\d+)/)?.[1] || '';
                result.url = window.location.href;

                return result;
            }
        """)

    # ------------------------------------------------------------------
    # Answer detail
    # ------------------------------------------------------------------

    async def get_answer_detail(self, question_id: str, answer_id: str) -> dict:
        """Get a specific answer's full content."""
        url = f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}"
        await self._navigate(url)

        # Click "展开阅读全文" via JS (standard DOM, not Playwright :has-text)
        try:
            await self.page.evaluate("""
                (() => {
                    for (const b of document.querySelectorAll('button')) {
                        if (b.textContent.includes('展开阅读全文')) { b.click(); break; }
                    }
                })()
            """)
            await asyncio.sleep(1)
        except Exception:
            pass

        return await self.page.evaluate("""
            () => {
                const result = {};

                const qTitle = document.querySelector('.QuestionHeader-title');
                if (qTitle) result.question_title = qTitle.textContent.trim();

                // Author: find UserLink-link with text inside AuthorInfo-content
                const authorLinks = document.querySelectorAll('.AuthorInfo-content .UserLink-link');
                for (const a of authorLinks) {
                    const t = a.textContent.trim();
                    if (t) { result.author = t; break; }
                }

                const headlineEl = document.querySelector('.AuthorInfo-badgeText');
                if (headlineEl) result.author_headline = headlineEl.textContent.trim();

                const contentEl = document.querySelector('.AnswerItem .RichText, .RichContent-inner .RichText');
                if (contentEl) result.content = contentEl.textContent.trim();

                const voteEl = document.querySelector('button[aria-label*="赞同"]');
                if (voteEl) {
                    const aria = voteEl.getAttribute('aria-label') || '';
                    const m = aria.match(/(\\d+)/);
                    if (m) result.upvotes = parseInt(m[1]);
                }
                for (const b of document.querySelectorAll('button')) {
                    if (b.textContent.includes('条评论')) {
                        const m = b.textContent.match(/(\\d+)/);
                        if (m) { result.comment_count = parseInt(m[1]); break; }
                    }
                }

                const timeEl = document.querySelector('.ContentItem-time span, .ContentItem-time');
                if (timeEl) result.created_time = timeEl.textContent.trim();

                result.question_id = window.location.pathname.match(/\\/question\\/(\\d+)/)?.[1] || '';
                result.answer_id = window.location.pathname.match(/\\/answer\\/(\\d+)/)?.[1] || '';
                result.url = window.location.href;

                return result;
            }
        """)

    # ------------------------------------------------------------------
    # Article detail
    # ------------------------------------------------------------------

    async def get_article_detail(self, article_id: str) -> dict:
        """Get a Zhihu zhuanlan article's full content."""
        url = f"https://zhuanlan.zhihu.com/p/{article_id}"
        await self._navigate(url)

        return await self.page.evaluate("""
            () => {
                const result = {};

                const titleEl = document.querySelector('.Post-Title, h1.Post-Title');
                if (titleEl) result.title = titleEl.textContent.trim();

                const authorEl = document.querySelector('.AuthorInfo-name a, .UserLink-link');
                if (authorEl) result.author = authorEl.textContent.trim();

                const contentEl = document.querySelector('.Post-RichTextContainer .RichText, .RichText.ztext.Post-RichText');
                if (contentEl) result.content = contentEl.textContent.trim();

                const voteEl = document.querySelector('button[aria-label*="赞同"], .LikeButton');
                if (voteEl) {
                    const m = voteEl.textContent.match(/(\\d+)/);
                    if (m) result.upvotes = parseInt(m[1]);
                }

                for (const b of document.querySelectorAll('button')) {
                    if (b.textContent.includes('条评论')) {
                        const m = b.textContent.match(/(\\d+)/);
                        if (m) { result.comment_count = parseInt(m[1]); break; }
                    }
                }

                const timeEl = document.querySelector('.ContentItem-time, .Post-Header time, time');
                if (timeEl) result.created_time = timeEl.textContent.trim();

                result.article_id = window.location.pathname.match(/\\/p\\/(\\d+)/)?.[1] || '';
                result.url = window.location.href;

                return result;
            }
        """)

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    async def get_comments(self, url: str, count: int = 20) -> List[dict]:
        """Get comments for a content page.

        Args:
            url: Full URL to the content page
            count: Max top-level comments to load
        """
        current = self.page.url
        if not current or not current.startswith(url[:40]):
            await self._navigate(url)

        # Open comment section via JS (standard DOM, not Playwright :has-text)
        try:
            await self.page.evaluate("""
                (() => {
                    for (const b of document.querySelectorAll('button')) {
                        if (b.textContent.includes('评论')) { b.click(); break; }
                    }
                })()
            """)
            await asyncio.sleep(2)
        except Exception:
            pass

        try:
            await self.page.wait_for_selector('.CommentContent, .CommentItem', timeout=5000)
        except PlaywrightTimeout:
            pass
        await asyncio.sleep(1)

        return await self.page.evaluate("""
            (maxCount) => {
                const results = [];
                // Find comment containers: .CommentContent is the modern class
                const items = document.querySelectorAll('.CommentContent, .CommentItem');

                items.forEach((item, i) => {
                    if (i >= maxCount) return;
                    const comment = {};

                    // Author: look for UserLink inside this comment
                    const authorEl = item.querySelector('a.UserLink-link, [class*="UserLink"]');
                    if (authorEl) comment.author = authorEl.textContent.trim();

                    // Content: the comment text itself
                    const contentEl = item.querySelector('.RichText, [class*="RichText"]');
                    if (contentEl) {
                        comment.content = contentEl.textContent.trim();
                    } else {
                        // Fallback: get direct text content (skip author name)
                        const text = item.textContent.trim();
                        if (text.length > 5 && text !== comment.author) {
                            comment.content = text.substring(0, 500);
                        }
                    }

                    // Time
                    const timeEl = item.querySelector('time, [class*="time"], [class*="Time"]');
                    if (timeEl) comment.time = timeEl.textContent.trim();

                    // Likes
                    const likeEl = item.querySelector('button[class*="like"], [class*="Like"]');
                    if (likeEl) {
                        const m = likeEl.textContent.match(/(\\d+)/);
                        if (m) comment.likes = parseInt(m[1]);
                    }

                    if (comment.content) results.push(comment);
                });
                return results;
            }
        """, count)

    # ------------------------------------------------------------------
    # User profile
    # ------------------------------------------------------------------

    async def get_user_profile(self, token: str) -> dict:
        """Get user profile: name, bio, stats, recent items."""
        url = f"https://www.zhihu.com/people/{token}"
        await self._navigate(url)

        return await self.page.evaluate("""
            () => {
                const result = {};

                const nameEl = document.querySelector('.ProfileHeader-name, .UserProfileHeader-name');
                if (nameEl) result.name = nameEl.textContent.trim();

                const headlineEl = document.querySelector('.ProfileHeader-headline, .UserProfileHeader-headline');
                if (headlineEl) result.headline = headlineEl.textContent.trim();

                const bioEl = document.querySelector('.ProfileHeader-detailItem .ProfileHeader-detailValue');
                if (bioEl) result.bio = bioEl.textContent.trim();

                const statItems = document.querySelectorAll('.NumberBoard-itemValue');
                const statLabels = document.querySelectorAll('.NumberBoard-itemName');
                result.stats = {};
                statItems.forEach((item, i) => {
                    const label = statLabels[i]?.textContent?.trim() || '';
                    const value = item.textContent.trim();
                    if (label) result.stats[label] = value;
                });

                const items = [];
                document.querySelectorAll('.List-item, .ContentItem').forEach((item, i) => {
                    if (i >= 10) return;
                    const entry = {};
                    const titleEl = item.querySelector('.ContentItem-title a, h2 a');
                    if (titleEl) {
                        entry.title = titleEl.textContent.trim();
                        entry.link = titleEl.href;
                    }
                    const excerptEl = item.querySelector('.RichText');
                    if (excerptEl) entry.excerpt = excerptEl.textContent.trim().substring(0, 200);
                    if (entry.title) items.push(entry);
                });
                result.recent_items = items;

                result.token = window.location.pathname.match(/\\/people\\/([^/]+)/)?.[1] || '';
                result.url = window.location.href;

                return result;
            }
        """)

    # ------------------------------------------------------------------
    # Navigation helper
    # ------------------------------------------------------------------

    async def _navigate(self, url: str) -> None:
        """Navigate to URL with retry and anti-bot handling."""
        for attempt in range(3):
            try:
                await self.page.goto(url, wait_until="networkidle", timeout=30000)
            except PlaywrightTimeout:
                try:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeout:
                    if attempt < 2:
                        await asyncio.sleep(3)
                        continue
                    break

            title = await self.page.title()
            if "unhuman" in self.page.url or "安全验证" in title:
                if attempt < 2:
                    await asyncio.sleep(5 + attempt * 5)
                    continue
                break
            return

        await asyncio.sleep(2)
