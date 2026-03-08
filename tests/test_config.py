"""Unit tests for zhihu_mcp.config — no browser or network required."""

import json
import tempfile
from pathlib import Path

import pytest

from zhihu_mcp.config import BrowserConfig, Config, Viewport, load_config


def test_browser_config_defaults():
    config = BrowserConfig()
    assert config.headless is True
    assert config.stealth_level == "advanced"
    assert config.use_pinchtab is False
    assert config.viewport.width == 1920
    assert config.viewport.height == 1080


def test_viewport_defaults():
    vp = Viewport()
    assert vp.width == 1920
    assert vp.height == 1080


def test_config_defaults():
    config = load_config()
    assert config.cookies_path == "cookies.json"
    assert isinstance(config.browser, BrowserConfig)


def test_config_from_dict_full():
    data = {
        "browser": {
            "headless": False,
            "stealth_level": "light",
            "viewport": {"width": 1280, "height": 720},
            "use_pinchtab": True,
            "pinchtab_url": "http://localhost:9999",
        },
        "cookies_path": "my_cookies.json",
    }
    config = Config._from_dict(data)
    assert config.browser.headless is False
    assert config.browser.stealth_level == "light"
    assert config.browser.viewport.width == 1280
    assert config.browser.viewport.height == 720
    assert config.browser.use_pinchtab is True
    assert config.browser.pinchtab_url == "http://localhost:9999"
    assert config.cookies_path == "my_cookies.json"


def test_config_from_file(tmp_path):
    config_data = {
        "browser": {"headless": False, "stealth_level": "light"},
        "cookies_path": "test_cookies.json",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))

    config = Config.from_file(config_file)
    assert config.browser.headless is False
    assert config.cookies_path == "test_cookies.json"


def test_config_from_file_not_found():
    with pytest.raises(FileNotFoundError):
        Config.from_file("/nonexistent/path/config.json")
