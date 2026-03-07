# TODO

## 与小红书MCP功能对比

> 小红书MCP 共 13 个工具，知乎MCP 当前 12 个工具（含 3 个独有的监控工具）

| 功能 | 小红书MCP | 知乎MCP | 状态 |
|------|----------|--------|------|
| 登录状态检查 | `check_login_status` | `check_login_status` | ✅ |
| 删除 Cookie | `delete_cookies` | `delete_cookies` | ✅ |
| Cookie 状态 | — | `cookie_status` | ✅ 知乎独有 |
| 扫码登录 | `get_login_qrcode` | — | ❌ P3 |
| 首页推荐/热榜 | `list_feeds` | — | ❌ P2.5 |
| 搜索 | `search_feeds` | `search_content` | ⚠️ SPA 不稳定 |
| 内容详情 | `get_feed_detail` | `get_question/answer/article_detail` | ✅ 更细分 |
| 评论读取 | 含在详情中 | `get_comments` | ✅ |
| 发表评论 | `post_comment_to_feed` | — | ❌ P2.6 |
| 回复评论 | `reply_comment_in_feed` | — | ❌ P2.6 |
| 点赞/取消 | `like_feed` | — | ❌ P2.7 |
| 收藏/取消 | `favorite_feed` | — | ❌ P2.7 |
| 内容发布 | `publish_content` + `publish_with_video` | — | ❌ P3 |
| 用户资料 | `user_profile` | `user_profile` | ✅ |
| 活动监控 | — | `get_activities` | ✅ 知乎独有 |
| 数据库查询 | — | `get_new_since` + `get_db_stats` | ✅ 知乎独有 |

---

## 已完成

### P0 - 核心基础
- [x] 浏览器管理 (`browser/manager.py`)
- [x] 反检测脚本 (`browser/stealth.py`)
- [x] 配置管理 (`config.py`)
- [x] 异常定义 (`errors.py`)
- [x] Cookie 管理 (`cookies/manager.py`)
- [x] 数据存储 (`storage.py`)
- [x] 网页爬取 (`scraper.py`)
- [x] MCP Server 入口 (`mcp_server.py`)
- [x] Pinchtab 备用后端 (`pinchtab_client.py`)

### P1 - 项目配置
- [x] `config.json.example`、`.gitignore`、`CLAUDE.md`

### P2.1 - 内容搜索与浏览
- [x] `search_content` — 关键词搜索（SPA 渲染不稳定，待修复）
- [x] `get_question_detail` — 问题详情 + Top 回答列表
- [x] `get_answer_detail` — 回答详情（正文/作者/点赞/评论数）
- [x] `get_article_detail` — 专栏文章详情

### P2.2 - 评论读取
- [x] `get_comments` — 评论列表（含作者）

### P2.3 - 用户信息
- [x] `user_profile` — 用户主页信息

### P2.4 - 认证管理
- [x] `check_login_status` — 登录状态检查
- [x] `delete_cookies` — 重置登录状态

### DOM 选择器修复
- [x] 作者名、点赞数、评论数、评论内容/作者、回答数逗号处理、评论 URL 匹配

---

## 待完成

### P2.5 - 知乎热榜
- [ ] `get_hot_list` — 获取知乎热榜列表（标题/热度/链接）
- [ ] `get_recommendations` — 获取首页推荐内容（对标小红书 `list_feeds`）

### P2.6 - 互动：评论
- [ ] `post_comment` — 对回答/文章发表评论
- [ ] `reply_comment` — 回复已有评论

### P2.7 - 互动：点赞/收藏
- [ ] `like_answer` — 点赞/取消点赞回答（智能检测当前状态）
- [ ] `favorite_content` — 收藏/取消收藏内容（智能检测当前状态）

### P2.8 - 稳定性修复
- [ ] 搜索 SPA 渲染问题（`search_content` 结果加载时机不稳定）
- [ ] 问题页加载更多回答（当前仅首屏 5 条，需滚动加载获取 10+）

### P3 - 远期功能
- [ ] 扫码登录流程（知乎二维码登录）
- [ ] 内容发布（发布回答/文章，对标小红书 `publish_content`）
- [ ] 关注/取关用户
- [ ] 定时监控 (`monitor.py`)
