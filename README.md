# Safe Zhihu MCP

`safe-zhihu-mcp` 是 [`alizeeblack-code/zhihu-mcp`](https://github.com/alizeeblack-code/zhihu-mcp)
的安全只读派生版。它通过独立的 Edge/Chrome 浏览器资料访问知乎，不需要知乎开放平台
Access Secret，也不会读取或导出日常浏览器 Cookie。

## 能力

- 搜索问题、回答和文章，支持排序与类型筛选
- 读取问题信息和可见高赞回答
- 读取回答全文与专栏文章全文
- 读取一级评论和楼中楼回复
- 读取用户公开资料与近期公开动态
- 用户明确要求时，将动态保存到本地 SQLite 供后续查询

## 硬性安全边界

- MCP 中不存在发布、编辑、评论、回复、点赞、关注、上传或删除工具。
- 登录只能由用户在独立可见浏览器中亲自完成。
- 不读取 Edge/Chrome 日常资料，不导出 `cookies.json`。
- 浏览器沙箱与 HTTPS 验证保持启用，拒绝跨域重定向。
- 主页面只能导航到 `zhihu.com` 和 `zhuanlan.zhihu.com`。
- 所有 ID、用户名、关键词和 URL 均经过严格验证。
- 单并发访问，最短间隔 3 秒，每小时最多 60 次、每天最多 200 次。
- 输出限制为 500,000 字符，浏览器下载被禁用。
- 运行数据保存在操作系统用户数据目录，不进入仓库。

这些措施不能消除知乎验证码、限流或账号限制风险。建议使用副号并控制使用频率。

## 安装

```text
uv tool install .
uv tool run --from playwright playwright install chromium
safe-zhihu-login
```

第三步会打开独立浏览器。请亲自登录知乎，成功后回到终端按 Enter。

## MCP 启动

```text
safe-zhihu-mcp
```

可用工具：

- `search_content`
- `get_question_detail`
- `get_answer_detail`
- `get_article_detail`
- `get_comments`
- `get_comment_replies`
- `user_profile`
- `get_activities`
- `get_new_since`
- `check_login_status`

`get_activities(..., persist=false)` 默认不保存。只有显式传入 `persist=true` 才写入本地数据库。

## 开发验证

```text
uv sync --extra dev
uv run pytest -q
```

## 许可证与来源

本项目保留原项目 MIT License 和作者版权。安全改造不代表知乎官方认可，也不改变知乎
网站与内容的使用规则。
