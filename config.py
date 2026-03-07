"""Configuration management for zhihu-mcp."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


@dataclass
class Viewport:
    width: int = 1920
    height: int = 1080


@dataclass
class BrowserConfig:
    headless: bool = True
    viewport: Viewport = field(default_factory=Viewport)
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    )
    user_data_dir: str = "./zhihu-profile"
    login_timeout_seconds: int = 120
    chrome_cookie_extraction: bool = True
    stealth_level: str = "advanced"  # "light" or "advanced"


@dataclass
class Config:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    cookies_path: str = "cookies.json"

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "Config":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> "Config":
        browser_data = data.get("browser", {})
        viewport_data = browser_data.get("viewport", {})
        browser = BrowserConfig(
            headless=browser_data.get("headless", True),
            viewport=Viewport(
                width=viewport_data.get("width", 1920),
                height=viewport_data.get("height", 1080),
            ),
            user_agent=browser_data.get("user_agent", BrowserConfig.user_agent),
            user_data_dir=browser_data.get("user_data_dir", "./zhihu-profile"),
            login_timeout_seconds=browser_data.get("login_timeout_seconds", 120),
            chrome_cookie_extraction=browser_data.get("chrome_cookie_extraction", True),
            stealth_level=browser_data.get("stealth_level", "advanced"),
        )
        return cls(
            browser=browser,
            cookies_path=data.get("cookies_path", "cookies.json"),
        )


def load_config(config_path: Optional[str] = None) -> Config:
    """Load config from file, env, or defaults."""
    if config_path:
        return Config.from_file(config_path)

    env_config = os.environ.get("ZHIHU_MCP_CONFIG")
    if env_config and Path(env_config).exists():
        return Config.from_file(env_config)

    for candidate in ("config.json", "config.yaml"):
        if Path(candidate).exists():
            return Config.from_file(candidate)

    # Return defaults
    return Config()
