#!/usr/bin/env python3
"""MCP server for Zhihu — exposes tools for AI agents to interact with Zhihu.

Usage:
    python3 mcp_server.py          # Run as MCP server (stdio)
    python3 mcp_server.py --test   # Run built-in self-tests
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_project_dir = Path(__file__).parent.resolve()
os.chdir(_project_dir)

if sys.platform == "darwin":
    os.environ.setdefault("TMPDIR", "/tmp")

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "zhihu-mcp",
    instructions=(
        "Interact with Zhihu (知乎). Tools: "
        "search_content — search by keyword; "
        "get_question_detail / get_answer_detail / get_article_detail — view content; "
        "get_comments — read comments; "
        "user_profile — view user info; "
        "get_activities — fetch user activity feed; "
        "get_new_since / get_db_stats — query stored data; "
        "check_login_status / delete_cookies — manage auth."
    ),
)


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

class _State:
    """Lazy-initialized shared state for browser and DB."""

    def __init__(self):
        self._browser = None
        self._scraper = None
        self._db = None
        self._initialized = False

    @property
    def db(self):
        if self._db is None:
            from zhihu_mcp.storage import Database
            self._db = Database()
        return self._db

    async def ensure_browser(self):
        if self._initialized:
            return self._scraper

        from zhihu_mcp.config import load_config

        app_config = load_config()
        is_headless = os.environ.get("HEADLESS", "true").lower() == "true"

        if app_config.browser.use_pinchtab:
            from zhihu_mcp.backend.pinchtab import PinchtabScraper

            self._scraper = PinchtabScraper(
                app_config.browser.pinchtab_url,
                app_config.browser.pinchtab_profile,
                headless=is_headless,
            )
            self._initialized = True
            logger.info("Pinchtab scraper initialized for MCP server")
            return self._scraper

        from zhihu_mcp.browser import BrowserManager
        from zhihu_mcp.config import BrowserConfig
        from zhihu_mcp.scraper import ZhihuScraper

        config = BrowserConfig(
            headless=is_headless,
            chrome_cookie_extraction=app_config.browser.chrome_cookie_extraction,
            user_data_dir=str(_project_dir / "zhihu-profile"),
            stealth_level=app_config.browser.stealth_level,
        )
        self._browser = BrowserManager(config, cookies_path=app_config.cookies_path)
        await self._browser.start()

        page = await self._browser.new_page()
        await self._browser.warmup_session(page)
        self._scraper = ZhihuScraper(page)
        self._initialized = True
        logger.info("Playwright browser initialized for MCP server")
        return self._scraper

    async def save_cookies(self):
        if self._browser:
            await self._browser.save_cookies()

    async def shutdown(self):
        if self._browser:
            await self._browser.close()
            self._initialized = False
            self._browser = None
            self._scraper = None


state = _State()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_activities(user: str, count: int = 10) -> str:
    """Fetch recent activities from a Zhihu user's profile (live scrape).

    Args:
        user: Zhihu user URL token (e.g. 'xu-ze-qiu')
        count: Number of activities to return (default 10, max 20)
    """
    count = min(max(count, 1), 20)

    try:
        scraper = await state.ensure_browser()
        activities = await scraper.fetch_activities(user, scroll_count=max(1, count // 5))
        await state.save_cookies()

        db = state.db
        new_count = 0
        for a in activities:
            if not db.is_seen(a.unique_id):
                db.add_activity(
                    a.unique_id, a.title, a.link,
                    a.summary, a.author, a.time.isoformat(),
                )
                new_count += 1

        results = [
            {
                "title": a.title,
                "link": a.link,
                "summary": a.summary[:200] if a.summary else "",
                "author": a.author,
                "time": a.raw_time,
            }
            for a in activities[:count]
        ]

        return json.dumps({
            "user": user,
            "fetched": len(results),
            "new_to_db": new_count,
            "activities": results,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"Failed to fetch activities for {user}: {e}")
        return json.dumps({"error": repr(e), "user": user})


@mcp.tool()
async def get_new_since(hours: int = 24, user: Optional[str] = None) -> str:
    """Query the database for activities captured in the last N hours.

    This does NOT scrape Zhihu — it returns previously stored results.

    Args:
        hours: Look back this many hours (default 24)
        user: Optional Zhihu user token to filter by
    """
    db = state.db
    all_activities = db.get_recent_activities(author=user, limit=100)
    cutoff = datetime.now() - timedelta(hours=hours)
    recent = [a for a in all_activities if a.created_at >= cutoff]

    results = [
        {
            "title": a.title,
            "link": a.link,
            "summary": a.summary[:200] if a.summary else "",
            "author": a.author,
            "time": a.time.isoformat() if a.time else "",
            "captured_at": a.created_at.isoformat(),
        }
        for a in recent
    ]

    return json.dumps({
        "hours": hours,
        "user_filter": user,
        "count": len(results),
        "activities": results,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_db_stats() -> str:
    """Get database statistics: total activities, tracked users, last capture time."""
    db = state.db
    stats = db.get_stats()

    conn = db._get_connection()
    cursor = conn.execute(
        "SELECT author, COUNT(*) as cnt FROM activities GROUP BY author ORDER BY cnt DESC LIMIT 20"
    )
    authors = [{"author": row[0], "count": row[1]} for row in cursor.fetchall()]

    cursor = conn.execute(
        "SELECT created_at FROM activities ORDER BY created_at DESC LIMIT 1"
    )
    row = cursor.fetchone()
    last_capture = row[0] if row else "never"

    return json.dumps({
        **stats,
        "last_capture": last_capture,
        "authors": authors,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def cookie_status() -> str:
    """Check if cookies are valid by visiting Zhihu and checking login status."""
    from zhihu_mcp.cookies import CookieManager

    mgr = CookieManager()
    result = mgr.get_status()
    result["login_verified"] = False

    try:
        scraper = await state.ensure_browser()
        if hasattr(scraper, "page") and scraper.page:
            # Playwright path: can visit page directly
            await scraper.page.goto(
                "https://www.zhihu.com", wait_until="networkidle", timeout=30000
            )
            title = await scraper.page.title()
            result["login_verified"] = "私信" in title or "消息" in title
            result["page_title"] = title
            await state.save_cookies()
        else:
            # Pinchtab path: cookie file check only
            result["backend"] = "pinchtab"
            result["login_verified"] = bool(mgr.load())
    except Exception as e:
        result["login_error"] = str(e)

    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# P2.1 — Content search & browsing
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_content(
    keyword: str,
    sort: str = "relevance",
    content_type: str = "all",
    count: int = 10,
) -> str:
    """Search Zhihu content by keyword.

    Args:
        keyword: Search query string
        sort: Sort order — "relevance" (default), "newest", or "most_upvoted"
        content_type: Filter type — "all" (default), "question", "article", "answer"
        count: Max results to return (default 10, max 20)
    """
    count = min(max(count, 1), 20)
    try:
        scraper = await state.ensure_browser()
        results = await scraper.search(keyword, sort=sort, content_type=content_type, count=count)
        await state.save_cookies()
        return json.dumps({
            "keyword": keyword, "sort": sort, "content_type": content_type,
            "count": len(results), "results": results,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return json.dumps({"error": repr(e), "keyword": keyword})


@mcp.tool()
async def get_question_detail(question_id: str) -> str:
    """Get Zhihu question detail: title, description, answer count, topics, top answers.

    Args:
        question_id: Numeric question ID (e.g. '123456789')
    """
    try:
        scraper = await state.ensure_browser()
        detail = await scraper.get_question_detail(question_id)
        await state.save_cookies()
        return json.dumps(detail, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"get_question_detail failed: {e}")
        return json.dumps({"error": repr(e), "question_id": question_id})


@mcp.tool()
async def get_answer_detail(question_id: str, answer_id: str) -> str:
    """Get full content of a specific Zhihu answer.

    Args:
        question_id: Numeric question ID
        answer_id: Numeric answer ID
    """
    try:
        scraper = await state.ensure_browser()
        detail = await scraper.get_answer_detail(question_id, answer_id)
        await state.save_cookies()
        return json.dumps(detail, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"get_answer_detail failed: {e}")
        return json.dumps({"error": repr(e), "question_id": question_id, "answer_id": answer_id})


@mcp.tool()
async def get_article_detail(article_id: str) -> str:
    """Get full content of a Zhihu zhuanlan article.

    Args:
        article_id: Numeric article ID (from zhuanlan.zhihu.com/p/{id})
    """
    try:
        scraper = await state.ensure_browser()
        detail = await scraper.get_article_detail(article_id)
        await state.save_cookies()
        return json.dumps(detail, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"get_article_detail failed: {e}")
        return json.dumps({"error": repr(e), "article_id": article_id})


# ---------------------------------------------------------------------------
# P2.2 — Comments
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_comments(url: str, count: int = 20) -> str:
    """Get comments for a Zhihu question/answer/article page.

    Args:
        url: Full URL of the content (e.g. 'https://www.zhihu.com/question/123/answer/456')
        count: Max top-level comments to load (default 20)
    """
    try:
        scraper = await state.ensure_browser()
        comments = await scraper.get_comments(url, count=count)
        await state.save_cookies()
        return json.dumps({
            "url": url, "count": len(comments), "comments": comments,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"get_comments failed: {e}")
        return json.dumps({"error": repr(e), "url": url})


# ---------------------------------------------------------------------------
# P2.3 — User profile
# ---------------------------------------------------------------------------

@mcp.tool()
async def user_profile(token: str) -> str:
    """Get a Zhihu user's profile: name, headline, bio, stats, recent items.

    Args:
        token: User URL token (e.g. 'xu-ze-qiu', from zhihu.com/people/{token})
    """
    try:
        scraper = await state.ensure_browser()
        profile = await scraper.get_user_profile(token)
        await state.save_cookies()
        return json.dumps(profile, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"user_profile failed: {e}")
        return json.dumps({"error": repr(e), "token": token})


# ---------------------------------------------------------------------------
# P2.4 — Auth management
# ---------------------------------------------------------------------------

@mcp.tool()
async def check_login_status() -> str:
    """Check Zhihu login status in detail.

    Returns login state, username if logged in, cookie presence, and expiry info.
    """
    from zhihu_mcp.cookies import CookieManager

    mgr = CookieManager()
    result = mgr.get_status()
    result["logged_in"] = False

    try:
        scraper = await state.ensure_browser()
        if hasattr(scraper, "page") and scraper.page:
            await scraper.page.goto(
                "https://www.zhihu.com", wait_until="networkidle", timeout=30000
            )
            title = await scraper.page.title()
            result["page_title"] = title
            result["logged_in"] = "首页" in title or "私信" in title

            if result["logged_in"]:
                username = await scraper.page.evaluate("""
                    () => {
                        const el = document.querySelector('.AppHeader-profile .Avatar, .AppHeader-userInfo');
                        return el ? el.getAttribute('alt') || el.textContent?.trim() || '' : '';
                    }
                """)
                if username:
                    result["username"] = username

            await state.save_cookies()
        else:
            result["backend"] = "pinchtab"
            result["logged_in"] = mgr.has_auth_cookies()
    except Exception as e:
        result["login_error"] = str(e)

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def delete_cookies() -> str:
    """Delete cookies file to reset login state.

    After deletion, the next browser operation will start without authentication.
    """
    from zhihu_mcp.cookies import CookieManager

    mgr = CookieManager()
    path = str(mgr.cookies_path)
    existed = mgr.cookies_path.exists()

    if existed:
        mgr.cookies_path.unlink()

    return json.dumps({
        "path": path,
        "existed": existed,
        "deleted": existed,
        "message": "Cookies deleted. Next operation will require re-authentication." if existed
                   else "No cookie file found.",
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("zhihu://config")
async def get_config() -> str:
    """Current configuration."""
    config_path = _project_dir / "config.json"
    if config_path.exists():
        return config_path.read_text(encoding="utf-8")
    return json.dumps({"error": "config.json not found"})


@mcp.resource("zhihu://cookies")
async def get_cookie_summary() -> str:
    """Summary of cookie status."""
    cookie_path = _project_dir / "cookies.json"
    if not cookie_path.exists():
        return json.dumps({"error": "cookies.json not found"})

    with open(cookie_path) as f:
        cookies = json.load(f)

    now = time.time()
    summary = []
    for c in cookies:
        expires = c.get("expires", -1)
        if expires > 0:
            remaining_h = (expires - now) / 3600
            status = f"{remaining_h:.0f}h remaining" if remaining_h > 0 else "EXPIRED"
        else:
            status = "session"
        summary.append({"name": c["name"], "domain": c["domain"], "status": status})

    return json.dumps(summary, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if "--test" in sys.argv:
        logging.basicConfig(level=logging.WARNING)
        asyncio.run(_run_self_tests())
    else:
        log_path = _project_dir / "mcp_server.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_path)],
        )
        mcp.run(transport="stdio")


async def _run_self_tests():
    print("=" * 50)
    print("zhihu-mcp Self-Tests")
    print("=" * 50)

    passed = failed = 0

    async def run_test(name, coro):
        nonlocal passed, failed
        print(f"\n--- {name} ---")
        try:
            result = await coro
            parsed = json.loads(result)
            print(f"  Result: {json.dumps(parsed, ensure_ascii=False, indent=2)[:400]}")
            passed += 1
            print("  PASSED")
            return parsed
        except Exception as e:
            failed += 1
            print(f"  FAILED: {e}")
            return None

    # Auth / DB
    await run_test("get_db_stats", get_db_stats())
    await run_test("cookie_status", cookie_status())

    # Search
    await run_test("search_content(大模型Agent)", search_content("大模型Agent", count=3))

    # Question detail (知乎上的经典问题)
    await run_test("get_question_detail(19550225)", get_question_detail("19550225"))

    # Answer detail — 取问题第一个回答做验证
    q_result = await run_test("get_question_detail(for_answer)", get_question_detail("19550225"))
    if q_result and q_result.get("answers"):
        first = q_result["answers"][0]
        aid = first.get("answer_id", "")
        if aid:
            await run_test(
                f"get_answer_detail(19550225, {aid})",
                get_answer_detail("19550225", aid),
            )

    # Article detail (知乎专栏文章)
    await run_test("get_article_detail(294862987)", get_article_detail("294862987"))

    # Comments
    await run_test(
        "get_comments(question/19550225)",
        get_comments("https://www.zhihu.com/question/19550225", count=5),
    )

    # User profile
    await run_test("user_profile(jiayaosu)", user_profile("jiayaosu"))

    # Activity monitoring
    await run_test("get_activities(jiayaosu, 3)", get_activities("jiayaosu", 3))
    await run_test("get_new_since(hours=24)", get_new_since(24))

    await state.shutdown()

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
