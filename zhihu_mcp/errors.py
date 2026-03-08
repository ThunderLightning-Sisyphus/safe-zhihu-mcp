"""Custom exceptions for zhihu-mcp."""


class ZhihuMCPError(Exception):
    """Base exception."""


class LoginRequiredError(ZhihuMCPError):
    """User is not logged in."""


class SecurityChallengeError(ZhihuMCPError):
    """Zhihu anti-bot security challenge encountered."""


class CookieError(ZhihuMCPError):
    """Cookie extraction or loading failed."""


class BrowserError(ZhihuMCPError):
    """Browser operation failed."""
