import json

import pytest

from zhihu_mcp.security import (
    RateLimiter,
    SecurityError,
    bounded_json,
    clamp_count,
    is_allowed_navigation,
    validate_content_url,
    validate_id,
    validate_keyword,
    validate_user_token,
)


def test_navigation_allowlist():
    assert is_allowed_navigation("https://www.zhihu.com/question/123")
    assert is_allowed_navigation("https://zhuanlan.zhihu.com/p/123")
    assert not is_allowed_navigation("http://www.zhihu.com/question/123")
    assert not is_allowed_navigation("https://zhihu.com.evil.example/question/123")
    assert not is_allowed_navigation("file:///etc/passwd")


def test_content_url_rejects_credentials_queries_and_other_hosts():
    assert validate_content_url("https://www.zhihu.com/question/123/answer/456")
    assert validate_content_url("https://zhuanlan.zhihu.com/p/123")
    for value in (
        "https://evil.example/question/123",
        "https://www.zhihu.com/question/123?next=https://evil.example",
        "https://user:pass@www.zhihu.com/question/123",
        "javascript:alert(1)",
    ):
        with pytest.raises(SecurityError):
            validate_content_url(value)


def test_identifiers_keywords_and_counts_are_bounded():
    assert validate_id("123", "id") == "123"
    assert validate_user_token("safe_user-1") == "safe_user-1"
    assert validate_keyword("投稿状态") == "投稿状态"
    assert clamp_count(50) == 50
    for value in ("../1", "1e3", "", "9" * 25):
        with pytest.raises(SecurityError):
            validate_id(value, "id")
    with pytest.raises(SecurityError):
        validate_user_token("../../profile")
    with pytest.raises(SecurityError):
        clamp_count(51)


def test_output_limit():
    assert json.loads(bounded_json({"ok": True}, max_chars=100))["ok"]
    with pytest.raises(SecurityError, match="output"):
        bounded_json({"data": "x" * 101}, max_chars=100)


@pytest.mark.asyncio
async def test_daily_rate_limit_is_fail_closed(tmp_path):
    limiter = RateLimiter(tmp_path, minimum=0, hourly=10, daily=1)
    await limiter.acquire()
    with pytest.raises(SecurityError, match="daily"):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_corrupt_ledger_blocks(tmp_path):
    (tmp_path / "daily.json").write_text("broken", encoding="utf-8")
    limiter = RateLimiter(tmp_path, minimum=0, hourly=10, daily=10)
    with pytest.raises(SecurityError, match="unreadable"):
        await limiter.acquire()

