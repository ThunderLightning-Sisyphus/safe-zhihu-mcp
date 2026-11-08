"""Zhihu scraper — DOM extraction for activities, search, detail, comments, profiles."""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

# Regex to strip HTML tags from text (img → [图片], other tags removed)
_IMG_TAG_RE = re.compile(r'<img\b[^>]*/?\s*>', re.IGNORECASE)
_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _clean_html(text: str) -> str:
    """Strip HTML tags from text, replacing img tags with [图片]."""
    if not text:
        return text
    text = _IMG_TAG_RE.sub('[图片]', text)
    text = _HTML_TAG_RE.sub('', text)
    # Collapse multiple [图片] markers
    text = re.sub(r'(\[图片\]\s*)+', '[图片] ', text)
    return text.strip()


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
        """Search Zhihu content by keyword via internal API.

        Args:
            keyword: Search query
            sort: "relevance", "newest", or "most_upvoted"
            content_type: "all", "question", "article", "answer"
            count: Max results to return
        """
        # Use Zhihu's internal search API (more reliable than DOM scraping)
        sort_map = {"relevance": "default", "newest": "created_time", "most_upvoted": "upvoted_count"}
        type_map = {"all": "general", "question": "general", "article": "general", "answer": "general"}
        sort_param = sort_map.get(sort, "default")
        search_type = type_map.get(content_type, "general")

        raw = await self.page.evaluate("""async (params) => {
            try {
                const url = `https://www.zhihu.com/api/v4/search_v3?t=${params.type}&q=${encodeURIComponent(params.keyword)}&correction=1&offset=0&limit=${params.limit}&lc_idx=0&show_all_topics=0&sort=${params.sort}`;
                const resp = await fetch(url, {
                    credentials: 'include',
                    headers: {'accept': 'application/json', 'x-requested-with': 'fetch'}
                });
                if (!resp.ok) return {error: resp.status};
                return await resp.json();
            } catch(e) {
                return {error: e.message};
            }
        }""", {"keyword": keyword, "type": search_type, "limit": min(count + 5, 20), "sort": sort_param})

        if isinstance(raw, dict) and "error" in raw:
            logger.warning(f"Search API error: {raw['error']}")
            return []

        results = []
        for item in raw.get("data", []):
            if item.get("type") != "search_result":
                continue
            obj = item.get("object", {})
            if not obj:
                continue

            otype = obj.get("type", "")
            # Skip non-content types (people, topics, etc.)
            if otype not in ("answer", "article", "question"):
                continue
            # Filter by content_type if specified
            if content_type == "question" and otype != "question":
                continue
            if content_type == "article" and otype != "article":
                continue
            if content_type == "answer" and otype != "answer":
                continue

            # Strip <em> tags from title/excerpt
            title = re.sub(r"<[^>]+>", "", obj.get("title", ""))
            excerpt = re.sub(r"<[^>]+>", "", obj.get("excerpt", ""))

            # Build web URL
            if otype == "article":
                link = f"https://zhuanlan.zhihu.com/p/{obj['id']}"
            elif otype == "answer":
                qid = obj.get("question", {}).get("id", "")
                link = f"https://www.zhihu.com/question/{qid}/answer/{obj['id']}"
            else:
                link = obj.get("url", "")

            author = ""
            if isinstance(obj.get("author"), dict):
                author = re.sub(r"<[^>]+>", "", obj["author"].get("name", ""))

            entry = {
                "title": title,
                "type": otype,
                "link": link,
                "author": author,
                "excerpt": excerpt[:300],
                "upvotes": obj.get("voteup_count", 0),
                "comment_count": obj.get("comment_count", 0),
            }
            results.append(entry)
            if len(results) >= count:
                break

        return results

    # ------------------------------------------------------------------
    # Question detail
    # ------------------------------------------------------------------

    async def get_question_detail(self, question_id: str) -> dict:
        """Get question detail: title, description, answer count, follower count."""
        url = f"https://www.zhihu.com/question/{question_id}"
        await self._navigate(url)

        detail = await self.page.evaluate("""
            () => {
                // Helper: strip img tags → [图片], then get text
                function cleanText(el) {
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('img').forEach(img => {
                        img.replaceWith('[图片]');
                    });
                    return clone.textContent.trim();
                }
                function parseNum(s) {
                    if (!s) return 0;
                    return parseInt(s.replace(/,/g, '')) || 0;
                }

                const result = {};
                const titleEl = document.querySelector('.QuestionHeader-title, h1[class*="QuestionHeader"]');
                if (titleEl) result.title = titleEl.textContent.trim();

                const descEl = document.querySelector('.QuestionRichText, .QuestionHeader-detail .RichText');
                if (descEl) result.description = cleanText(descEl);

                const metaEls = document.querySelectorAll('.NumberBoard-itemValue');
                if (metaEls.length >= 1) result.followers = parseNum(metaEls[0]?.textContent);
                if (metaEls.length >= 2) result.views = parseNum(metaEls[1]?.textContent);

                const ansCountEl = document.querySelector('.List-headerText span, h4.List-headerText');
                if (ansCountEl) {
                    const m = ansCountEl.textContent.match(/([\\d,]+)/);
                    if (m) result.answer_count = parseInt(m[1].replace(/,/g, ''));
                }

                const topicEls = document.querySelectorAll('.TopicLink .Popover div, .Tag-content');
                result.topics = Array.from(topicEls).map(el => el.textContent.trim()).filter(t => t);

                const qid = window.location.pathname.match(/\\/question\\/(\\d+)/)?.[1] || '';
                const answers = [];
                const ansItems = document.querySelectorAll('.AnswerItem');
                ansItems.forEach((item, i) => {
                    if (i >= 10) return;
                    const ans = {};
                    const authorLinks = item.querySelectorAll('.AuthorInfo-content .UserLink-link');
                    for (const a of authorLinks) {
                        const t = a.textContent.trim();
                        if (t) { ans.author = t; break; }
                    }
                    const contentEl = item.querySelector('.RichContent-inner .RichText');
                    if (contentEl) ans.excerpt = cleanText(contentEl).substring(0, 200);
                    const voteEl = item.querySelector('button[aria-label*="赞同"]');
                    if (voteEl) {
                        const aria = voteEl.getAttribute('aria-label') || '';
                        const m = aria.match(/(\\d+)/);
                        if (m) ans.upvotes = parseInt(m[1]);
                    }
                    const linkEl = item.querySelector('a[href*="/answer/"]');
                    if (linkEl) {
                        const m2 = linkEl.href.match(/answer\\/(\\d+)/);
                        if (m2) {
                            ans.answer_id = m2[1];
                            ans.url = 'https://www.zhihu.com/question/' + qid + '/answer/' + m2[1];
                        }
                    }
                    if (ans.author || ans.excerpt) answers.push(ans);
                });
                result.answers = answers;
                result.question_id = qid;
                result.url = window.location.href;

                return result;
            }
        """)
        # Post-process: strip HTML from text fields
        if detail:
            if detail.get("description"):
                detail["description"] = _clean_html(detail["description"])
            for ans in detail.get("answers", []):
                if ans.get("excerpt"):
                    ans["excerpt"] = _clean_html(ans["excerpt"])
        return detail

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

        result = await self.page.evaluate("""
            () => {
                function cleanText(el) {
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('img').forEach(img => { img.replaceWith('[图片]'); });
                    return clone.textContent.trim();
                }

                const result = {};
                const qTitle = document.querySelector('.QuestionHeader-title');
                if (qTitle) result.question_title = qTitle.textContent.trim();

                const authorLinks = document.querySelectorAll('.AuthorInfo-content .UserLink-link');
                for (const a of authorLinks) {
                    const t = a.textContent.trim();
                    if (t) { result.author = t; break; }
                }

                const headlineEl = document.querySelector('.AuthorInfo-badgeText');
                if (headlineEl) result.author_headline = headlineEl.textContent.trim();

                const contentEl = document.querySelector('.AnswerItem .RichText, .RichContent-inner .RichText');
                if (contentEl) result.content = cleanText(contentEl);

                const voteEl = document.querySelector('button[aria-label*="赞同"]');
                if (voteEl) {
                    const aria = voteEl.getAttribute('aria-label') || '';
                    const m = aria.match(/(\\d+)/);
                    if (m) result.upvotes = parseInt(m[1]);
                }
                for (const b of document.querySelectorAll('.ContentItem-actions button')) {
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
        # Post-process: strip HTML from content
        if result and result.get("content"):
            result["content"] = _clean_html(result["content"])
        return result

    # ------------------------------------------------------------------
    # Article detail
    # ------------------------------------------------------------------

    async def get_article_detail(self, article_id: str) -> dict:
        """Get a Zhihu zhuanlan article's full content."""
        url = f"https://zhuanlan.zhihu.com/p/{article_id}"
        await self._navigate(url)

        result = await self.page.evaluate("""
            () => {
                function cleanText(el) {
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('img').forEach(img => { img.replaceWith('[图片]'); });
                    return clone.textContent.trim();
                }

                const result = {};
                const titleEl = document.querySelector('.Post-Title, h1.Post-Title');
                if (titleEl) result.title = titleEl.textContent.trim();

                const authorEl = document.querySelector('.AuthorInfo-name a, .UserLink-link');
                if (authorEl) result.author = authorEl.textContent.trim();

                const contentEl = document.querySelector('.Post-RichTextContainer .RichText, .RichText.ztext.Post-RichText');
                if (contentEl) result.content = cleanText(contentEl);

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
        # Post-process: strip HTML from content
        if result and result.get("content"):
            result["content"] = _clean_html(result["content"])
        return result

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    async def get_comments(self, url: str, count: int = 20) -> List[dict]:
        """Get comments for a content page.

        Args:
            url: Full URL to the content page
            count: Max top-level comments to load
        """
        endpoint = None
        answer_match = re.search(r"/question/\d+/answer/(\d+)/?$", url)
        question_match = re.search(r"/question/(\d+)/?$", url)
        article_match = re.search(r"/p/(\d+)/?$", url)
        if answer_match:
            endpoint = f"https://www.zhihu.com/api/v4/answers/{answer_match.group(1)}/root_comments"
        elif question_match:
            endpoint = f"https://www.zhihu.com/api/v4/questions/{question_match.group(1)}/root_comments"
        elif article_match:
            endpoint = f"https://www.zhihu.com/api/v4/articles/{article_match.group(1)}/root_comments"

        if endpoint:
            try:
                response = await self.page.context.request.get(
                    endpoint,
                    params={"order": "normal", "limit": count, "offset": 0, "status": "open"},
                    headers={"Referer": url},
                    timeout=30_000,
                )
                if response.status == 200:
                    payload = await response.json()
                    items = payload.get("data", []) if isinstance(payload, dict) else []
                    parsed = []
                    for item in items[:count]:
                        if not isinstance(item, dict):
                            continue
                        author = item.get("author") if isinstance(item.get("author"), dict) else {}
                        parsed.append({
                            "comment_id": str(item.get("id", "")),
                            "author": author.get("name", ""),
                            "author_token": author.get("url_token", ""),
                            "content": _clean_html(str(item.get("content", "")))[:2000],
                            "like_count": item.get("like_count", 0),
                            "reply_count": item.get("child_comment_count", 0),
                            "created_time": item.get("created_time"),
                        })
                    if parsed:
                        return parsed
            except Exception as exc:
                logger.info("Comment API unavailable; using DOM fallback: %s", type(exc).__name__)

        current = self.page.url
        if not current or current.split('?')[0] != url.split('?')[0]:
            await self._navigate(url)

        # Open comment section via JS — click the answer's comment button, not the question's
        try:
            await self.page.evaluate("""
                (() => {
                    // First try answer-level comment button (inside ContentItem-actions)
                    for (const b of document.querySelectorAll('.ContentItem-actions button')) {
                        if (b.textContent.includes('评论')) { b.click(); return; }
                    }
                    // Fallback: any comment button (for articles etc)
                    for (const b of document.querySelectorAll('button')) {
                        if (b.textContent.includes('评论')) { b.click(); return; }
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
                // .CommentContent holds the comment text; author is in a sibling element
                const items = document.querySelectorAll('.CommentContent');

                items.forEach((item, i) => {
                    if (i >= maxCount) return;
                    const comment = {};

                    // Content: text of the CommentContent element itself
                    const text = item.textContent.trim();
                    if (text) {
                        comment.content = text.substring(0, 500);
                    }

                    // Author: go to parent container, find the people link
                    const container = item.parentElement;
                    if (container) {
                        const authorEl = container.querySelector('a[href*="/people/"]');
                        if (authorEl) comment.author = authorEl.textContent.trim();
                    }

                    if (comment.content) results.push(comment);
                });
                return results;
            }
        """, count)

    async def get_comment_replies(self, comment_id: str, count: int = 20) -> List[dict]:
        """Read replies using the logged-in browser context; never writes data."""
        endpoint = (
            f"https://www.zhihu.com/api/v4/comments/{comment_id}/child_comments"
            f"?limit={count}&offset=0"
        )
        response = await self.page.context.request.get(
            endpoint,
            headers={"Referer": "https://www.zhihu.com/"},
            timeout=30_000,
        )
        if response.status != 200:
            raise RuntimeError(f"Zhihu comment API returned HTTP {response.status}")
        payload = await response.json()
        items = payload.get("data", []) if isinstance(payload, dict) else []
        results = []
        for item in items[:count]:
            if not isinstance(item, dict):
                continue
            author = item.get("author") if isinstance(item.get("author"), dict) else {}
            reply_to = item.get("reply_to_author") if isinstance(item.get("reply_to_author"), dict) else {}
            content = _clean_html(str(item.get("content", "")))[:2000]
            results.append({
                "comment_id": str(item.get("id", "")),
                "author": author.get("name", ""),
                "author_token": author.get("url_token", ""),
                "reply_to": reply_to.get("name", ""),
                "content": content,
                "like_count": item.get("like_count", 0),
                "created_time": item.get("created_time"),
            })
        return results

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
