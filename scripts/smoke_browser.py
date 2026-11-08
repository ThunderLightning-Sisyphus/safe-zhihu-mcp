"""Launch the isolated browser and verify a read-only Zhihu navigation."""

import asyncio

from zhihu_mcp.browser import BrowserManager
from zhihu_mcp.config import load_config


async def main() -> None:
    manager = BrowserManager(load_config().browser)
    await manager.start()
    try:
        page = await manager.new_page()
        await page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        print({"title": (await page.title())[:100], "url": page.url})
    finally:
        await manager.close()


if __name__ == "__main__":
    asyncio.run(main())
