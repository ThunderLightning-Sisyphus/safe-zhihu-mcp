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

## P2.1 - 内容搜索与浏览

- [ ] `search_content` 工具 — 按关键词搜索知乎内容（问题/文章/回答），支持排序和过滤
- [ ] `get_question_detail` 工具 — 获取问题详情（标题/描述/回答数/关注数）
- [ ] `get_answer_detail` 工具 — 获取回答详情（正文/作者/点赞数/评论数）
- [ ] `get_article_detail` 工具 — 获取专栏文章详情（正文/作者/点赞数）

## P2.2 - 评论系统

- [ ] `get_comments` 工具 — 获取回答/文章的评论列表（支持分页/嵌套回复展开）
- [ ] `post_comment` 工具 — 对回答/文章发表评论
- [ ] `reply_comment` 工具 — 回复已有评论

## P2.3 - 用户信息

- [ ] `user_profile` 工具 — 获取用户主页信息（简介/关注数/粉丝数/获赞数/回答列表）

## P2.4 - 认证管理

- [ ] `check_login_status` 工具 — 完善登录状态检查（区分已登录/未登录/cookie过期）
- [ ] `delete_cookies` 工具 — 重置登录状态

## P3 - 远期功能

- [ ] 二维码/手机号登录流程（知乎登录方式与小红书不同，需单独设计）
- [ ] `like_answer` / `unlike_answer` 工具 — 点赞/取消点赞
- [ ] `favorite_content` / `unfavorite_content` 工具 — 收藏/取消收藏
- [ ] 内容发布（发布回答/文章）
- [ ] 定时监控 (`monitor.py`)
