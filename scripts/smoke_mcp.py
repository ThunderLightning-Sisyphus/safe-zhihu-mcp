"""Exercise representative MCP handlers without printing personal content."""

import asyncio
import json

import mcp_server


async def call(name: str, **kwargs):
    tool = mcp_server.mcp._tool_manager._tools[name]
    return json.loads(await tool.fn(**kwargs))


async def main() -> None:
    try:
        login = await call("check_login_status")
        search = await call("search_content", keyword="投稿状态", count=3)
        comments = await call(
            "get_comments",
            url="https://www.zhihu.com/question/19550225/answer/1992353258262504861",
            count=3,
        )
        reply_target = next(
            (item.get("comment_id") for item in comments.get("comments", []) if item.get("reply_count", 0) > 0),
            None,
        )
        replies = (
            await call("get_comment_replies", comment_id=reply_target, count=3)
            if reply_target else {"success": True, "count": 0}
        )
        print({
            "logged_in": login.get("logged_in"),
            "search_ok": search.get("success"),
            "search_count": search.get("count", 0),
            "comments_ok": comments.get("success"),
            "comment_count": comments.get("count", 0),
            "replies_ok": replies.get("success"),
            "reply_count": replies.get("count", 0),
        })
    finally:
        if mcp_server.state.browser is not None:
            await mcp_server.state.browser.close()


if __name__ == "__main__":
    asyncio.run(main())
