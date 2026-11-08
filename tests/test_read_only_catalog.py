from pathlib import Path


def test_mcp_catalog_contains_no_write_tools():
    source = (Path(__file__).parents[1] / "mcp_server.py").read_text(encoding="utf-8")
    forbidden = (
        "publish_article",
        "publish_video",
        "post_comment",
        "reply_comment",
        "like_content",
        "follow_user",
        "delete_cookies",
        "draft_answer",
        "edit_answer",
    )
    for name in forbidden:
        assert f"def {name}(" not in source


def test_dangerous_browser_flags_and_cookie_export_are_absent():
    root = Path(__file__).parents[1]
    browser = (root / "zhihu_mcp" / "browser" / "manager.py").read_text(encoding="utf-8")
    all_runtime = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [root / "mcp_server.py", root / "login.py", browser and root / "zhihu_mcp" / "browser" / "manager.py"]
    )
    assert "--no-sandbox" not in browser
    assert "ignore_https_errors=True" not in browser
    assert "cookies.json" not in all_runtime
    assert "pycookiecheat" not in all_runtime
    assert "rookiepy" not in all_runtime

