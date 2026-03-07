# zhihu-mcp

知乎 MCP (Model Context Protocol) 服务器，使 AI Agent 能够与知乎交互 — 搜索内容、查看问题/回答/文章详情、获取评论、抓取用户动态等。

## 功能

| MCP 工具 | 说明 |
|----------|------|
| `search_content` | 按关键词搜索知乎内容，支持排序和类型过滤 |
| `get_question_detail` | 获取问题详情（标题、描述、回答数、关注数、Top 回答） |
| `get_answer_detail` | 获取回答详情（正文、作者、点赞数、评论数） |
| `get_article_detail` | 获取专栏文章详情 |
| `get_comments` | 获取回答/文章的评论列表 |
| `user_profile` | 获取用户主页信息 |
| `get_activities` | 实时爬取指定用户的活动动态 |
| `get_new_since` | 查询数据库中最近 N 小时的活动 |
| `get_db_stats` | 数据库统计 |
| `cookie_status` | 检查 cookie 和登录状态 |
| `check_login_status` | 完善的登录状态检查 |
| `delete_cookies` | 重置登录状态 |

## OpenClaw Skills

预置的高级技能，供 OpenClaw 等 AI Agent 平台调用：

| Skill | 说明 |
|-------|------|
| [research-on-zhihu](skills/research-on-zhihu/SKILL.md) | 知乎话题研究 — 搜索 + 阅读高赞回答 + 分析评论 → 输出研究报告 |
| [analyze-zhihu-question](skills/analyze-zhihu-question/SKILL.md) | 知乎问题深度分析 — 获取问题详情 + 逐个阅读回答 → 输出观点分布 |
| [track-zhihu-user](skills/track-zhihu-user/SKILL.md) | 知乎用户追踪 — 用户资料 + 动态抓取 → 输出用户画像和动态报告 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置 Cookie

将知乎登录后的 cookie 导出为 `cookies.json`（Playwright 格式），放在项目根目录。

可以从浏览器扩展（如 EditThisCookie）导出，或从 `zhihu_monitor` 等项目复制。

### 3. 运行 MCP 服务器

```bash
python3 mcp_server.py
```

### 4. 接入 AI Agent

在 Claude Desktop 或其他 MCP 客户端中配置：

```json
{
  "mcpServers": {
    "zhihu": {
      "command": "python3",
      "args": ["/path/to/zhihu-mcp/mcp_server.py"]
    }
  }
}
```

## 架构

```
┌─────────────┐     MCP/stdio      ┌──────────────┐    Playwright     ┌──────────────┐
│   AI Agent   │◄──────────────────►│  mcp_server  │◄────────────────►│   Chromium    │
└─────────────┘                    └──────┬───────┘   (headless)      └──────┬───────┘
                                          │                                 │
                                          ▼                                 ▼
                                   ┌──────────────┐                  ┌──────────────┐
                                   │   SQLite DB   │                  │  zhihu.com   │
                                   └──────────────┘                  └──────────────┘
```

## 项目结构

```
zhihu-mcp/
├── mcp_server.py            # MCP 服务器入口
├── scraper.py               # 知乎页面 DOM 提取
├── config.py                # 配置管理
├── storage.py               # SQLite 数据层
├── errors.py                # 自定义异常
├── pinchtab_client.py       # Pinchtab HTTP 后端（备用）
├── browser/
│   ├── manager.py           # 浏览器生命周期管理
│   └── stealth.py           # 反检测 JS 脚本
├── cookies/
│   └── manager.py           # Cookie 管理与提取
└── skills/
    ├── research-on-zhihu/   # 知乎话题研究
    ├── analyze-zhihu-question/ # 知乎问题深度分析
    └── track-zhihu-user/    # 知乎用户追踪
```

## 技术栈

- **Python 3.9+**
- **Playwright** — 浏览器自动化 + stealth 反检测
- **FastMCP (mcp)** — MCP 协议服务器
- **SQLite** — 本地数据持久化
