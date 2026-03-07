# zhihu-mcp

MCP for 知乎/zhihu.com。

让 AI Agent 能够搜索知乎内容、阅读问题和回答、分析评论区、追踪用户动态 — 通过标准 MCP 协议接入任何 AI 客户端。

## 项目简介

**主要功能**

<details>
<summary><b>1. 搜索知乎内容</b></summary>

按关键词搜索知乎，支持按相关性、时间、热度排序，可过滤内容类型（问题/回答/文章）。

基于知乎内部 API，比 DOM 抓取更稳定可靠。

</details>

<details>
<summary><b>2. 获取问题详情</b></summary>

获取知乎问题的完整信息：
- 问题标题、描述、话题标签
- 关注数、浏览数、回答数
- Top 10 高赞回答列表（含作者、摘要、点赞数、链接）

</details>

<details>
<summary><b>3. 阅读回答全文</b></summary>

获取指定回答的完整内容：
- 作者名称和简介
- 回答正文（图片替换为 `[图片]` 标记）
- 点赞数、评论数
- 发布/编辑时间

</details>

<details>
<summary><b>4. 阅读专栏文章</b></summary>

获取知乎专栏（zhuanlan.zhihu.com）文章全文，包括作者、点赞数、评论数。

</details>

<details>
<summary><b>5. 获取评论区</b></summary>

获取回答或文章的评论列表，包括评论内容和作者。支持自定义加载数量。

</details>

<details>
<summary><b>6. 查看用户资料</b></summary>

获取知乎用户主页信息：昵称、简介、关注数、粉丝数、获赞数、回答数、文章数等。

</details>

<details>
<summary><b>7. 追踪用户动态</b></summary>

实时抓取用户最近的活动（回答问题、发表文章、赞同内容等），自动存入本地 SQLite 数据库，支持历史查询。

</details>

**风险说明**

本项目使用 Playwright 驱动无头浏览器访问知乎，注入 stealth 反检测脚本。正常使用频率下（不频繁大量请求），风险较低。建议：
- 使用已登录的 Cookie，避免频繁登录操作
- 控制调用频率，避免短时间内大量请求
- 本项目基于学习目的，禁止用于违法行为

## 1. 快速开始

### 1.1. 安装

需要 **Python 3.10+**（`mcp` 包要求）。

```bash
# 克隆项目
git clone https://github.com/ay/zhihu-mcp.git
cd zhihu-mcp

# 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 1.2. 配置 Cookie

知乎需要登录才能正常使用。将浏览器中的知乎 Cookie 导出为 `cookies.json`（Playwright 格式），放在项目根目录。

**获取方式：**

1. 使用浏览器扩展（如 EditThisCookie、Cookie-Editor）导出
2. 从其他知乎项目（如 zhihu_monitor）复制
3. 确保包含 `z_c0`（认证 token）和 `d_c0`（设备 token）

### 1.3. 启动 MCP 服务

```bash
# 默认：无头模式
python3 mcp_server.py

# 如果需要看到浏览器界面（调试用）
HEADLESS=false python3 mcp_server.py
```

### 1.4. 验证

```bash
# 运行内置自测
python3 mcp_server.py --test
```

## 2. MCP 客户端接入

本服务使用 **stdio** 传输协议（标准输入/输出），兼容所有支持 stdio MCP 的客户端。

<details>
<summary><b>Claude Code CLI</b></summary>

```bash
claude mcp add zhihu-mcp -- /path/to/zhihu-mcp/venv/bin/python3 /path/to/zhihu-mcp/mcp_server.py
```

</details>

<details>
<summary><b>Claude Desktop</b></summary>

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "zhihu-mcp": {
      "command": "/path/to/zhihu-mcp/venv/bin/python3",
      "args": ["/path/to/zhihu-mcp/mcp_server.py"],
      "env": {
        "HEADLESS": "true"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Cursor</b></summary>

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "zhihu-mcp": {
      "command": "/path/to/zhihu-mcp/venv/bin/python3",
      "args": ["/path/to/zhihu-mcp/mcp_server.py"],
      "env": {
        "HEADLESS": "true"
      }
    }
  }
}
```

</details>

<details>
<summary><b>VSCode</b></summary>

在项目根目录创建 `.vscode/mcp.json`：

```json
{
  "servers": {
    "zhihu-mcp": {
      "command": "/path/to/zhihu-mcp/venv/bin/python3",
      "args": ["/path/to/zhihu-mcp/mcp_server.py"],
      "env": {
        "HEADLESS": "true"
      }
    }
  }
}
```

</details>

<details>
<summary><b>OpenClaw（通过 MCPorter）</b></summary>

```bash
# 安装 MCPorter（如未安装）
npm i -g mcporter

# 添加 zhihu-mcp 到 MCPorter 配置
npx mcporter config add zhihu-mcp /path/to/zhihu-mcp/venv/bin/python3 /path/to/zhihu-mcp/mcp_server.py

# 验证
npx mcporter list zhihu-mcp
```

或直接编辑 MCPorter 配置文件（通常在 `~/.config/mcporter/config.json` 或 OpenClaw 项目的 `config/mcporter.json`）：

```json
{
  "mcpServers": {
    "zhihu-mcp": {
      "command": "/path/to/zhihu-mcp/venv/bin/python3",
      "args": ["/path/to/zhihu-mcp/mcp_server.py"],
      "env": {
        "HEADLESS": "true",
        "TMPDIR": "/tmp"
      }
    }
  }
}
```

</details>

<details>
<summary><b>其他 MCP 客户端</b></summary>

任何支持 stdio MCP 协议的客户端都可以接入。核心配置：

- **command**: `python3`（或 venv 中的 python 路径）
- **args**: `["/path/to/zhihu-mcp/mcp_server.py"]`
- **transport**: `stdio`

</details>

## 3. 可用 MCP 工具

连接成功后，可使用以下 12 个 MCP 工具：

### 内容搜索与浏览

| 工具 | 说明 | 关键参数 |
|------|------|----------|
| `search_content` | 搜索知乎内容 | `keyword`（必需）, `sort`（relevance/newest/most_upvoted）, `content_type`（all/question/article/answer）, `count` |
| `get_question_detail` | 获取问题详情 + Top 回答列表 | `question_id`（必需） |
| `get_answer_detail` | 获取回答完整内容 | `question_id`（必需）, `answer_id`（必需） |
| `get_article_detail` | 获取专栏文章全文 | `article_id`（必需） |
| `get_comments` | 获取评论列表 | `url`（必需，内容页完整 URL）, `count` |

### 用户相关

| 工具 | 说明 | 关键参数 |
|------|------|----------|
| `user_profile` | 获取用户主页信息 | `token`（必需，URL 中的用户标识，如 `xu-ze-qiu`） |
| `get_activities` | 实时抓取用户动态（会启动浏览器） | `user`（必需）, `count` |
| `get_new_since` | 查询本地数据库中的历史动态（不爬取） | `hours`, `user` |
| `get_db_stats` | 数据库统计信息 | 无 |

### 认证管理

| 工具 | 说明 | 关键参数 |
|------|------|----------|
| `check_login_status` | 检查登录状态，返回用户名 | 无 |
| `cookie_status` | Cookie 文件状态检查 | 无 |
| `delete_cookies` | 删除 Cookie 文件，重置登录 | 无 |

## 4. OpenClaw Skills

预置的高级技能，将多个 MCP 工具组合成完整的工作流：

| Skill | 说明 |
|-------|------|
| [research-on-zhihu](skills/research-on-zhihu/SKILL.md) | 知乎话题研究 — 搜索 + 阅读高赞回答 + 分析评论 → 输出研究报告 |
| [analyze-zhihu-question](skills/analyze-zhihu-question/SKILL.md) | 问题深度分析 — 获取问题详情 + 逐个阅读回答 → 输出观点分布 |
| [analyze-zhihu-answer](skills/analyze-zhihu-answer/SKILL.md) | 回答深度分析 — 回答全文 + 评论区讨论 → 输出可信度评估 |
| [track-zhihu-user](skills/track-zhihu-user/SKILL.md) | 用户追踪 — 资料 + 动态抓取 → 输出用户画像和活跃领域 |

### 使用示例

```
帮我研究一下知乎上关于"大模型Agent"的讨论
```

```
分析这个知乎问题：https://www.zhihu.com/question/38215616
```

```
看看知乎用户 xu-ze-qiu 最近在做什么
```

```
帮我看看这个回答的评论区怎么说：https://www.zhihu.com/question/38215616/answer/123456789
```

## 5. 架构

```
┌─────────────┐     MCP/stdio      ┌──────────────┐    Playwright     ┌──────────────┐
│   AI Agent   │◄──────────────────►│  mcp_server  │◄────────────────►│   Chromium    │
│              │                    │              │   (headless)      │  + stealth    │
│ Claude Code  │                    │   12 tools   │                   └──────┬───────┘
│ Cursor       │                    └──────┬───────┘                          │
│ OpenClaw     │                           │                                  ▼
│ ...          │                    ┌──────┴───────┐                  ┌──────────────┐
└─────────────┘                    │   SQLite DB   │                  │  zhihu.com   │
                                   │  (活动历史)    │                  └──────────────┘
                                   └──────────────┘
```

**工作原理：**
1. AI Agent 通过 MCP stdio 协议调用工具
2. `mcp_server.py` 接收请求，驱动 Playwright 无头浏览器
3. 浏览器注入 stealth 反检测脚本，访问知乎页面
4. 搜索功能使用知乎内部 API（`/api/v4/search_v3`），更稳定
5. 其他功能通过 DOM 提取页面数据
6. 用户动态自动存入 SQLite，支持历史查询

## 6. 项目结构

```
zhihu-mcp/
├── mcp_server.py            # MCP 服务器入口（12 个工具定义）
├── scraper.py               # 知乎页面抓取（DOM 提取 + 内部 API）
├── config.py                # 配置管理
├── storage.py               # SQLite 数据层
├── errors.py                # 自定义异常
├── pinchtab_client.py       # Pinchtab HTTP 后端（备用）
├── requirements.txt         # Python 依赖
├── browser/
│   ├── manager.py           # 浏览器生命周期管理
│   └── stealth.py           # 反检测 JS 脚本注入
├── cookies/
│   └── manager.py           # Cookie 加载与持久化
└── skills/                  # OpenClaw 高级技能
    ├── research-on-zhihu/
    ├── analyze-zhihu-question/
    ├── analyze-zhihu-answer/
    └── track-zhihu-user/
```

## 7. 常见问题

**Q: Cookie 过期了怎么办？**

重新从浏览器导出 Cookie，替换 `cookies.json`。关键 cookie `z_c0` 通常有效期约 6 个月。

**Q: 搜索结果为空？**

搜索功能使用知乎内部 API，需要有效的登录 Cookie。请先用 `check_login_status` 确认登录状态。

**Q: 浏览器启动失败？**

确保已运行 `playwright install chromium` 安装浏览器。macOS 上如果遇到沙箱问题，设置环境变量 `TMPDIR=/tmp`。

**Q: 和 zhihu_monitor 项目的关系？**

zhihu-mcp 是 zhihu_monitor 的升级版，增加了搜索、内容详情、评论、用户资料等功能，并以标准 MCP 协议提供服务。

## 技术栈

- **Python 3.10+**
- **[Playwright](https://playwright.dev/python/)** — 浏览器自动化 + stealth 反检测
- **[FastMCP (mcp)](https://github.com/jlowin/fastmcp)** — MCP 协议服务器框架
- **SQLite** — 本地数据持久化

## License

MIT
