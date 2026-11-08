"""Security-focused configuration for safe-zhihu-mcp."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_dir


@dataclass(frozen=True)
class Viewport:
    width: int = 1440
    height: int = 960


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool = True
    viewport: Viewport = field(default_factory=Viewport)
    profile_dir: Path = field(
        default_factory=lambda: Path(user_data_dir("safe-zhihu-mcp", "OpenAI")) / "browser-profile"
    )
    channel: str = "msedge" if os.name == "nt" else "chrome"
    navigation_timeout_ms: int = 30_000


@dataclass(frozen=True)
class Limits:
    min_interval_seconds: float = 3.0
    hourly_calls: int = 60
    daily_calls: int = 200
    max_results: int = 50
    max_output_chars: int = 500_000


@dataclass(frozen=True)
class Config:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    limits: Limits = field(default_factory=Limits)
    data_dir: Path = field(
        default_factory=lambda: Path(user_data_dir("safe-zhihu-mcp", "OpenAI"))
    )


def load_config() -> Config:
    """Return fixed secure defaults; environment flags cannot weaken them."""
    return Config()
