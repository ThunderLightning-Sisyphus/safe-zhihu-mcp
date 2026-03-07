# zhihu-mcp 项目规划

## 目标

构建一个知乎 MCP (Model Context Protocol) 服务器，使 AI Agent 能够与知乎网站交互——抓取用户动态、查询存储数据、检查登录状态等。

## 架构设计

参考两个已有项目：

- **xiaohongshu-mcp**（Go）— 提供架构模式：`NewBrowser()` → cookie 加载 → 页面操作 → `saveCookies()` 的生命周期设计
- **zhihu_monitor**（Python）— 提供知乎特定逻辑：stealth 反检测、安全验证处理、MCP 工具定义

### 系统架构

```
┌─────────────┐     MCP/stdio      ┌──────────────┐    Playwright     ┌──────────────┐
│   AI Agent   │◄──────────────────►│  mcp_server  │◄────────────────►│   Chromium    │
│              │                    │    .py       │                  │  (headless)   │
└─────────────┘                    └──────┬───────┘                  └──────┬───────┘
                                          │                                 │
                                          ▼                                 ▼
                                   ┌──────────────┐                  ┌──────────────┐
                                   │   SQLite DB   │                  │  zhihu.com   │
                                   │  (activities) │                  │              │
                                   └──────────────┘                  └──────────────┘
```

## 模块规划

### 已完成

| 模块 | 文件 | 说明 |
|------|------|------|
| 浏览器管理 | `browser/manager.py` | Playwright 生命周期管理，persistent/non-persistent 上下文，cookie 加载/保存，session 预热，安全验证处理 |
| 反检测注入 | `browser/stealth.py` | 两级 JS 注入脚本：基础（隐藏 webdriver、伪装 plugins/languages）和进阶（Canvas 噪声、WebGL 厂商欺骗、硬件指纹伪装） |
| 配置管理 | `config.py` | `BrowserConfig` / `Config` 数据类，支持 JSON 文件、环境变量 `ZHIHU_MCP_CONFIG`、默认值 |
| 异常定义 | `errors.py` | `ZhihuMCPError` 基类及子类：`LoginRequiredError`、`SecurityChallengeError`、`CookieError`、`BrowserError` |
| Cookie 模块 | `cookies/__init__.py` | 模块占位，声明导出 `CookieManager` 和 `ChromeCookieExtractor` |
| 依赖声明 | `requirements.txt` | playwright, mcp, pycookiecheat, rookiepy |

### 待实现

| 优先级 | 模块 | 文件 | 说明 |
|--------|------|------|------|
| P0 | Cookie 管理实现 | `cookies/manager.py` | `CookieManager`：JSON 文件读写、过期检测、知乎关键 cookie（z_c0, d_c0）验证；`ChromeCookieExtractor`：从本机 Chrome 提取已有 cookie |
| P0 | MCP Server | `mcp_server.py` | FastMCP 服务器入口，暴露工具和资源，stdio 传输 |
| P0 | 网页爬取 | `scraper.py` | DOM 提取逻辑——解析知乎用户活动页 `/people/{token}/activities`，提取标题、链接、摘要、作者、时间 |
| P1 | 数据存储 | `storage.py` | SQLite 数据库层——活动去重、持久化、按时间/用户查询 |
| P1 | MCP 工具 | (在 mcp_server.py 中) | `get_activities`（实时爬取）、`get_new_since`（数据库查询）、`get_db_stats`（统计）、`cookie_status`（登录检测） |
| P1 | MCP 资源 | (在 mcp_server.py 中) | `zhihu://config`（配置）、`zhihu://cookies`（cookie 状态） |
| P2 | 定时监控 | `monitor.py` | 后台定时轮询配置的用户列表 |
| P2 | Pinchtab 集成 | `pinchtab_client.py` | 可选的 HTTP 后端，通过 Pinchtab 守护进程操控浏览器，绕过更严格的反检测 |

## 目标文件结构

```
zhihu-mcp/
├── PLAN.md                  # 本文件：项目规划
├── README.md                # 项目说明
├── requirements.txt         # Python 依赖
├── config.py                # 配置管理
├── errors.py                # 自定义异常
├── mcp_server.py            # MCP 服务器入口
├── scraper.py               # 知乎页面 DOM 提取
├── storage.py               # SQLite 数据层
├── monitor.py               # 定时后台监控
├── browser/
│   ├── __init__.py
│   ├── manager.py           # 浏览器生命周期管理
│   └── stealth.py           # 反检测 JS 脚本
├── cookies/
│   ├── __init__.py
│   └── manager.py           # Cookie 管理与提取
├── config.json.example      # 配置文件示例
└── cookies.json              # 运行时 cookie 存储（gitignore）
```

## 技术栈

- **Python 3.10+**
- **Playwright** — 浏览器自动化
- **FastMCP (mcp)** — MCP 协议服务器
- **pycookiecheat / rookiepy** — 从本机 Chrome 提取 cookie
- **SQLite** — 本地数据持久化

## 参考项目

- `xiaohongshu-mcp/` — 同目录下的小红书 MCP 项目（Go 实现）
- `zhihu_monitor/` — 同目录下的知乎监控项目（Python 实现，含完整 MCP 工具）
