"""Interactive one-time login using the isolated browser profile."""

from __future__ import annotations

import asyncio

from zhihu_mcp.browser import BrowserManager
from zhihu_mcp.config import load_config


async def _login() -> None:
    manager = BrowserManager(load_config().browser)
    await manager.start(interactive=True)
    try:
        page = await manager.new_page()
        await page.goto("https://www.zhihu.com/signin", wait_until="domcontentloaded")
        print("请在打开的独立浏览器中亲自完成知乎登录。登录成功后回到这里按 Enter。")
        await asyncio.to_thread(input)
        await page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        logged_in = await page.locator('.AppHeader-profile, [class*="AppHeader-profile"]').count() > 0
        if not logged_in:
            raise RuntimeError("未检测到登录状态；未修改其他浏览器资料。")
        print("登录状态已保存在 safe-zhihu-mcp 独立浏览器目录。")
    finally:
        await manager.close()


def main() -> None:
    asyncio.run(_login())


if __name__ == "__main__":
    main()

