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
        "Interact with Zhihu (知乎). Use get_activities to fetch recent posts "
        "from any Zhihu user by their URL token. Use get_new_since to check the "
        "database for recently captured activities. Use get_db_stats for an overview. "
        "Use cookie_status to check login state."
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
            from storage import Database
            self._db = Database()
        return self._db

    async def ensure_browser(self):
        if self._initialized:
            return self._scraper

        from browser import BrowserManager
        from config import BrowserConfig, load_config
        from scraper import ZhihuScraper

        app_config = load_config()
        is_headless = os.environ.get("HEADLESS", "true").lower() == "true"

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
        logger.info("Browser initialized for MCP server")
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
    from cookies import CookieManager

    mgr = CookieManager()
    result = mgr.get_status()
    result["login_verified"] = False

    try:
        scraper = await state.ensure_browser()
        await scraper.page.goto(
            "https://www.zhihu.com", wait_until="networkidle", timeout=30000
        )
        title = await scraper.page.title()
        result["login_verified"] = "私信" in title or "消息" in title
        result["page_title"] = title
        await state.save_cookies()
    except Exception as e:
        result["login_error"] = str(e)

    return json.dumps(result, ensure_ascii=False, indent=2)


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

    await run_test("get_db_stats", get_db_stats())
    await run_test("cookie_status", cookie_status())
    await run_test("get_activities(xu-ze-qiu, 3)", get_activities("xu-ze-qiu", 3))
    await run_test("get_new_since(hours=24)", get_new_since(24))

    await state.shutdown()

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
