# zhihu-mcp 项目规划

## 目标

构建一个知乎 MCP (Model Context Protocol) 服务器，使 AI Agent 能够与知乎网站交互——搜索内容、查看详情与评论、抓取用户动态、查询存储数据等。

## 架构参考

- **xiaohongshu-mcp**（Go）— 架构模式：浏览器生命周期、cookie 管理、MCP 工具设计
- **zhihu_monitor**（Python）— 知乎特定逻辑：stealth 反检测、安全验证处理、DOM 提取

## 浏览器后端

支持两种浏览器后端：

1. **Playwright**（主要）— 直接通过 Playwright 驱动 Chromium，注入 stealth 脚本反检测
2. **Pinchtab**（备用）— 通过 HTTP API 连接 Pinchtab 管理的浏览器实例

当前已验证 Playwright + stealth 模式在 headless 下可正常工作。

## 知乎 DOM 选择器（已验证）

| 元素 | 选择器 | 备注 |
|------|--------|------|
| 问题标题 | `.QuestionHeader-title` | |
| 回答作者 | `.AuthorInfo-content .UserLink-link` | 需跳过空头像链接 |
| 点赞数 | `button[aria-label*="赞同"]` | 解析 `aria-label` 属性，非 textContent |
| 评论数 | `.ContentItem-actions button` 含 "条评论" | 跳过 `QuestionHeader-Comment` 内的问题级按钮 |
| 评论内容 | `.CommentContent` | 文本直接在元素内 |
| 评论作者 | 父元素内 `a[href*="/people/"]` | 作者在 CommentContent 的兄弟元素中 |
| 回答数 | `.List-headerText` | 数字可能含逗号（`1,003`） |
| 关注数/浏览数 | `.NumberBoard-itemValue` | 第 1 个=关注，第 2 个=浏览 |
| 话题 | `.TopicLink .Popover div, .Tag-content` | |
| 回答列表 | `.AnswerItem` | 首屏约 5 条，更多需滚动加载 |
| 回答链接 | `.ContentItem-time a[href*="/answer/"]` | 从 href 提取 answer_id |

## 注意事项

- Zhihu 的 CSS 类名部分使用 CSS Modules（如 `css-14nvvry`），这些不稳定，应避免依赖
- 回答页面会同时显示多个回答，选择器需注意作用域（第一个 `.ContentItem` 是目标回答）
- `page.evaluate()` 中只能用标准 CSS/JS，不能用 Playwright 伪选择器（`:has-text()` 等）
- 搜索页是 SPA 渲染，`wait_for_selector` 时机不稳定
