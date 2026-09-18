<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>面向 AI 编程工具的通用 AI 路由器与多供应商统一网关</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">支持的供应商</a> • <a href="#core-capabilities">核心能力</a> • <a href="#deployment">部署</a> • <a href="#sdk-surfaces">SDK 接入</a> • <a href="#architecture">架构设计</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <b>中文（简体）</b> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

本 README 提供 15 种语言版本，功能范围一致。链接的技术指南保留原文语言。

面向编程工具的通用 AI 路由器。Polaris 提供智能自动故障转移、令牌感知上下文清理、使用量可视化和无缝格式转换，让本地 Agent、IDE 助手和自动化脚本可以通过一个稳定的 API 接口调用各种免费与付费的 LLM 算力。

> Polaris 面向个人或可信团队的自托管场景，仅支持一个 worker 和一个副本。Docker Compose、本地所有者登录、SQLite、路由及已记录的 SDK 接口是核心范围。PostgreSQL、OIDC、反向代理和外部遥测为可选功能；MongoDB 作为兼容选项保留。不支持多副本协调和 Kubernetes。 [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## 为什么选择 Polaris

现代编程工作流通常混合使用多种客户端与模型供应商：OpenAI 兼容工具、Gemini 原生 SDK、Anthropic 风格的 Agent、Google 凭据以及实验性模型路由。Polaris 位于这些客户端与模型后端之间，让每个工具继续使用其原生协议，同时由网关统一处理请求路由、重试、上下文清理和响应格式标准化。

<a id="core-capabilities"></a>

## 核心能力

- 自动故障转移，支持按请求预留、公平轮换、冷却及耗尽配额处理。
- 清理过长历史，同时保留系统指令、工具上下文和最近对话。
- 转换 OpenAI Chat Completions/Responses、Gemini 和 Anthropic Messages 协议，支持流式响应。
- 管理 OAuth 账户和 API 密钥，按提供商验证及去重。
- 按凭据维护模型目录，尊重各账户的权限。
- 记录凭据的不可用模型路由，并从 Models 页面恢复。
- 支持 SSE、伪流式及截断响应的有限重试。
- 支持均衡、优先级、加权、最低延迟和最低成本路由。
- 虚拟密钥支持日/月预算、RPM/TPM、到期时间及模型白名单。
- 按调用估算美元成本，并在仪表盘和 Prometheus 中汇总。
- 可选的提示注入检测、关键词拦截和个人信息脱敏。
- 可选的确定性响应精确匹配缓存。
- Prometheus 指标、可选 Langfuse 导出及用量追踪。
- 提供凭据、日志、配置、用量和版本管理控制台。

<a id="console-preview"></a>

## 控制台预览

截图使用隔离的离线演示环境中的虚构数据。

### 仪表盘

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — 仪表盘" />
</picture>

### 凭据

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — 控制台预览" />
</picture>

<a id="supported-providers"></a>

## 支持的供应商

目录包含 23 个提供商。可用模型和功能取决于各凭据的实际权限。

| 提供商 | 连接方式 | 服务 / 范围 |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API 密钥 | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API 密钥 | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth（设备码） | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API 密钥 | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | API 密钥 | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | 端点；API 密钥可选 | 本地 / 自托管 |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | API 密钥 | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | API 令牌 + 账户 ID | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | API 密钥 | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | API 密钥 | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | API 密钥；组织 ID 可选 | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | API / 服务密钥 | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | API 密钥 | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | 浏览器 OAuth / AWS 设备登录 / API 密钥 | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth（Meta 设备码） | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | API 密钥 | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | API 密钥 | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | API 密钥 | NVIDIA 托管推理 |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | API 密钥 + Zen/Go 套餐 | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | API 密钥 | Poolside API |

客户端使用统一的 [SDK 接口](#sdk-surfaces)。协议转换、流式及故障转移受模型能力限制；不支持的选项会被明确拒绝。在 **Providers** 中按提供商或凭据配置连接。Muse Code 与 Meta Model API 的凭据及模型命名空间相互独立。

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## 架构设计

```text
客户端工具
  OpenAI SDK | Google GenAI SDK | Anthropic SDK | IDE 集成插件
        |
        v
Polaris
  身份认证 -> 格式协议转换 -> 令牌感知清理 -> 路由分发 -> 故障转移 -> 流式输出
        |
        v
供应商适配器
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

在 Polaris 后端适配器持续演进的同时，对外的公共 API 契约保持绝对稳定。

<a id="repository-structure"></a>

## 代码仓库结构

```text
backend/       FastAPI 组合根、路由核心、协议转换器、存储层与测试用例
frontend/      管理控制台页面结构、样式、脚本及供应商图标资产
deploy/        容器定义、平台部署清单与操作系统启动脚本
docs/          架构设计说明与项目维护文档
.github/       CI 流水线、依赖自动化与贡献模板
```

详见[架构设计](../architecture.md)，了解模块边界、请求处理流程、状态归属与当前版本的发布约束。

<a id="deployment"></a>

## 部署

单机、单 worker 的 Docker Compose 是主要部署路径。请按照[安装指南](../installation.md)及[支持矩阵](../installation.md#support-matrix)操作。

基础配置不依赖外部服务，数据保存在 `polaris-data`。模板面向 `1.0.0`。仅使用已发布且版本一致的 Polaris 标签和镜像安装；若使用尚未发布的源码，请按[发布清单](../releases/1.0.0-preparation.md)构建独立的本地镜像。升级或回滚遵循[更新指南](../updating.md)，通过 `deploy/compose.advanced.yml` 按需启用高级选项。

参见[标识符约定](../migrations/polaris.md)和[故障排查](../troubleshooting.md)。原生脚本、`docker run`、Render 和 Zeabur 是兼容路径，不具备同等安装及恢复验证。发布镜像支持 `linux/amd64`；`linux/arm64` 发布仍暂停。

### 本地开发或排查：

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

打开控制台；首次设置流程与 Docker 相同：

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## 配置项

优先级为环境变量、已保存配置、默认值。[生成的配置参考](../reference/configuration.md)说明类型、分组、负责模块以及即时生效、重启生效或仅环境配置的生命周期。无效值会阻止启动并指出变量；疑似拼错的 `POLARIS_*` 名称会产生警告。

| 环境变量 | 默认值 | 用途说明 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | 绑定监听地址。 |
| `PORT` | `4283` | HTTP 端口。 |
| `HOST_PORT` | `4283` | 宿主机端口，仅供 Docker Compose 使用。 |
| `WORKERS` | `1` | 仅支持一个 worker。 |
| `POLARIS_RUNTIME_MODE` | `standalone` | 仅支持 `standalone`。 |
| `POLARIS_REPLICA_COUNT` | `1` | 仅支持一个副本。 |
| `CORS_ORIGINS` | 空 | 允许跨域调用 API 的浏览器 Origin 列表（逗号分隔）。同源控制台访问请保持为空。 |
| `CORS_ORIGIN_REGEX` | 空 | 用于匹配动态浏览器 Origin 的可选正则表达式。 |
| `API_KEY` | 自动生成 | 客户端 API 密钥，前缀为 `sk-polaris-`。 |
| `PANEL_PASSWORD` | 设置前为空 | Web 控制面板的访问密码。 |
| `SETUP_TOKEN` | 空 | 远程首次设置所需的唯一令牌，至少 24 字符；不自动生成或记录。直接 localhost 访问不需要。 |
| `SETUP_ALLOW_INSECURE_HTTP` | `false` | 仅在接受凭据和会话未加密的风险后，才启用远程 HTTP 设置。建议使用 HTTPS；仍然需要强设置令牌。 |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Web 控制台会话有效期（秒）。 |
| `PANEL_COOKIE_SECURE` | 自动 | 设为 `true` 强制仅在 HTTPS 下传输 Cookie。留空时通过 `X-Forwarded-Proto` 自动检测。 |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | 登录频率限制时间窗口（秒）。 |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | 限制窗口期内单个客户端允许的最大失败登录尝试次数。 |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | 内存中登录频率限制器追踪的最大客户端地址数量。 |
| `MAX_REQUEST_BODY_MB` | `64` | 最大 HTTP 请求体大小（MiB）。超出限制的 SDK 请求将返回对应协议的原生错误包。 |
| `TRUST_PROXY_HEADERS` | `false` | 仅在下游存在可信的反向代理且会覆写转发头时才接收客户端与协议转发头。 |
| `CREDENTIALS_DIR` | `./backend/data/creds` | 凭据存储目录。在 Docker 中需将 `/app/backend/data/creds` 挂载至宿主机卷。 |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Code Assist 后端服务地址。 |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Google Antigravity 后端服务地址。 |
| `PROXY` | 空 | 可选的 HTTP、HTTPS 或 SOCKS 代理。 |
| `RETRY_429_ENABLED` | `true` | 对速率限制和上游临时故障启用有界重试。保留旧名称以兼容既有配置。 |
| `RETRY_429_MAX_RETRIES` | `5` | 上游临时故障的最大重试次数。 |
| `RETRY_429_INTERVAL` | `1` | 临时重试的基础退避间隔（秒）。 |
| `AUTO_DISABLE` | `false` | 在发生配置的严重错误后自动禁用对应凭据。 |
| `AUTO_DISABLE_ERROR_CODES` | `403` | 逗号分隔的严重错误状态码列表。 |
| `ROUTING_STRATEGY` | `balanced` | 策略：`balanced`、`priority`、`weighted`、`least_latency`、`lowest_cost`。 |
| `PREFERRED_PROVIDER` | 空 | `priority` 策略优先选用的供应商，例如 `google_antigravity` 或 `google_ai_studio`。 |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | 供应商推理超时时间，限制在 5 到 900 秒之间。 |
| `RESPONSE_CACHE_ENABLED` | `false` | 为温度 0、非流式的确定性响应启用内存缓存。 |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | 缓存有效期，单位秒。 |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | 缓存响应数量上限。 |
| `GUARDRAILS_ENABLED` | `false` | 启用调用前防护。 |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | 对发出文本中的邮箱、银行卡及 API 密钥脱敏。 |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | 检测到提示注入时返回 HTTP 400。 |
| `GUARDRAILS_BLOCKED_KEYWORDS` | 空 | 逗号分隔的禁用关键词，不区分大小写。 |
| `PRICING_SYNC_ENABLED` | `true` | 后台更新 LiteLLM 价格；离线保留最后有效副本。 |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | 价格更新间隔：1–168 小时。 |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | 防截断流式传输的最大续写重试次数。 |
| `TOKEN_COMPRESSION_ENABLED` | `true` | 在路由至供应商前压缩超长对话历史。 |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | 触发上下文压缩的预估输入令牌阈值。 |
| `TOKEN_COMPRESSION_TARGET` | `24000` | 压缩后的预估输入令牌目标值。必须低于触发阈值。 |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | 压缩过程中必须保留的最近用户轮次最少数。 |
| `COMPATIBILITY_MODE` | `false` | 为不兼容系统消息的客户端/模型自动转换 System 消息。 |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | 在可用时返回模型的思考推理过程（reasoning）。 |
| `MONGODB_URI` | 空 | MongoDB 兼容存储。 |
| `POSTGRESQL_URI` | 空 | 可选 PostgreSQL 存储。 |
| `CODE_ASSIST_CLIENT_ID` | 内置桌面客户端 | Code Assist OAuth Client ID 的可选覆盖值。 |
| `CODE_ASSIST_CLIENT_SECRET` | 内置桌面客户端 | Code Assist OAuth Client Secret 的可选覆盖值。 |
| `ANTIGRAVITY_CLIENT_ID` | 内置桌面客户端 | Google Antigravity OAuth Client ID 的可选覆盖值，也可在供应商页面配置。 |
| `ANTIGRAVITY_CLIENT_SECRET` | 内置桌面客户端 | Google Antigravity OAuth Client Secret 的可选覆盖值，上游变更时可通过环境变量或供应商页面调整。 |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Google AI Studio Generative Language API 的可选服务地址覆盖值。 |
| `XAI_API_URL` | `https://api.x.ai/v1` | SpaceXAI Console API 密钥凭据的可选 API 服务地址覆盖值，也可在供应商页面配置。 |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Grok Build OAuth 订阅端点的可选服务地址覆盖值。 |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Grok Build OAuth Issuer 的可选覆盖值。控制台仅接受 `x.ai` 域名下的 HTTPS 主机。 |
| `XAI_CLIENT_ID` | 内置公共客户端 | Grok Build PKCE OAuth Client ID 的可选覆盖值。 |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Grok Build OAuth 与 SpaceXAI Console API 请求共享的可选 HTTP User-Agent 覆盖值。 |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | OpenAI Platform API 的可选服务地址覆盖值，也可在供应商页面配置。 |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Codex 推理与账户模型列表端点的可选覆盖值。 |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Codex 账户速率限制查询端点的可选覆盖值。 |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Codex 设备授权服务的可选服务地址覆盖值。 |
| `CODEX_CLIENT_ID` | 内置公共客户端 | Codex 设备 OAuth Client ID 的可选覆盖值。 |
| `CODEX_USER_AGENT` | 兼容 Codex CLI 的值 | Codex 请求的可选 User-Agent 覆盖值。 |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Claude Code 专用 Messages 端点。 |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Claude Code PKCE 授权端点的可选覆盖值。控制台仅接受 Anthropic 和 Claude 官方主机。 |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Claude Code Token 端点的可选覆盖值。控制台仅接受 Anthropic 和 Claude 官方主机。 |
| `CLAUDE_CLIENT_ID` | 内置公共客户端 | Claude Code PKCE OAuth Client ID 的可选覆盖值。 |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | Claude Code 专用 User-Agent。 |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Providers 中独立的 Claude Platform 端点。 |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | Claude Platform 独立 User-Agent。 |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Google Antigravity 协议级请求的可选 User-Agent 覆盖值。 |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Google Antigravity 载荷层 userAgent 的可选覆盖值。 |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | 启用需要认证的 `GET /metrics`。 |
| `METRICS_TOKEN` | 空 | Prometheus 必需的 Bearer 令牌，至少 32 个 UTF-8 字节。 |
| `OTEL_EXPORT_ENABLED` | `false` | 启用不含内容的 OTLP/HTTP 聚合数据导出。 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 空 | HTTPS 收集器地址，不允许在 URL 中嵌入凭据。 |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | 导出间隔：15–300 秒。 |
| `LANGFUSE_PUBLIC_KEY` | 空 | 与私钥共同启用 Langfuse。 |
| `LANGFUSE_SECRET_KEY` | 空 | 用于追踪的 Langfuse 私钥。 |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse 数据接收端点。 |
| `LOG_LEVEL` | `info` | 运行时日志记录级别。 |
| `LOG_MAX_MB` | `10` | 单个活动日志文件在轮转前的最大体积（MB）。 |
| `LOG_BACKUP_COUNT` | `3` | 保留的历史轮转日志文件数量。 |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | 文件日志输出路径。在 Docker 中需将 `/app/backend/data/logs` 挂载至宿主机卷。 |

### 压缩控制

全局 AI Quality 策略具有最终约束力。虚拟密钥只能继承或禁用压缩：通过 `PATCH /api/virtual-keys/{key_id}/quality-policy` 提交当前修订号，使用 `inherit` 取消密钥限制。已认证请求可设置 `x-polaris-compression: off`；省略或 `inherit` 遵循全局及密钥策略。请求不能重新启用全局禁用的压缩，也不能提高压缩强度。只删除安全的历史前缀；结构或估算不确定时原样发送。Token 数量为估算值。

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## SDK 接入

Polaris 严格按照官方 Python SDK 的标准 URL 行为进行设计。请完全参照下文方式配置客户端，网关无需任何非标准的重复路径前缀。

示例中使用虚拟模型 `polaris`。请先在控制台的“模型”页面配置其优先级回退模型链，或者直接将其替换为具体的供应商模型 ID。

### OpenAI Python SDK

将 OpenAI 的 Base URL 设置为 `/v1`，SDK 会自动在末尾追加 `/chat/completions`。

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "用一段话解释这个代码仓库。"}]
)
```

同一客户端也可以直接调用 OpenAI Responses API：

```python
response = client.responses.create(
    model="polaris",
    instructions="请简明扼要。",
    input="用一段话解释这个代码仓库。"
)

print(response.output_text)
```

Responses 兼容层支持文本输入、图片输入、非流式 Function Tool 以及 SSE 文本流式传输。对于 OpenAI 托管的内置工具、持久化响应历史以及流式函数调用，网关会明确返回错误拒绝请求，因为 Polaris 不会执行、持久化或隐式丢弃这些 OpenAI 特有的专有行为。

### Anthropic Python SDK

将 Anthropic 的 Base URL 直接指向网关根地址，SDK 会自动在末尾追加 `/v1/messages`。

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "撰写一条 Git 提交信息。"}]
)
```

### Google GenAI Python SDK

将 Google GenAI 的 Base URL 直接指向网关根地址，SDK 会自动追加默认模型路由，例如 `/v1beta/models/{model}:generateContent`。

```python
from google import genai
from google.genai import types

client = genai.Client(
    http_options={
        "base_url": "http://127.0.0.1:4283"
    },
    api_key="sk-polaris-..."
)

response = client.models.generate_content(
    model="polaris",
    contents="写一个简短的 Python 函数。",
    config=types.GenerateContentConfig(
        system_instruction="你是一个得力的编程助手。"
    )
)
```

### 支持的路由列表

Polaris 提供标准 SDK 兼容路由，无需额外的产品命名空间前缀：

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/messages`
- `GET /v1/models`
- `GET /v1beta/models`
- `POST /v1beta/models/{model}:generateContent`
- `POST /v1beta/models/{model}:streamGenerateContent`
- `POST /v1beta/models/{model}:countTokens`
- `POST /vertex/v1/chat/completions`
- `POST /vertex/v1/models/{model}:generateContent`

身份认证、请求校验、路由选择、上游调用及流式启动前的失败均使用对应 SDK 接口的原生错误格式包裹。每个 HTTP 响应均包含 `X-Request-ID` 请求标识；客户端可在该请求头传入安全标识以进行全链路追踪。当上游返回速率限制或暂时不可用时，网关将原样保留并透传 `Retry-After` 头。

<a id="model-features"></a>

## 模型特性与高级控制

控制台“模型”页面通过已启用的各供应商凭据中发现的模型，聚合构建出虚拟模型 `polaris`。只需设置一次各底层模型的优先级顺序，即可在任意支持的 SDK 中使用 `polaris`。Polaris 会在支持第一顺位模型的健康凭据之间进行负载均衡；当该模型不可用时，自动依次降级尝试后续配置的模型。具体的供应商物理模型 ID 依然保留可用，以满足需要确定性指定模型的客户端需求。保存空列表即可停用 `polaris`，这不会影响任何供应商凭据。

模型发现机制具备供应商感知能力：通用模型可由多个供应商共同支持，而专有模型仅由兼容的凭据承接。每个已验证的凭据独立保存其专属的供应商目录，路由器优先采用凭据显式声明支持的模型，而非通用的供应商类型推断。刷新目录将重新拉取当前供应商的实时可用性；不可用的配置项将保持可见，直到其恢复或被手动移除。

当上游对某个物理模型返回 `404` 时，Polaris 会在该凭据和模型作用域内记录不可用路由，而非直接禁用整个供应商。该路由将立即被临时避开，并在**不可用模型路由**列表中保持可见，直到被手动清除或该凭据重新校验通过。这避免了因单个账户的订阅权限或地域限制而影响同一供应商下的其他健康账户。若启用的凭据均未声明或推断支持所请求的模型，网关将返回明确的无兼容凭据错误，而不是将请求随机发往不匹配的供应商。

Polaris 支持在模型名称中解析特性前缀与后缀：

- `fake-streaming/{model}` 或配置的伪流式前缀，适用于强制要求 SSE 输出的客户端。
- `streaming-anti-truncation/{model}` 或配置的防截断前缀，用于长文本流式生成的自动续写恢复。
- 思考深度后缀（如 `-high`、`-medium`、`-low`、`-minimal`、`-max`），适用于支持该特性的 Gemini 系列模型。
- 联网搜索后缀（如 `-search`），适用于支持 Google Search 搜索接地的模型。

供应商适配器会在向上游发送请求前自动将这些特性标识规范化。

<a id="usage-and-cost-visibility"></a>

## 使用量与成本透明度

每次提供商尝试、重试和故障转移分别计数；追踪记录保留逻辑请求的最终结果。记录结果、凭据、提供商报告的输入/输出/缓存/推理 token、估算节省量和美元成本。缺失用量不等于实测为零。统计周期采用浏览器时区的固定边界，日视图覆盖 00:00–23:00。默认在启动时及每 24 小时更新 LiteLLM 公开价格，原子保留最后有效副本；更新失败不阻塞推理。凭据目录中的 `model_pricing.json` 优先，单价单位为每百万 token。仪表盘、`/api/virtual-keys` 和 `/metrics` 提供汇总；以提供商账单及 tokenizer 为准。

虚拟密钥支持日/月预算、RPM/TPM 滑动窗口、到期时间和 glob 模型规则。只存储 SHA-256 哈希，密钥明文仅在创建时显示。

<a id="credential-workflow"></a>

## 凭据配置工作流

1. 启动 Polaris。
2. 在 VPS 上访问 `http://你的服务器IP:4283`，或在本地开发时访问 `http://127.0.0.1:4283`。
3. 完成检查并创建所有者密码。远程首次设置前，预先配置至少 24 字符的唯一 `SETUP_TOKEN` 或 `PANEL_PASSWORD`。令牌不会自动生成或写入日志。
4. 在“供应商”页面添加账户、API 密钥或 Ollama 连接。
5. 验证凭据有效性，并在面板中监控冷却时间与错误状态。 **Credentials** (`/credentials`).
6. 将你的编程工具连接至上述支持的 API 接口之一。

添加 Google Antigravity 凭据时，Google 会在登录完成后将浏览器重定向至 `http://localhost:4283/callback`。在本地机器上，Polaris 会直接展示 OAuth 授权成功页面。在 VPS 上，由于该 `localhost` 指向用户的本地浏览器机器，页面可能无法打开；只需复制浏览器地址栏中的完整 URL，返回“供应商”页面粘贴至 `Callback URL` 框中，点击 `保存凭据` 即可。

Google AI Studio 使用 API 密钥认证而非 OAuth。在“供应商”页面添加密钥后，Polaris 将对照 Google 模型目录验证其有效性，保存为供应商凭据，并将兼容的 Gemini 或 Gemma 请求路由至该凭据。智能路由器可以在共享的 Gemini 模型上于 AI Studio 与 Google Antigravity 之间自动故障转移，同时保证专有模型仅由兼容凭据承接。

Google AI Studio 批量导入支持 JSON 文件及包含 JSON 文件的 ZIP 压缩包。JSON 文件可包含单条密钥、`api_keys` 数组或密钥对象数组：

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

文件导入是离线操作：Polaris 检查 JSON/ZIP 结构，将新密钥保存为 `unverified`，跳过重复或已存在的密钥，不连接 Google。导入的模型列表不视为已验证。格式错误会单独报告，不泄露密钥。之后请主动执行凭证验证/模型发现；**Test model** 单独检查推理权限，可能消耗配额或产生费用。

Grok Build 支持 PKCE OAuth 凭据，而 SpaceXAI Console 支持 API 密钥。SpaceXAI Console 密钥在保存前会对照 SpaceXAI Console API 模型目录进行验证。对于 Grok Build OAuth，Polaris 会生成授权链接；授权完成后，复制授权页面展示的授权码并粘贴至表单中。当存在 Refresh Token 时系统会自动刷新访问令牌，且两种凭据类型均仅暴露各自当前目录声明的模型。在“凭据”页面，可查询 Grok Build OAuth 账户的月度额度消耗情况，以及 xAI 提供时的周度使用量。该账户级账单视图不支持 SpaceXAI Console API 密钥。

Codex 使用 OpenAI 设备授权流程。在“供应商”页面生成设备代码，打开展示的验证网址，输入代码完成登录，然后返回检查授权状态。Polaris 将保存 Codex 返回的账户级模型目录，在需要时自动刷新 OAuth 访问令牌，并通过 Codex Responses 传输协议转发兼容请求。OpenAI Platform 使用 API 密钥认证；密钥在保存前均通过账户模型目录进行有效性校验。两款产品均支持 JSON 和 ZIP 导入，并具备供应商特定的校验与去重能力。

Claude Code 使用 Anthropic 的 PKCE OAuth 流程。生成授权链接，完成授权后将返回的授权码粘贴回“供应商”页面。Claude Platform 接收 Anthropic API 密钥。两款产品均可发现每个凭据支持的模型列表，使用 Anthropic Messages 传输协议，在可能时自动刷新 Claude Code 访问令牌，并支持带校验的 JSON 或 ZIP 导入。

Muse Code 使用 Meta 设备授权。在 **Providers → Muse Code** 获取链接，在 Meta 批准设备码，再返回 **Save credential** 保存。直接连接，无需 CLI、Linux 或 VPS；模型前缀为 `muse-code/`，可设置显示名称。套餐、会话/周配额、重置时间和观测时间仅在提供商返回时显示；缺失不代表剩余 100%。刷新会检查订阅并使用当前会话获取推理密钥；会话失效时需重新登录。

Kiro 支持 Google/GitHub 浏览器 OAuth、AWS 设备授权和 API 密钥。高级字段随认证方式变化：运行区域、AWS 令牌区域/起始 URL，或 API 密钥的配置文件 ARN。

Ollama 连接按端点配置，并可包含用于受保护或云端服务器的可选 Bearer API 密钥。Polaris 通过 `/api/tags` 发现可用模型，并通过 `/api/chat` 执行推理路由。当 Polaris 运行在 Docker 中时，`localhost` 指向容器本身；请使用宿主机网关地址或网络可达的其他 Ollama 端点。

凭据池完整导入与 Google Antigravity 批量导入支持最大 10 MB 的压缩包、最多 500 个文件、单个凭据文件最大 2 MB 以及解压后最大 25 MB 的数据量。Google AI Studio、OpenAI、Anthropic 和 Ollama 供应商单项导入采用更严格的限制：单个导入文件最大 2 MB、最多 200 条 JSON 记录、解压后最大 5 MB。

**Credentials**（`/credentials`）按提供商分组账户与密钥。管理弹窗显示身份、模型、状态和可用操作。OAuth 可能返回套餐、额度及按时间窗口或模型划分的配额。API 密钥不会自动提供邮箱、套餐或账单；缺失信息显示为不可用。

**Download ZIP** 导出凭据；**Import ZIP** 按提供商验证、去重并逐条报告错误。导入成功或发现模型目录不证明具有推理权限；**Test model** 会发起真实请求，可能消耗配额或产生费用。压缩包包含敏感信息。完整 SQLite 数据及配置备份应使用 **Settings** 中的加密流程。

Google Antigravity 凭据命名为 `google-antigravity-{account_fingerprint}.json`，指纹派生自规范化的账户邮箱且不泄露明文。Google AI Studio 凭据命名为 `google-ai-studio-{key_fingerprint}.json`，Grok Build OAuth 凭据命名为 `grok-{account_fingerprint}.json`，SpaceXAI Console 凭据命名为 `xai-console-{key_fingerprint}.json`，Codex 凭据命名为 `openai-codex-{account_fingerprint}.json`，OpenAI Platform 凭据命名为 `openai-platform-{key_fingerprint}.json`，Claude Code 凭据命名为 `claude-code-{account_fingerprint}.json`，Claude Platform 凭据命名为 `claude-platform-{key_fingerprint}.json`，Ollama 连接命名为 `ollama-{connection_fingerprint}.json`。旧版 `provider_*.json` 和 `xai-grok-*.json` 凭据保持向下兼容，并在导出时自动转换为标准规范名称。

凭据模式名称：

- `code_assist`：标准 Code Assist 凭据池。
- `provider`：通用供应商后端凭据池。

<a id="storage"></a>

## 数据存储

推荐使用 SQLite。Compose 将 `/app/backend/data` 保存在 `polaris-data`；直接使用 Docker 时，将 `/app/backend/data/creds` 和 `/app/backend/data/logs` 挂载到 `/opt/polaris/creds`、`/opt/polaris/logs` 等持久目录。

PostgreSQL 为可选项；MongoDB 保留兼容支持，直接工作，无需 Redis。二者只配置一个。初始化失败会阻止启动，不会静默回退 SQLite。外部数据库不提供横向扩容：仍仅支持一个 worker、一个副本。可移植加密备份仅支持 SQLite，不支持后端间在线迁移。

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[数据存储](../storage.md)

支持通过环境变量导入凭据。可在控制台操作，或将以下变量之一设置为原始 JSON 字符串，亦可使用带 `_B64` 后缀的 Base64 编码字符串：

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

负载内容可以是单个凭据对象、凭据数组或 `{ "credentials": [...] }` 结构。

<a id="development"></a>

## 开发指南

本节面向项目贡献者及本地调试。生产环境部署请使用带有持久化宿主机卷的 Docker 方案。

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

[质量门禁](../quality-gates.md)区分任务、阶段和发布验证。`python tools/quality_gate.py --list-suites` 也列出可选的外部实时检查。[兼容性约定](../compatibility.md)覆盖 SDK/管理路由、迁移、模式和示例。

所有代码检查均通过后启动服务：

```bash
python backend/main.py
```

生产运行基线为 Python 3.12，CI 自动化测试覆盖 Python 3.12 和 3.14。有关 Pull Request 提交流程与代码评审标准，请参阅[贡献指南](../../CONTRIBUTING.md)。

<a id="deployment-notes"></a>

## 部署注意事项

- 切勿提交包含凭据的 JSON 文件或 `.env` 文件。
- 为客户端集成配置专用的 `API_KEY`，并为控制台访问设置独立的 `PANEL_PASSWORD`。
- 严格限制对持久化凭据数据卷或外部数据库的访问权限，并在平台层启用静态落盘加密；路由器必须能够解密读取供应商令牌。
- 当服务暴露于非 localhost 环境时，务必将 Polaris 置于配置了 TLS 的反向代理之后。
- 配置反向代理保留 `Host` 请求头并传递 `X-Forwarded-Proto`；在确认全程 HTTPS 终止时设置 `PANEL_COOKIE_SECURE=true`。
- 仅当服务完全仅经由会重写 `X-Forwarded-For` 和 `X-Forwarded-Proto` 的可信代理访问时，才设置 `TRUST_PROXY_HEADERS=true`。
- 使用 `GET /health` 进行进程存活探针检查，使用 `GET /ready` 进行包含存储层感知的就绪探针检查。
- 外部遥测需主动启用：Prometheus 要求 `PROMETHEUS_EXPORT_ENABLED` 和强 `METRICS_TOKEN`；OpenTelemetry 只导出聚合数据，不导出提示或响应内容。参见[可观测性](../observability.md)。
- Docker 镜像仅在启动初期以 root 权限修复挂载数据目录的权限归属，随后降权切换至无特权的 `gateway` 用户运行。
- 当浏览器客户端需要跨域访问时，请将 `CORS_ORIGINS` 显式设置为受信任的来源。
- 升级或迁移 SQLite 前使用[经过认证的加密备份](../backup-and-restore.md)，并将压缩包及口令保存在 `polaris-data` 之外。
- Docker 镜像发布使用仓库机密 `DOCKERHUB_USERNAME` 与 `DOCKERHUB_TOKEN` 推送至 Docker Hub，并使用内置的 `GITHUB_TOKEN` 推送至 GitHub Packages（`ghcr.io/nguywnben/polaris`）。仅在发布到自定义 Docker Hub 镜像名称时才设置可选的 `IMAGE_NAME` 变量。
- 在 1.x 系列版本中，请保持 `WORKERS=1` 和单应用副本；外部存储无法替代分布式协同机制。
- 请使用标准规范的 `/api/credentials` 管理路由。Beta 阶段的 `/api/creds` 别名已在 1.0.0 中彻底移除。
- 在迁移 Beta 版本部署前，请先查阅[升级至 1.0 指南](../upgrading-to-1.0.md)。
- 升级现有运行实例或回滚版本时，请参考[更新指南](../updating.md)。
- 在打 Tag 或发布镜像前，请对照维护的[发布核对清单](../release-checklist.md)逐项确认。
- 请根据实际用量配额合理制定日志保留与凭据轮转策略。
- 一旦代码仓库或云平台安全扫描告警凭据泄漏，请立即吊销并轮换该凭据。
- Render 部署清单使用的是带有持久化硬盘的付费服务。Render 的免费服务使用临时文件系统，仅适合一次性测试体验。

<a id="community-and-project-health"></a>

## 社区与项目健康度

- 在提交 Pull Request 前请阅读[贡献指南](../../CONTRIBUTING.md)。
- 报告安全漏洞请通过[安全政策](../../SECURITY.md)中注明的私密渠道提交。
- 查看[更新日志](../../CHANGELOG.md)了解各版本的详细变更。
- 在参与本项目的所有相关活动中均须遵守[行为准则](../../CODE_OF_CONDUCT.md)。

<a id="acknowledgements-inspirations"></a>

## 致谢与灵感来源

Polaris 站在开源 AI 路由、可观测性与网关社区的坚实肩膀之上。我们向以下项目的创作者与维护者致以由衷的敬意与感谢：

| 项目 | 项目描述 | Stars |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | 多供应商密钥管理与基于 Web 的 API 聚合架构灵感来源 | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | 面向 AI 编程 CLI 的开创性多协议代理与格式转换层 | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | 行业标杆级的统一 LLM 代理、负载均衡与故障转移路由 | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | 极速 AI 网关架构设计、路由策略及高弹性容灾模式 | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | 开源 LLM 工程化平台、调用追踪、系统可观测性与指标采集 | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## 开源许可证

Polaris 基于 [MIT 开源许可证](../../LICENSE) 发布。
