# zhihu-mcp 项目规划

## 目标

构建一个知乎 MCP (Model Context Protocol) 服务器，使 AI Agent 能够与知乎网站交互——搜索内容、查看详情与评论、抓取用户动态、查询存储数据等。

## 架构设计

参考两个已有项目：

- **xiaohongshu-mcp**（Go）— 提供架构模式：浏览器生命周期、cookie 管理、MCP 工具设计（13 个工具覆盖认证/浏览/搜索/互动/发布）
- **zhihu_monitor**（Python）— 提供知乎特定逻辑：stealth 反检测、安全验证处理、DOM 提取

### 系统架构

```
┌─────────────┐     MCP/stdio      ┌──────────────┐    Playwright     ┌──────────────┐
│   AI Agent   │◄──────────────────►│  mcp_server  │◄────────────────►│   Chromium    │
│              │                    │    .py       │   / Pinchtab     │  (headless)   │
└─────────────┘                    └──────┬───────┘                  └──────┬───────┘
                                          │                                 │
                                          ▼                                 ▼
                                   ┌──────────────┐                  ┌──────────────┐
                                   │   SQLite DB   │                  │  zhihu.com   │
                                   │  (activities) │                  │              │
                                   └──────────────┘                  └──────────────┘
```

## MCP 工具清单

### 已实现

| 工具 | 说明 |
|------|------|
| `get_activities` | 实时爬取指定用户的活动动态 |
| `get_new_since` | 查询数据库中最近 N 小时的活动 |
| `get_db_stats` | 数据库统计（总数/作者数/最后入库时间） |
| `cookie_status` | 检查 cookie 和登录状态 |

### P2.1 — 内容搜索与浏览

| 工具 | 说明 |
|------|------|
| `search_content` | 按关键词搜索知乎（问题/文章/回答），支持排序（相关/最新/点赞）和类型过滤 |
| `get_question_detail` | 获取问题详情：标题、描述、回答数、关注数 |
| `get_answer_detail` | 获取回答详情：完整正文、作者、点赞数、评论数 |
| `get_article_detail` | 获取专栏文章详情：完整正文、作者、点赞数 |

### P2.2 — 评论系统

| 工具 | 说明 |
|------|------|
| `get_comments` | 获取回答/文章评论列表，支持分页和嵌套回复展开 |
| `post_comment` | 对回答/文章发表评论 |
| `reply_comment` | 回复已有评论 |

### P2.3 — 用户信息

| 工具 | 说明 |
|------|------|
| `user_profile` | 获取用户主页：简介、关注/粉丝/获赞数、回答列表 |

### P2.4 — 认证管理

| 工具 | 说明 |
|------|------|
| `check_login_status` | 完善的登录状态检查（已登录/未登录/cookie过期） |
| `delete_cookies` | 重置登录状态，删除 cookie 文件 |

### P3 — 远期

| 工具 | 说明 |
|------|------|
| 二维码/手机号登录 | 知乎登录流程设计 |
| `like_answer` / `unlike_answer` | 点赞/取消点赞 |
| `favorite_content` / `unfavorite_content` | 收藏/取消收藏 |
| 内容发布 | 发布回答/文章 |
| `monitor.py` | 定时后台监控 |

## 已完成模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 浏览器管理 | `browser/manager.py` | Playwright 生命周期，persistent/non-persistent，cookie 加载/保存，session 预热，安全验证 |
| 反检测注入 | `browser/stealth.py` | 两级 JS 注入：基础 + 进阶（Canvas 噪声、WebGL 欺骗、硬件伪装） |
| 配置管理 | `config.py` | BrowserConfig / Config 数据类，JSON/环境变量/默认值，Pinchtab 配置 |
| 异常定义 | `errors.py` | ZhihuMCPError 及子类 |
| Cookie 管理 | `cookies/manager.py` | CookieManager + ChromeCookieExtractor（pycookiecheat/rookiepy） |
| 数据存储 | `storage.py` | SQLite 活动去重、CRUD、统计 |
| 网页爬取 | `scraper.py` | 知乎活动页 DOM 提取，中文时间解析 |
| MCP Server | `mcp_server.py` | FastMCP 服务器，4 个工具 + 2 个资源 |
| Pinchtab 后端 | `pinchtab_client.py` | HTTP API 替代 Playwright 的浏览器后端 |

## 目标文件结构

```
zhihu-mcp/
├── PLAN.md                  # 项目规划
├── TODO.md                  # 任务追踪
├── requirements.txt         # Python 依赖
├── config.py                # 配置管理
├── config.json.example      # 配置示例
├── errors.py                # 自定义异常
├── mcp_server.py            # MCP 服务器入口
├── scraper.py               # 知乎页面 DOM 提取
├── storage.py               # SQLite 数据层
├── pinchtab_client.py       # Pinchtab HTTP 后端
├── browser/
│   ├── __init__.py
│   ├── manager.py           # 浏览器生命周期管理
│   └── stealth.py           # 反检测 JS 脚本
└── cookies/
    ├── __init__.py
    └── manager.py           # Cookie 管理与提取
```

## 技术栈

- **Python 3.9+**
- **Playwright** — 浏览器自动化
- **FastMCP (mcp)** — MCP 协议服务器
- **pycookiecheat / rookiepy** — Chrome cookie 提取
- **aiohttp** — Pinchtab HTTP 客户端
- **SQLite** — 本地数据持久化
