"""Cookie management and Chrome cookie extraction for zhihu-mcp."""

import json
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CookieManager:
    """Manage cookies: load/save JSON, validate auth cookies, check expiry."""

    AUTH_COOKIE_NAMES = {"z_c0", "d_c0", "_xsrf"}

    def __init__(self, cookies_path: str = "cookies.json"):
        self.cookies_path = Path(cookies_path)

    def load(self) -> list[dict]:
        """Load cookies from JSON file."""
        if not self.cookies_path.exists():
            return []
        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            return cookies if isinstance(cookies, list) else []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load cookies: {e}")
            return []

    def save(self, cookies: list[dict]) -> None:
        """Save cookies to JSON file."""
        with open(self.cookies_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(cookies)} cookies to {self.cookies_path}")

    def has_auth_cookies(self) -> bool:
        """Check if auth cookies (z_c0, d_c0) exist."""
        cookies = self.load()
        names = {c.get("name") for c in cookies}
        return bool(names & self.AUTH_COOKIE_NAMES)

    def get_expired_count(self) -> int:
        """Count expired cookies."""
        now = time.time()
        cookies = self.load()
        return sum(
            1 for c in cookies
            if c.get("expires", -1) > 0 and c["expires"] < now
        )

    def get_status(self) -> dict:
        """Get cookie status summary."""
        cookies = self.load()
        now = time.time()
        auth_cookies = [
            c["name"] for c in cookies if c.get("name") in self.AUTH_COOKIE_NAMES
        ]
        expired = sum(
            1 for c in cookies
            if c.get("expires", -1) > 0 and c["expires"] < now
        )
        return {
            "file_exists": self.cookies_path.exists(),
            "count": len(cookies),
            "auth_cookies": auth_cookies,
            "expired_count": expired,
        }

    def filter_zhihu(self, cookies: list[dict]) -> list[dict]:
        """Filter cookies to zhihu domains only."""
        return [c for c in cookies if "zhihu" in c.get("domain", "")]


class ChromeCookieExtractor:
    """Extract Zhihu cookies from Chrome's encrypted store on macOS.

    Uses pycookiecheat (primary) or rookiepy (fallback).
    """

    ZHIHU_DOMAINS = [".zhihu.com", "www.zhihu.com", "zhihu.com"]
    ZHIHU_URLS = [
        "https://www.zhihu.com",
        "https://zhihu.com",
        "https://zhuanlan.zhihu.com",
    ]

    @staticmethod
    def extract() -> list[dict]:
        """Extract Zhihu cookies from Chrome. Returns Playwright-format cookies."""
        cookies = ChromeCookieExtractor._try_pycookiecheat()
        if cookies:
            return cookies

        cookies = ChromeCookieExtractor._try_rookiepy()
        if cookies:
            return cookies

        logger.error(
            "All Chrome cookie extraction methods failed. "
            "Ensure you are logged into Zhihu in Chrome."
        )
        return []

    @staticmethod
    def extract_and_save(output_path: str = "cookies.json") -> list[dict]:
        """Extract cookies and save to file."""
        cookies = ChromeCookieExtractor.extract()
        if cookies:
            mgr = CookieManager(output_path)
            mgr.save(cookies)
        return cookies

    @staticmethod
    def _try_pycookiecheat() -> list[dict]:
        try:
            from pycookiecheat import chrome_cookies
        except ImportError:
            logger.debug("pycookiecheat not available")
            return []

        all_cookies = {}
        try:
            for url in ChromeCookieExtractor.ZHIHU_URLS:
                all_cookies.update(chrome_cookies(url))
        except Exception as e:
            logger.warning(f"pycookiecheat failed: {e}")
            return []

        if not all_cookies:
            return []

        pw_cookies = ChromeCookieExtractor._enrich_from_chrome_db(all_cookies)
        logger.info(f"pycookiecheat: extracted {len(pw_cookies)} cookies")
        return pw_cookies

    @staticmethod
    def _try_rookiepy() -> list[dict]:
        try:
            import rookiepy
        except ImportError:
            logger.debug("rookiepy not available")
            return []

        try:
            raw = rookiepy.chrome(domains=ChromeCookieExtractor.ZHIHU_DOMAINS)
        except Exception as e:
            logger.warning(f"rookiepy failed: {e}")
            return []

        if not raw:
            return []

        pw_cookies = []
        for c in raw:
            pw_cookies.append({
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "expires": c.get("expires", -1),
                "httpOnly": c.get("httpOnly", c.get("http_only", False)),
                "secure": c.get("secure", False),
                "sameSite": c.get("sameSite", c.get("same_site", "Lax")),
            })

        logger.info(f"rookiepy: extracted {len(pw_cookies)} cookies")
        return pw_cookies

    @staticmethod
    def _enrich_from_chrome_db(simple_cookies: dict) -> list[dict]:
        """Enrich {name: value} cookies with metadata from Chrome's SQLite DB."""
        chrome_db = (
            Path.home() / "Library" / "Application Support"
            / "Google" / "Chrome" / "Default" / "Cookies"
        )

        if not chrome_db.exists():
            return [
                {
                    "name": n, "value": v, "domain": ".zhihu.com",
                    "path": "/", "expires": -1, "httpOnly": False,
                    "secure": False, "sameSite": "Lax",
                }
                for n, v in simple_cookies.items()
            ]

        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
            os.close(tmp_fd)
            shutil.copy2(str(chrome_db), tmp_path)

            conn = sqlite3.connect(tmp_path)
            cursor = conn.cursor()
            pw_cookies = []

            samesite_map = {-1: "None", 0: "None", 1: "Lax", 2: "Strict"}

            for name, value in simple_cookies.items():
                cursor.execute(
                    "SELECT host_key, path, expires_utc, is_secure, is_httponly, samesite "
                    "FROM cookies WHERE name = ? AND host_key LIKE '%zhihu%' LIMIT 1",
                    (name,),
                )
                row = cursor.fetchone()

                if row:
                    host_key, path, expires_utc, is_secure, is_httponly, samesite = row
                    expires = (expires_utc / 1_000_000) - 11644473600 if expires_utc > 0 else -1
                    pw_cookies.append({
                        "name": name, "value": value, "domain": host_key,
                        "path": path, "expires": expires,
                        "httpOnly": bool(is_httponly), "secure": bool(is_secure),
                        "sameSite": samesite_map.get(samesite, "Lax"),
                    })
                else:
                    pw_cookies.append({
                        "name": name, "value": value, "domain": ".zhihu.com",
                        "path": "/", "expires": -1, "httpOnly": False,
                        "secure": False, "sameSite": "Lax",
                    })

            conn.close()
            return pw_cookies
        except Exception as e:
            logger.warning(f"Failed to enrich cookies from Chrome DB: {e}")
            return [
                {
                    "name": n, "value": v, "domain": ".zhihu.com",
                    "path": "/", "expires": -1, "httpOnly": False,
                    "secure": False, "sameSite": "Lax",
                }
                for n, v in simple_cookies.items()
            ]
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
