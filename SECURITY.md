# Security

## Credential model

The project never accepts, displays, exports, or serializes Zhihu cookies. Authentication
state remains inside a dedicated persistent Playwright browser profile created for this
project. Do not replace that directory with a daily-browser profile.

## Network and tool model

The MCP catalog is read-only. Main-frame navigation is restricted to supported Zhihu HTTPS
hosts. Downloads, insecure TLS, browser `--no-sandbox`, arbitrary URLs, arbitrary local paths,
and arbitrary HTTP forwarding are intentionally unsupported.

## Reporting

Do not include cookies, profile archives, screenshots containing personal information, or
account identifiers in public issues. Revoke the Zhihu session from account settings if the
local browser profile may have been exposed.

