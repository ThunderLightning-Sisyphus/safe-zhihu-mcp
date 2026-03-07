# TODO

## P0 - 核心基础（已完成）

- [x] 浏览器管理 (`browser/manager.py`)
- [x] 反检测脚本 (`browser/stealth.py`)
- [x] 配置管理 (`config.py`)
- [x] 异常定义 (`errors.py`)
- [x] Cookie 管理实现 (`cookies/manager.py`)
- [x] 数据存储 (`storage.py`)
- [x] 网页爬取 (`scraper.py`)
- [x] MCP Server 入口 (`mcp_server.py`)

## P1 - 项目配置（已完成）

- [x] 配置文件示例 (`config.json.example`)
- [x] .gitignore

## P2 - 扩展后端（已完成）

- [x] Pinchtab 集成 (`pinchtab_client.py`)

## P2.1 - 内容搜索与浏览（已完成）

- [x] `search_content` — 按关键词搜索知乎内容
- [x] `get_question_detail` — 获取问题详情（含 Top 回答列表）
- [x] `get_answer_detail` — 获取回答详情（正文/作者/点赞/评论数）
- [x] `get_article_detail` — 获取专栏文章详情

## P2.2 - 评论系统（读取已完成）

- [x] `get_comments` — 获取回答/文章评论列表（含作者）
- [ ] `post_comment` — 发表评论
- [ ] `reply_comment` — 回复评论

## P2.3 - 用户信息（已完成）

- [x] `user_profile` — 获取用户主页信息

## P2.4 - 认证管理（已完成）

- [x] `check_login_status` — 登录状态检查
- [x] `delete_cookies` — 重置登录状态

## DOM 选择器验证（已完成）

- [x] 作者名：`.AuthorInfo-content .UserLink-link`（跳过空头像链接）
- [x] 点赞数：`button[aria-label*="赞同"]` 解析 `aria-label` 属性
- [x] 评论数：`.ContentItem-actions button`（跳过问题级按钮）
- [x] 评论内容：`.CommentContent` + 父元素内 `a[href*="/people/"]` 获取作者
- [x] 回答数：处理带逗号数字（`1,003` → `1003`）
- [x] 评论 URL 匹配：完整路径比较，避免同问题下不同回答共享评论

## P3 - 远期功能

- [ ] 搜索 SPA 渲染问题（搜索结果页加载时机不稳定）
- [ ] 问题页加载更多回答（当前仅首屏 5 条，需滚动加载）
- [ ] 登录流程（二维码/手机号）
- [ ] 互动操作（点赞/收藏/评论）
- [ ] 内容发布（发布回答/文章）
- [ ] 定时监控 (`monitor.py`)
