"""Input validation, navigation allowlisting, and persistent rate limiting."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ALLOWED_HOSTS = frozenset({"www.zhihu.com", "zhuanlan.zhihu.com", "zhihu.com"})
ID_RE = re.compile(r"^[0-9]{1,24}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
QUESTION_RE = re.compile(r"^/question/[0-9]{1,24}/?$")
ANSWER_RE = re.compile(r"^/question/[0-9]{1,24}/answer/[0-9]{1,24}/?$")
ARTICLE_RE = re.compile(r"^/p/[0-9]{1,24}/?$")


class SecurityError(RuntimeError):
    pass


def validate_id(value: str, name: str) -> str:
    cleaned = str(value).strip()
    if ID_RE.fullmatch(cleaned) is None:
        raise SecurityError(f"{name} must be a numeric identifier")
    return cleaned


def validate_user_token(value: str) -> str:
    cleaned = str(value).strip()
    if TOKEN_RE.fullmatch(cleaned) is None:
        raise SecurityError("invalid Zhihu user token")
    return cleaned


def validate_keyword(value: str) -> str:
    cleaned = str(value).strip()
    if not 2 <= len(cleaned) <= 100 or any(ord(ch) < 32 for ch in cleaned):
        raise SecurityError("keyword must contain 2-100 printable characters")
    return cleaned


def validate_content_url(value: str) -> str:
    cleaned = str(value).strip()
    parsed = urlparse(cleaned)
    valid_path = (
        (parsed.hostname == "www.zhihu.com" and (QUESTION_RE.fullmatch(parsed.path) or ANSWER_RE.fullmatch(parsed.path)))
        or (parsed.hostname == "zhuanlan.zhihu.com" and ARTICLE_RE.fullmatch(parsed.path))
    )
    if parsed.scheme != "https" or not valid_path or parsed.username or parsed.password or parsed.port:
        raise SecurityError("URL must be a supported HTTPS Zhihu question, answer, or article")
    if parsed.query or parsed.fragment or parsed.params:
        raise SecurityError("URL query strings and fragments are not accepted")
    return cleaned


def is_allowed_navigation(value: str) -> bool:
    if value in ("", "about:blank"):
        return True
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS


def clamp_count(value: int, *, maximum: int = 50) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise SecurityError(f"count must be between 1 and {maximum}")
    return value


def bounded_json(data: Any, *, max_chars: int) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > max_chars:
        raise SecurityError("result exceeds the configured output limit")
    return text


class RateLimiter:
    def __init__(self, directory: Path, *, minimum: float, hourly: int, daily: int):
        self.directory = directory
        self.minimum = minimum
        self.hourly = hourly
        self.daily = daily
        self._lock = asyncio.Lock()
        self._recent: deque[float] = deque()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.time()
            while self._recent and now - self._recent[0] >= 3600:
                self._recent.popleft()
            if len(self._recent) >= self.hourly:
                raise SecurityError("hourly read limit reached")
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / "daily.json"
            day = time.strftime("%Y-%m-%d", time.localtime(now))
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                data = {"version": 1, "day": day, "calls": 0}
            except (OSError, ValueError) as exc:
                raise SecurityError("rate-limit ledger is unreadable") from exc
            if not isinstance(data, dict) or data.get("version") != 1 or type(data.get("calls")) is not int:
                raise SecurityError("rate-limit ledger is invalid")
            if data.get("day") != day:
                data = {"version": 1, "day": day, "calls": 0}
            if data["calls"] >= self.daily:
                raise SecurityError("daily read limit reached")
            if self._recent:
                wait = self.minimum - (now - self._recent[-1])
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = time.time()
            data["calls"] += 1
            temporary = self.directory / f"daily-{uuid.uuid4().hex}.tmp"
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            self._recent.append(now)

