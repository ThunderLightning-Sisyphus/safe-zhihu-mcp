# CLAUDE.md

本项目使用中文作为主要沟通语言。提交说明、文档、注释优先使用中文。

## 项目概述

zhihu-mcp 是一个知乎 MCP 服务器，让 AI Agent 能与知乎交互。基于 Playwright + stealth 反检测驱动 headless Chromium 抓取知乎页面。

## 关键架构

- **mcp_server.py** — FastMCP 入口，注册所有 MCP 工具
- **scraper.py** — 核心 DOM 提取，所有 JS 在 `page.evaluate()` 中执行
- **browser/manager.py** — Playwright 浏览器生命周期（persistent/non-persistent context）
- **browser/stealth.py** — 反检测 JS 注入（navigator.webdriver 覆盖、Canvas 噪声等）
- **pinchtab_client.py** — Pinchtab HTTP 后端（备用，当前未使用）
- **cookies/manager.py** — Cookie 加载/保存/提取
- **storage.py** — SQLite 活动数据存储
- **config.py** — 配置管理（BrowserConfig dataclass）

## 重要约束

### page.evaluate() 只支持标准 CSS/JS
Playwright 伪选择器（`:has-text()`、`:visible` 等）在 `page.evaluate()` 内无效。必须用标准 DOM API：
```javascript
// 错误：document.querySelector('button:has-text("评论")')
// 正确：
for (const b of document.querySelectorAll('button')) {
    if (b.textContent.includes('评论')) { b.click(); break; }
}
```

### 知乎 DOM 选择器（已验证）
| 元素 | 选择器 | 注意 |
|------|--------|------|
| 回答作者 | `.AuthorInfo-content .UserLink-link` | 跳过空头像链接（遍历取首个有文本的） |
| 点赞数 | `button[aria-label*="赞同"]` | 解析 `aria-label` 属性，不是 textContent |
| 评论数 | `.ContentItem-actions button` 含 "条评论" | 不要用全局 `button`，会匹配到问题级评论按钮 |
| 评论内容 | `.CommentContent` | 文本直接在元素内，作者在父元素的兄弟节点 `a[href*="/people/"]` |
| 回答数 | `.List-headerText` | 数字含逗号（`1,003`），需 `replace(/,/g, '')` |
| 回答页多按钮 | 回答页同时显示多个回答 | 用 `.ContentItem-actions` 限定作用域，避免取到其他回答的数据 |

### 评论 URL 匹配
`get_comments` 判断是否需要导航时，必须比较完整路径（`url.split('?')[0]`），不能截断比较——同一问题下不同回答 URL 前缀相同。

### 代理绕过
浏览器启动参数包含 `--proxy-bypass-list=*.zhihu.com,zhihu.com,*.zhimg.com`，访问知乎时不走系统代理。

## 开发与测试

- 测试脚本在 `tests/` 目录（已 gitignored）
- `tests/test_core.py` 是主要的集成测试脚本
- 默认使用 headless 模式（`config.browser.headless = True`），调试时可改为 `False`
- 需要有效的 `cookies.json`（含 `z_c0` 认证 token）才能正常抓取

## 已知限制

- 搜索功能（SPA 渲染）不稳定，`wait_for_selector` 时机问题
- 问题页仅加载首屏约 5 条回答，更多需要实现滚动加载
- CSS Modules 类名（如 `css-14nvvry`）不稳定，不要依赖
