"""Pinchtab HTTP client — alternative browser backend for Zhihu scraping.

Pinchtab is a standalone Go binary that runs Chrome via CDP with superior
anti-detection (Sec-Ch-Ua patching, native fingerprinting). It exposes an
HTTP API for browser control, which this module wraps.

The PinchtabScraper implements the same interface as ZhihuScraper
so it can be used as a drop-in replacement in mcp_server.py.
"""

import asyncio
import logging
from typing import Optional, List, Any

import aiohttp

from zhihu_mcp.scraper import ActivityCard, ZhihuScraper

logger = logging.getLogger(__name__)

# Shared JS extraction script (same logic as ZhihuScraper._parse_cards)
_EXTRACT_ACTIVITIES_JS = """
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
        self._time_parser = ZhihuScraper.__new__(ZhihuScraper)

    # ------------------------------------------------------------------
    # Instance management
    # ------------------------------------------------------------------

    async def _ensure_instance(self) -> str:
        """Ensure the Pinchtab profile is running. Returns instance base URL."""
        if self.instance_port:
            return f"http://localhost:{self.instance_port}"

        logger.info(f"Starting Pinchtab instance for profile: {self.profile}")

        async with aiohttp.ClientSession() as session:
            profile_id = None

            # Check for already running instance
            try:
                resp = await session.get(
                    f"{self.pinchtab_url}/instances",
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                if resp.status == 200:
                    instances = await resp.json()
                    for inst in instances:
                        if inst.get("profileName") != self.profile:
                            continue
                        if inst.get("status") == "running" and inst.get("port"):
                            self.instance_port = inst["port"]
                            logger.info(
                                f"Connected to running Pinchtab on port {self.instance_port}"
                            )
                            return f"http://localhost:{self.instance_port}"
                        if inst.get("status") in ("error", "exited", "stopped"):
                            logger.warning(f"Flushing stale instance for '{self.profile}'")
                            inst_id = inst.get("id", "")
                            try:
                                await session.delete(
                                    f"{self.pinchtab_url}/instances/{inst_id}",
                                    timeout=aiohttp.ClientTimeout(total=10),
                                )
                            except Exception:
                                pass
                            await asyncio.sleep(1)
            except asyncio.TimeoutError:
                logger.warning("Timeout checking Pinchtab instances")

            # Find the profile ID by name
            try:
                resp = await session.get(
                    f"{self.pinchtab_url}/profiles",
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                if resp.status == 200:
                    for prof in await resp.json():
                        if prof.get("name") == self.profile:
                            profile_id = prof["id"]
                            break
            except Exception:
                pass

            # Create profile if it doesn't exist
            if not profile_id:
                try:
                    resp = await session.post(
                        f"{self.pinchtab_url}/profiles",
                        json={"name": self.profile},
                        timeout=aiohttp.ClientTimeout(total=10),
                    )
                    if resp.status in (200, 201):
                        data = await resp.json()
                        profile_id = data.get("id")
                        logger.info(f"Created Pinchtab profile '{self.profile}' ({profile_id})")
                except Exception as e:
                    raise RuntimeError(f"Failed to create Pinchtab profile: {e}")

            if not profile_id:
                raise RuntimeError(f"Could not find or create profile '{self.profile}'")

            # Start the profile: POST /profiles/{id}/start
            try:
                resp = await session.post(
                    f"{self.pinchtab_url}/profiles/{profile_id}/start",
                    json={"headless": self.headless},
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
                            inst.get("profileName") == self.profile
                            and inst.get("status") == "running"
                            and inst.get("port")
                        ):
                            self.instance_port = inst["port"]
                            logger.info(
                                f"Started Pinchtab '{self.profile}' on port {self.instance_port}"
                            )
                            return f"http://localhost:{self.instance_port}"

            raise RuntimeError("Pinchtab profile never finished starting")

    # ------------------------------------------------------------------
    # Core: navigate + evaluate
    # ------------------------------------------------------------------

    async def _navigate_and_evaluate(
        self,
        url: str,
        js_expression: str,
        wait_seconds: float = 5,
        pre_scripts: Optional[List[str]] = None,
    ) -> Any:
        """Navigate to URL, optionally run pre-scripts, then evaluate JS and return result.

        Args:
            url: Target URL to navigate to
            js_expression: JS expression to evaluate and return result
            wait_seconds: Seconds to wait after navigation for page to render
            pre_scripts: Optional list of JS scripts to run before the main extraction
                         (e.g. clicking buttons to expand content)
        """
        instance_url = await self._ensure_instance()

        async with aiohttp.ClientSession() as session:
            # Navigate
            try:
                nav_resp = await session.post(
                    f"{instance_url}/navigate",
                    json={"url": url, "waitNav": True, "newTab": True},
                    timeout=aiohttp.ClientTimeout(total=45),
                )
            except asyncio.TimeoutError:
                raise RuntimeError(f"Timeout navigating to {url}")

            if nav_resp.status != 200:
                raise RuntimeError(f"Navigation failed: {await nav_resp.text()}")

            nav_data = await nav_resp.json()
            tab_id = nav_data.get("tabId", "")

            try:
                await asyncio.sleep(wait_seconds)

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

                # Run pre-scripts (e.g. click expand buttons)
                if pre_scripts:
                    for script in pre_scripts:
                        try:
                            await session.post(
                                f"{instance_url}/evaluate",
                                json={"tabId": tab_id, "expression": script},
                                timeout=aiohttp.ClientTimeout(total=10),
                            )
                            await asyncio.sleep(1)
                        except Exception as e:
                            logger.debug(f"Pre-script failed (non-fatal): {e}")

                # Run main extraction
                try:
                    resp = await session.post(
                        f"{instance_url}/evaluate",
                        json={"tabId": tab_id, "expression": js_expression},
                        timeout=aiohttp.ClientTimeout(total=20),
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError("Timeout on JS evaluation")

                if resp.status != 200:
                    raise RuntimeError(f"Evaluation failed: {await resp.text()}")

                return (await resp.json()).get("result")

            finally:
                if tab_id:
                    try:
                        await session.post(
                            f"{instance_url}/tab",
                            json={"action": "close", "tabId": tab_id},
                            timeout=aiohttp.ClientTimeout(total=5),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to close tab: {e}")

    # ------------------------------------------------------------------
    # Activities (original method)
    # ------------------------------------------------------------------

    async def fetch_activities(
        self, token: str, scroll_count: int = 1
    ) -> List[ActivityCard]:
        """Fetch activities via Pinchtab HTTP API."""
        url = self.BASE_URL.format(token=token)
        logger.info(f"Pinchtab fetching: {url}")

        activities_data = await self._navigate_and_evaluate(url, _EXTRACT_ACTIVITIES_JS)

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

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self, keyword: str, sort: str = "relevance", content_type: str = "all", count: int = 10
    ) -> List[dict]:
        """Search Zhihu content by keyword via Pinchtab."""
        sort_map = {"relevance": "default", "newest": "created_time", "most_upvoted": "upvoted_count"}
        sort_param = sort_map.get(sort, "default")
        url = f"https://www.zhihu.com/search?type=content&q={keyword}&sort={sort_param}"

        js = """
        (() => {
            const maxCount = %d;
            const results = [];
            const items = document.querySelectorAll('.List-item, .SearchResult-Card, .ContentItem');

            items.forEach((item, i) => {
                if (i >= maxCount) return;
                const result = {};

                const titleEl = item.querySelector('h2 a, .ContentItem-title a, a[href*="/question/"], a[href*="/p/"]');
                if (titleEl) {
                    result.title = titleEl.textContent.trim();
                    result.link = titleEl.href;
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

                const authorEl = item.querySelector('.AuthorInfo-name, .UserLink-link');
                if (authorEl) result.author = authorEl.textContent.trim();

                const excerptEl = item.querySelector('.RichText, .CopyrightRichText-richText');
                if (excerptEl) result.excerpt = excerptEl.textContent.trim().substring(0, 300);

                const voteEl = item.querySelector('.VoteButton--up, button[aria-label*="赞同"]');
                if (voteEl) {
                    const m = voteEl.textContent.match(/(\\d+)/);
                    if (m) result.upvotes = parseInt(m[1]);
                }

                if (result.title) results.push(result);
            });
            return results;
        })()
        """ % count

        result = await self._navigate_and_evaluate(url, js)
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Question detail
    # ------------------------------------------------------------------

    async def get_question_detail(self, question_id: str) -> dict:
        """Get question detail via Pinchtab."""
        url = f"https://www.zhihu.com/question/{question_id}"

        js = """
        (() => {
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
            const ansItems = document.querySelectorAll('.AnswerItem, .List-item');
            ansItems.forEach((item, i) => {
                if (i >= 5) return;
                const ans = {};
                const authorEl = item.querySelector('.AuthorInfo-name a, .UserLink-link');
                if (authorEl) ans.author = authorEl.textContent.trim();
                const contentEl = item.querySelector('.RichContent-inner .RichText');
                if (contentEl) ans.excerpt = contentEl.textContent.trim().substring(0, 200);
                const voteEl = item.querySelector('button[aria-label*="赞同"]');
                if (voteEl) {
                    const m = voteEl.textContent.match(/(\\d+)/);
                    if (m) ans.upvotes = parseInt(m[1]);
                }
                const linkEl = item.querySelector('a[href*="/answer/"]');
                if (linkEl) {
                    const m2 = linkEl.href.match(/\\/answer\\/(\\d+)/);
                    if (m2) ans.answer_id = m2[1];
                }
                if (ans.author || ans.excerpt) answers.push(ans);
            });
            result.answers = answers;
            result.question_id = window.location.pathname.match(/\\/question\\/(\\d+)/)?.[1] || '';
            result.url = window.location.href;

            return result;
        })()
        """

        result = await self._navigate_and_evaluate(url, js)
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------
    # Answer detail
    # ------------------------------------------------------------------

    async def get_answer_detail(self, question_id: str, answer_id: str) -> dict:
        """Get a specific answer's full content via Pinchtab."""
        url = f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}"

        # Click "展开阅读全文" before extracting
        expand_js = """
        (() => {
            for (const b of document.querySelectorAll('button')) {
                if (b.textContent.includes('展开阅读全文')) { b.click(); break; }
            }
        })()
        """

        js = """
        (() => {
            const result = {};

            const qTitle = document.querySelector('.QuestionHeader-title');
            if (qTitle) result.question_title = qTitle.textContent.trim();

            const authorEl = document.querySelector('.AnswerItem .AuthorInfo-name a, .AuthorInfo-name .UserLink-link');
            if (authorEl) result.author = authorEl.textContent.trim();

            const headlineEl = document.querySelector('.AuthorInfo-detail .AuthorInfo-badgeText');
            if (headlineEl) result.author_headline = headlineEl.textContent.trim();

            const contentEl = document.querySelector('.AnswerItem .RichText, .RichContent-inner .RichText');
            if (contentEl) result.content = contentEl.textContent.trim();

            const voteEl = document.querySelector('button[aria-label*="赞同"]');
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

            const timeEl = document.querySelector('.ContentItem-time span, .ContentItem-time');
            if (timeEl) result.created_time = timeEl.textContent.trim();

            result.question_id = window.location.pathname.match(/\\/question\\/(\\d+)/)?.[1] || '';
            result.answer_id = window.location.pathname.match(/\\/answer\\/(\\d+)/)?.[1] || '';
            result.url = window.location.href;

            return result;
        })()
        """

        result = await self._navigate_and_evaluate(url, js, pre_scripts=[expand_js])
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------
    # Article detail
    # ------------------------------------------------------------------

    async def get_article_detail(self, article_id: str) -> dict:
        """Get a Zhihu zhuanlan article via Pinchtab."""
        url = f"https://zhuanlan.zhihu.com/p/{article_id}"

        js = """
        (() => {
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
        })()
        """

        result = await self._navigate_and_evaluate(url, js)
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    async def get_comments(self, url: str, count: int = 20) -> List[dict]:
        """Get comments for a content page via Pinchtab."""
        # Click comment button to open comment section
        click_comment_js = """
        (() => {
            for (const b of document.querySelectorAll('button')) {
                if (b.textContent.includes('评论')) { b.click(); break; }
            }
        })()
        """

        js = """
        (() => {
            const maxCount = %d;
            const results = [];
            const items = document.querySelectorAll('.CommentItem, [class*="CommentItemV2"]');

            items.forEach((item, i) => {
                if (i >= maxCount) return;
                const comment = {};

                const authorEl = item.querySelector('.CommentItem-authorName, a[class*="UserLink"]');
                if (authorEl) comment.author = authorEl.textContent.trim();

                const contentEl = item.querySelector('.CommentItem-content, [class*="RichText"]');
                if (contentEl) comment.content = contentEl.textContent.trim();

                const timeEl = item.querySelector('.CommentItem-time, time');
                if (timeEl) comment.time = timeEl.textContent.trim();

                const likeEl = item.querySelector('.CommentItem-likeBtn, button[class*="like"]');
                if (likeEl) {
                    const m = likeEl.textContent.match(/(\\d+)/);
                    if (m) comment.likes = parseInt(m[1]);
                }

                const replies = [];
                item.querySelectorAll('.CommentItem .CommentItem, [class*="childComment"]').forEach(reply => {
                    const r = {};
                    const rAuthor = reply.querySelector('a[class*="UserLink"]');
                    if (rAuthor) r.author = rAuthor.textContent.trim();
                    const rContent = reply.querySelector('[class*="RichText"]');
                    if (rContent) r.content = rContent.textContent.trim();
                    if (r.content) replies.push(r);
                });
                if (replies.length > 0) comment.replies = replies;

                if (comment.content) results.push(comment);
            });
            return results;
        })()
        """ % count

        result = await self._navigate_and_evaluate(
            url, js, wait_seconds=5, pre_scripts=[click_comment_js]
        )
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # User profile
    # ------------------------------------------------------------------

    async def get_user_profile(self, token: str) -> dict:
        """Get user profile via Pinchtab."""
        url = f"https://www.zhihu.com/people/{token}"

        js = """
        (() => {
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
        })()
        """

        result = await self._navigate_and_evaluate(url, js)
        return result if isinstance(result, dict) else {}
