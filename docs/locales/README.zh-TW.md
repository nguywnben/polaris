<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>面向 AI 程式設計工具的通用 AI 路由器與多供應商統一閘道</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">支持的供应商</a> • <a href="#core-capabilities">核心能力</a> • <a href="#deployment">部署</a> • <a href="#sdk-surfaces">快速上手 SDK 接入</a> • <a href="#architecture">架構設計</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <b>中文（繁體）</b> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

本 README 提供 15 種語言版本，功能範圍一致。連結的技術指南保留原文語言。

面向程式設計工具的通用 AI 路由器。Polaris 提供智慧自動容錯移轉、權杖感知上下文清理、使用量視覺化與無縫格式轉換，讓本地 Agent、IDE 助手與自動化腳本能透過單一穩定的 API 介面調用各類免費與付費的 LLM 算力。

> Polaris 適用於個人或可信任團隊的自行託管環境，僅支援一個 worker 和一個副本。核心包含 Docker Compose、本機擁有者登入、SQLite、路由與已記錄的 SDK 介面。PostgreSQL、OIDC、反向代理與外部遙測為選用功能；MongoDB 保留相容支援。不支援多副本協調及 Kubernetes。 [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## 為什麼選擇 Polaris

現代程式設計工作流通常混合使用多種客戶端與模型供應商：OpenAI 相容工具、Gemini 原生 SDK、Anthropic 風格的 Agent、Google 憑證以及實驗性模型路由。Polaris 位於這些客戶端與模型後端之間，讓每個工具能繼續使用其原生協定，同時由閘道統一處理請求路由、重試、請求清理與回應格式標準化。

<a id="core-capabilities"></a>

## 核心能力

- 自動容錯移轉，支援逐請求保留、公平輪替、冷卻及配額耗盡處理。
- 精簡過長歷史，同時保留系統指令、工具脈絡與最近對話。
- 轉換 OpenAI Chat Completions/Responses、Gemini 和 Anthropic Messages 協定，含串流回應。
- 管理 OAuth 帳戶與 API 金鑰，依供應商驗證及去重。
- 依憑證建立模型目錄，遵循帳戶權限。
- 記錄憑證的不可用模型路由，並由 Models 頁面復原。
- 支援 SSE、模擬串流與截斷回應的有限重試。
- 支援均衡、優先順序、加權、最低延遲和最低成本路由。
- 虛擬金鑰支援日/月預算、RPM/TPM、到期時間及模型允許清單。
- 逐次呼叫估算美元成本，彙整至儀表板與 Prometheus。
- 選用提示注入偵測、關鍵字封鎖及個資遮蔽。
- 選用確定性回應的完全相符快取。
- Prometheus 指標、選用 Langfuse 匯出及用量追蹤。
- 提供憑證、日誌、設定、用量及版本管理主控台。

<a id="console-preview"></a>

## 控制台預覽

螢幕截圖使用隔離的離線示範環境中的虛構資料。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — 儀表板" width="1600" height="1100" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — 控制台預覽" width="1600" height="1100" />
</picture>

<a id="supported-providers"></a>

## 支持的供应商

目錄包含 23 個供應商。可用模型和功能取決於各憑證的實際權限。

| 供應商 | 連線方式 | 服務 / 範圍 |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API 金鑰 | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API 金鑰 | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth（裝置碼） | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API 金鑰 | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | API 金鑰 | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | 端點；API 金鑰選填 | 本機 / 自行託管 |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | API 金鑰 | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | API 權杖 + 帳戶 ID | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | API 金鑰 | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | API 金鑰 | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | API 金鑰；組織 ID 選填 | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | API / 服務金鑰 | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | API 金鑰 | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | 瀏覽器 OAuth / AWS 裝置登入 / API 金鑰 | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth（Meta 裝置碼） | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | API 金鑰 | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | API 金鑰 | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | API 金鑰 | NVIDIA 託管推論 |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | API 金鑰 + Zen/Go 方案 | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | API 金鑰 | Poolside API |

用戶端使用共同的 [SDK 介面](#sdk-surfaces)。轉換、串流及容錯移轉受模型能力限制；不相容選項會明確遭到拒絕。在 **Providers** 中依供應商或憑證設定連線。Muse Code 和 Meta Model API 的憑證與模型命名空間互相獨立。

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## 架構設計

```text
客戶端工具
  OpenAI SDK | Google GenAI SDK | Anthropic SDK | IDE 整合外掛
        |
        v
Polaris
  身分認證 -> 格式協定轉換 -> 權杖感知清理 -> 路由分發 -> 容錯移轉 -> 串流輸出
        |
        v
供應商適配器
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

在 Polaris 後端適配器持續演進的同時，對外的公共 API 契約保持絕對穩定。

<a id="repository-structure"></a>

## 程式庫目錄結構

```text
backend/       FastAPI 組合根、路由核心、協定轉換器、儲存層與測試用例
frontend/      管理控制台頁面結構、樣式、腳本及供應商圖示資產
deploy/        容器定義、平台部署清單與作業系統啟動腳本
docs/          架構設計說明與專案維護文檔
.github/       CI 流水線、依賴自動化與貢獻範本
```

詳見[架構設計](../architecture.md)，瞭解模組邊界、請求處理流程、狀態歸屬與目前版本的發布約束。

<a id="deployment"></a>

## 部署

單機、單 worker 的 Docker Compose 是主要部署方式。請遵循[安裝指南](../installation.md)與[支援矩陣](../installation.md#support-matrix)。

基本設定不需外部服務，資料保存在 `polaris-data`。範本面向 `1.0.0`。僅使用已發布且版本一致的 Polaris 標籤和映像安裝；若使用尚未發布的原始碼，請依[發布清單](../releases/1.0.0-preparation.md)建置獨立的本機映像。升級或回復請遵循[更新指南](../updating.md)，進階功能可透過 `deploy/compose.advanced.yml` 選用。

參閱[識別名稱約定](../migrations/polaris.md)及[疑難排解](../troubleshooting.md)。原生指令碼、`docker run`、Render 與 Zeabur 屬相容路徑，未具備同等安裝及復原驗證。映像發布支援 `linux/amd64`；`linux/arm64` 仍暫停發布。

### 本機開發或疑難排解：

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

開啟主控台；初始設定流程與 Docker 相同：

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## 配置項

優先順序為環境變數、已儲存設定、預設值。[產生的設定參考](../reference/configuration.md)說明型別、分組、負責模組及立即生效、重新啟動生效或僅限環境的生命週期。無效值會阻止啟動並指出變數；疑似拼錯的 `POLARIS_*` 名稱會產生警告。

| 環境變數 | 預設值 | 用途說明 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | 繫結監聽位址。 |
| `PORT` | `4283` | HTTP 連接埠。 |
| `HOST_PORT` | `4283` | 宿主機連接埠，僅供 Docker Compose 使用。 |
| `WORKERS` | `1` | 僅支援一個 worker。 |
| `POLARIS_RUNTIME_MODE` | `standalone` | 僅支援 `standalone`。 |
| `POLARIS_REPLICA_COUNT` | `1` | 僅支援一個副本。 |
| `CORS_ORIGINS` | 空白 | 允許跨來源調用 API 的瀏覽器 Origin 列表（逗號分隔）。同來源控制台造訪請保持為空。 |
| `CORS_ORIGIN_REGEX` | 空白 | 用於比對動態瀏覽器 Origin 的可選正規表示式。 |
| `API_KEY` | 自動產生 | 用戶端 API 金鑰，前綴為 `sk-polaris-`。 |
| `PANEL_PASSWORD` | 設定前為空白 | Web 控制面板的造訪密碼。 |
| `SETUP_TOKEN` | 空白 | 遠端初始設定所需的唯一權杖，至少 24 字元；不自動產生或記錄。直接 localhost 存取不需要。 |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Web 控制台工作階段有效時間（秒）。 |
| `PANEL_COOKIE_SECURE` | 自動 | 設為 `true` 強制僅在 HTTPS 下傳輸 Cookie。留空時透過 `X-Forwarded-Proto` 自動偵測。 |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | 登入頻率限制時間窗口（秒）。 |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | 限制窗口期內單一客戶端允許的最大失敗登入嘗試次數。 |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | 記憶體中登入頻率限制器追蹤的最大客戶端位址數量。 |
| `MAX_REQUEST_BODY_MB` | `64` | 最大 HTTP 請求主體大小（MiB）。超出限制的 SDK 請求將回傳對應協定的原生錯誤封包。 |
| `TRUST_PROXY_HEADERS` | `false` | 僅在下游存在受信任的反向代理且會覆寫轉發標頭時才接收客戶端與協定轉發標頭。 |
| `CREDENTIALS_DIR` | `./backend/data/creds` | 憑證儲存目錄。在 Docker 中需將 `/app/backend/data/creds` 掛載至宿主機磁碟區。 |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Code Assist 後端服務位址。 |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Google Antigravity 後端服務位址。 |
| `PROXY` | 空白 | 可選的 HTTP、HTTPS 或 SOCKS 代理。 |
| `RETRY_429_ENABLED` | `true` | 對速率限制和上游暫時性故障啟用有限次重試。保留舊名稱以相容既有配置。 |
| `RETRY_429_MAX_RETRIES` | `5` | 上游暫時性故障的最大重試次數。 |
| `RETRY_429_INTERVAL` | `1` | 暫時性重試的基礎退避間隔（秒）。 |
| `AUTO_DISABLE` | `false` | 在發生配置的嚴重錯誤後自動停用對應憑證。 |
| `AUTO_DISABLE_ERROR_CODES` | `403` | 逗號分隔的嚴重錯誤狀態碼列表。 |
| `ROUTING_STRATEGY` | `balanced` | 策略：`balanced`、`priority`、`weighted`、`least_latency`、`lowest_cost`。 |
| `PREFERRED_PROVIDER` | 空白 | `priority` 策略優先選用的供應商，例如 `google_antigravity` 或 `google_ai_studio`。 |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | 供應商推論逾時時間，限制在 5 到 900 秒之間。 |
| `RESPONSE_CACHE_ENABLED` | `false` | 為溫度 0、非串流的確定性回應啟用記憶體快取。 |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | 快取有效期，單位秒。 |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | 快取回應數量上限。 |
| `GUARDRAILS_ENABLED` | `false` | 啟用呼叫前防護。 |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | 遮蔽傳出文字的電子郵件、信用卡與 API 金鑰。 |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | 偵測到提示注入時回傳 HTTP 400。 |
| `GUARDRAILS_BLOCKED_KEYWORDS` | 空白 | 逗號分隔的封鎖關鍵字，不區分大小寫。 |
| `PRICING_SYNC_ENABLED` | `true` | 背景更新 LiteLLM 價格；離線保留最後有效副本。 |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | 價格更新間隔：1–168 小時。 |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | 防截斷串流傳輸的最大續寫重試次數。 |
| `TOKEN_COMPRESSION_ENABLED` | `true` | 在路由至供應商前壓縮超長對話歷史。 |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | 觸發上下文壓縮的預估輸入權杖閾值。 |
| `TOKEN_COMPRESSION_TARGET` | `24000` | 壓縮後的預估輸入權杖目標值。必須低於觸發閾值。 |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | 壓縮過程中必須保留的最近使用者輪次最少數。 |
| `COMPATIBILITY_MODE` | `false` | 為不相容系統訊息的客戶端/模型自動轉換 System 訊息。 |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | 在可用時回傳模型的思考推理過程（reasoning）。 |
| `MONGODB_URI` | 空白 | MongoDB 相容儲存。 |
| `POSTGRESQL_URI` | 空白 | 選用 PostgreSQL 儲存。 |
| `CODE_ASSIST_CLIENT_ID` | 內建桌面用戶端 | Code Assist OAuth Client ID 的可選覆蓋值。 |
| `CODE_ASSIST_CLIENT_SECRET` | 內建桌面用戶端 | Code Assist OAuth Client Secret 的可選覆蓋值。 |
| `ANTIGRAVITY_CLIENT_ID` | 內建桌面用戶端 | Google Antigravity OAuth Client ID 的可選覆蓋值，亦可在供應商頁面配置。 |
| `ANTIGRAVITY_CLIENT_SECRET` | 內建桌面用戶端 | Google Antigravity OAuth Client Secret 的可選覆蓋值，上游變更時可透過環境變數或供應商頁面調整。 |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Google AI Studio Generative Language API 的可選服務位址覆蓋值。 |
| `XAI_API_URL` | `https://api.x.ai/v1` | SpaceXAI Console API 金鑰憑證的可選 API 服務位址覆蓋值，亦可在供應商頁面配置。 |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Grok Build OAuth 訂閱端點的可選服務位址覆蓋值。 |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Grok Build OAuth Issuer 的可選覆蓋值。控制台僅接受 `x.ai` 網域下的 HTTPS 主機。 |
| `XAI_CLIENT_ID` | 內建公開用戶端 | Grok Build PKCE OAuth Client ID 的可選覆蓋值。 |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Grok Build OAuth 與 SpaceXAI Console API 請求共用的可選 HTTP User-Agent 覆蓋值。 |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | OpenAI Platform API 的可選服務位址覆蓋值，亦可在供應商頁面配置。 |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Codex 推論與帳戶模型列表端點的可選覆蓋值。 |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Codex 帳戶速率限制查詢端點的可選覆蓋值。 |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Codex 裝置授權服務的可選服務位址覆蓋值。 |
| `CODEX_CLIENT_ID` | 內建公開用戶端 | Codex 裝置 OAuth Client ID 的可選覆蓋值。 |
| `CODEX_USER_AGENT` | 相容 Codex CLI 的值 | Codex 請求的可選 User-Agent 覆蓋值。 |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Claude Code 專用 Messages 端點。 |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Claude Code PKCE 授權端點的可選覆蓋值。控制台僅接受 Anthropic 與 Claude 官方主機。 |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Claude Code Token 端點的可選覆蓋值。控制台僅接受 Anthropic 與 Claude 官方主機。 |
| `CLAUDE_CLIENT_ID` | 內建公開用戶端 | Claude Code PKCE OAuth Client ID 的可選覆蓋值。 |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | Claude Code 專用 User-Agent。 |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Providers 中獨立的 Claude Platform 端點。 |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | Claude Platform 獨立 User-Agent。 |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Google Antigravity 協定層級請求的可選 User-Agent 覆蓋值。 |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Google Antigravity 負載層 userAgent 的可選覆蓋值。 |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | 啟用需要驗證的 `GET /metrics`。 |
| `METRICS_TOKEN` | 空白 | Prometheus 必要的 Bearer 權杖，至少 32 個 UTF-8 位元組。 |
| `OTEL_EXPORT_ENABLED` | `false` | 啟用不含內容的 OTLP/HTTP 彙整資料匯出。 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 空白 | HTTPS 收集器位址，不允許在 URL 內嵌憑證。 |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | 匯出間隔：15–300 秒。 |
| `LANGFUSE_PUBLIC_KEY` | 空白 | 與私密金鑰共同啟用 Langfuse。 |
| `LANGFUSE_SECRET_KEY` | 空白 | 用於追蹤的 Langfuse 私密金鑰。 |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse 資料接收端點。 |
| `LOG_LEVEL` | `info` | 執行階段日誌記錄層級。 |
| `LOG_MAX_MB` | `10` | 單一活動日誌檔案在輪替前的最大體積（MB）。 |
| `LOG_BACKUP_COUNT` | `3` | 保留的歷史輪替日誌檔案數量。 |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | 檔案日誌輸出路徑。在 Docker 中需將 `/app/backend/data/logs` 掛載至宿主機磁碟區。 |

### 壓縮控制

全域 AI Quality 原則具有最終約束力。虛擬金鑰只能繼承或停用壓縮：透過 `PATCH /api/virtual-keys/{key_id}/quality-policy` 提交目前修訂版，使用 `inherit` 移除金鑰限制。已驗證請求可設定 `x-polaris-compression: off`；省略或 `inherit` 遵循全域及金鑰原則。請求不能重新啟用全域停用的壓縮，也不能提高壓縮強度。僅移除安全的歷史前綴；結構或估算不確定時原樣傳送。Token 數量為估算值。

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## 快速上手 SDK 接入

Polaris 嚴格按照官方 Python SDK 的標準 URL 行為進行設計。請完全參照下文方式配置客戶端，閘道無需任何非標準的重複路徑前綴。

範例中使用虛擬模型 `polaris`。請先在控制台的「模型」頁面配置其優先順序回退模型鏈，或者直接將其替換為具體的供應商模型 ID。

### OpenAI Python SDK

將 OpenAI 的 Base URL 設定為 `/v1`，SDK 會自動在末尾追加 `/chat/completions`。

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "用一段話解釋這個程式庫。"}]
)
```

同一客戶端亦可以直接調用 OpenAI Responses API：

```python
response = client.responses.create(
    model="polaris",
    instructions="請簡明扼要。",
    input="用一段話解釋這個程式庫。"
)

print(response.output_text)
```

Responses 相容層支援文字輸入、圖片輸入、非串流 Function Tool 以及 SSE 文字串流傳輸。對於 OpenAI 託管的內建工具、持久化回應歷史以及串流函式調用，閘道會明確回傳錯誤拒絕請求，因為 Polaris 不會執行、持久化或隱含捨棄這些 OpenAI 特有的專有行為。

### Anthropic Python SDK

將 Anthropic 的 Base URL 直接指向閘道根位址，SDK 會自動在末尾追加 `/v1/messages`。

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "撰寫一條 Git 提交訊息。"}]
)
```

### Google GenAI Python SDK

將 Google GenAI 的 Base URL 直接指向閘道根位址，SDK 會自動追加預設模型路由，例如 `/v1beta/models/{model}:generateContent`。

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
    contents="寫一個簡短的 Python 函式。",
    config=types.GenerateContentConfig(
        system_instruction="你是一個得力的程式設計助手。"
    )
)
```

### 支援的路由列表

Polaris 提供標準 SDK 相容路由，無需額外的產品命名空間前綴：

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

身分認證、請求校驗、路由選擇、上游調用及串流啟動前的失敗均使用對應 SDK 介面的原生錯誤格式包裹。每個 HTTP 回應均包含 `X-Request-ID` 請求標識；客戶端可在該請求標頭傳入安全標識以進行全鏈路追蹤。當上游回傳速率限制或暫時無法使用時，閘道將原樣保留並透傳 `Retry-After` 標頭。

<a id="model-features"></a>

## 模型特性與高級控制

控制台「模型」頁面透過已啟用的各供應商憑證中探索到的模型，聚合建構出虛擬模型 `polaris`。只需設定一次各底層模型的優先順序順序，即可在任意支援的 SDK 中使用 `polaris`。Polaris 會在支援第一順位模型的健康憑證之間進行負載平衡；當該模型無法使用時，自動依次降級嘗試後續配置的模型。具體的供應商物理模型 ID 依然保留可用，以滿足需要確定性指定模型的客戶端需求。儲存空列表即可停用 `polaris`，這不會影響任何供應商憑證。

模型探索機制具備供應商感知能力：通用模型可由多個供應商共同支援，而專有模型僅由相容的憑證承接。每個已驗證的憑證獨立儲存其專屬的供應商目錄，路由器優先採用憑證明確宣告支援的模型，而非通用的供應商類型推斷。重新整理目錄將重新拉取目前供應商的即時可用性；無法使用的配置項將保持可見，直到其復原或被手動移除。

當上游對某個物理模型回傳 `404` 時，Polaris 會在該憑證與模型作用域內記錄無法使用路由，而非直接停用整個供應商。該路由將立即被暫時避開，並在**無法使用模型路由**列表中保持可見，直到被手動清除或該憑證重新校驗通過。這避免了因單一帳戶的訂閱權限或地域限制而影響同一供應商下的其他健康帳戶。若啟用的憑證均未宣告或推斷支援所請求的模型，閘道將回傳明確的無相容憑證錯誤，而不是將請求隨機發往不符合的供應商。

Polaris 支援在模型名稱中解析特性前綴與後綴：

- `fake-streaming/{model}` 或配置的偽串流前綴，適用於強制要求 SSE 輸出的客戶端。
- `streaming-anti-truncation/{model}` 或配置的防截斷前綴，用於長文本串流生成的自動續寫復原。
- 思考深度後綴（如 `-high`、`-medium`、`-low`、`-minimal`、`-max`），適用於支援該特性的 Gemini 系列模型。
- 連網搜尋後綴（如 `-search`），適用於支援 Google Search 搜尋接地的模型。

供應商適配器會在向上游發送請求前自動將這些特性標識規範化。

<a id="usage-and-cost-visibility"></a>

## 使用量與成本透明度

每次供應商嘗試、重試及容錯移轉分開計數；追蹤保留邏輯請求的最終結果。記錄結果、憑證、供應商回報的輸入/輸出/快取/推理 token、估算節省量及美元成本。缺少用量不等於實測為零。統計期間採瀏覽器時區的固定邊界，日檢視涵蓋 00:00–23:00。預設於啟動時及每 24 小時更新 LiteLLM 公開價格，以不可分割操作保留最後有效副本；失敗不阻擋推論。憑證目錄的 `model_pricing.json` 優先，單價為每百萬 token。儀表板、`/api/virtual-keys` 與 `/metrics` 提供彙整；以供應商帳單與 tokenizer 為準。

虛擬金鑰支援日/月預算、RPM/TPM 滑動視窗、到期時間及 glob 模型規則。僅儲存 SHA-256 雜湊，明文金鑰只在建立時顯示。

<a id="credential-workflow"></a>

## 憑證配置工作流程

1. 啟動 Polaris。
2. 在 VPS 上造訪 `http://你的伺服器IP:4283`，或在本地開發時造訪 `http://127.0.0.1:4283`。
3. 完成檢查並建立擁有者密碼。遠端初始設定前，預先設定至少 24 字元的唯一 `SETUP_TOKEN` 或 `PANEL_PASSWORD`。權杖不會自動產生或寫入日誌。
4. 在「供應商」頁面新增帳戶、API 金鑰或 Ollama 連線。
5. 驗證憑證有效性，並在面板中監控冷卻時間與錯誤狀態。 **Credentials** (`/credentials`).
6. 將你的程式設計工具連接至上述支援的 API 介面之一。

新增 Google Antigravity 憑證時，Google 會在登入完成後將瀏覽器重新導向至 `http://localhost:4283/callback`。在本地機器上，Polaris 會直接展示 OAuth 授權成功頁面。在 VPS 上，由於該 `localhost` 指向使用者的本地瀏覽器機器，頁面可能無法開啟；只需複製瀏覽器網址列中的完整 URL，返回「供應商」頁面貼至 `Callback URL` 框中，點擊 `儲存憑證` 即可。

Google AI Studio 使用 API 金鑰認證而非 OAuth。在「供應商」頁面新增金鑰後，Polaris 將對照 Google 模型目錄驗證其有效性，儲存為供應商憑證，並將相容的 Gemini 或 Gemma 請求路由至該憑證。智慧路由器可以在共用的 Gemini 模型上於 AI Studio 與 Google Antigravity 之間自動容錯移轉，同時保證專有模型僅由相容憑證承接。

Google AI Studio 批次匯入支援 JSON 檔案及包含 JSON 檔案的 ZIP 壓縮檔。JSON 檔案可包含單條金鑰、`api_keys` 陣列或金鑰物件陣列：

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

檔案匯入是離線操作：Polaris 檢查 JSON/ZIP 結構，將新金鑰儲存為 `unverified`，略過重複或已存在的金鑰，不連線至 Google。匯入的模型清單不視為已驗證。格式錯誤會個別回報，不洩漏金鑰。之後請主動執行憑證驗證/模型探索；**Test model** 另外檢查推論權限，可能消耗配額或產生費用。

Grok Build 支援 PKCE OAuth 憑證，而 SpaceXAI Console 支援 API 金鑰。SpaceXAI Console 金鑰在儲存前會對照 SpaceXAI Console API 模型目錄進行驗證。對於 Grok Build OAuth，Polaris 會產生授權連結；授權完成後，複製授權頁面展示的授權碼並貼至表單中。當存在 Refresh Token 時系統會自動重新整理存取權杖，且兩種憑證類型均僅暴露各自目前目錄宣告的模型。在「憑證」頁面，可查詢 Grok Build OAuth 帳戶的月度額度消耗情況，以及 xAI 提供時的週度使用量。該帳戶級帳單檢視不支援 SpaceXAI Console API 金鑰。

Codex 使用 OpenAI 裝置授權流程。在「供應商」頁面產生裝置代碼，開啟展示的驗證網址，輸入代碼完成登入，然後返回檢查授權狀態。Polaris 將儲存 Codex 回傳的帳戶級模型目錄，在需要時自動重新整理 OAuth 存取權杖，並透過 Codex Responses 傳輸協定轉發相容請求。OpenAI Platform 使用 API 金鑰認證；金鑰在儲存前均透過帳戶模型目錄進行有效性校驗。兩款產品均支援 JSON 與 ZIP 匯入，並具備供應商特定的校驗與去重能力。

Claude Code 使用 Anthropic 的 PKCE OAuth 流程。產生授權連結，完成授權後將回傳的授權碼貼回「供應商」頁面。Claude Platform 接收 Anthropic API 金鑰。兩款產品均可探索每個憑證支援的模型列表，使用 Anthropic Messages 傳輸協定，在可能時自動重新整理 Claude Code 存取權杖，並支援帶校驗的 JSON 或 ZIP 匯入。

Muse Code 使用 Meta 裝置授權。在 **Providers → Muse Code** 取得連結，於 Meta 核准裝置碼，再回到 **Save credential** 儲存。直接連線，不需 CLI、Linux 或 VPS；模型前綴為 `muse-code/`，可設定顯示名稱。方案、工作階段/週配額、重設時間及觀測時間僅在供應商回傳時顯示；缺少資料不表示剩餘 100%。重新整理會檢查訂閱並透過目前工作階段取得推論金鑰；工作階段失效時需重新登入。

Kiro 支援 Google/GitHub 瀏覽器 OAuth、AWS 裝置授權及 API 金鑰。進階欄位依驗證方式改變：執行區域、AWS 權杖區域/起始 URL，或 API 金鑰的設定檔 ARN。

Ollama 連線按端點配置，並可包含用於受保護或雲端伺服器的可選 Bearer API 金鑰。Polaris 透過 `/api/tags` 探索可用模型，並透過 `/api/chat` 執行推論路由。當 Polaris 執行在 Docker 中時，`localhost` 指向容器本身；請使用宿主機閘道位址或網路可達的其他 Ollama 端點。

憑證完整匯入與 Google Antigravity 批次匯入支援最大 10 MB 的壓縮檔、最多 500 個檔案、單一憑證檔案最大 2 MB 以及解壓縮後最大 25 MB 的資料量。Google AI Studio、OpenAI、Anthropic 與 Ollama 供應商單項匯入採用更嚴格的限制：單一匯入檔案最大 2 MB、最多 200 條 JSON 記錄、解壓縮後最大 5 MB。

**Credentials**（`/credentials`）依供應商分組帳戶與金鑰。管理對話框呈現身分、模型、狀態及可用操作。OAuth 可能回傳方案、點數及依時間視窗或模型劃分的配額。API 金鑰不會自動提供電子郵件、方案或帳務資料；缺少的資訊顯示為無法取得。

**Download ZIP** 匯出憑證；**Import ZIP** 依供應商驗證、去重並逐筆回報錯誤。匯入成功或發現模型目錄不代表具有推論權限；**Test model** 會送出真實請求，可能消耗配額或產生費用。封存檔包含機密。完整 SQLite 與設定備份應使用 **Settings** 的加密流程。

Google Antigravity 憑證命名為 `google-antigravity-{account_fingerprint}.json`，指紋衍生自規範化的帳戶電子郵件且不洩漏明文。Google AI Studio 憑證命名為 `google-ai-studio-{key_fingerprint}.json`，Grok Build OAuth 憑證命名為 `grok-{account_fingerprint}.json`，SpaceXAI Console 憑證命名為 `xai-console-{key_fingerprint}.json`，Codex 憑證命名為 `openai-codex-{account_fingerprint}.json`，OpenAI Platform 憑證命名為 `openai-platform-{key_fingerprint}.json`，Claude Code 憑證命名為 `claude-code-{account_fingerprint}.json`，Claude Platform 憑證命名為 `claude-platform-{key_fingerprint}.json`，Ollama 連線命名為 `ollama-{connection_fingerprint}.json`。舊版 `provider_*.json` 與 `xai-grok-*.json` 憑證保持向下相容，並在匯出時自動轉換為標準規範名稱。

憑證模式名稱：

- `code_assist`：標準 Code Assist 憑證。
- `provider`：通用供應商後端憑證。

<a id="storage"></a>

## 資料儲存

建議使用 SQLite。Compose 將 `/app/backend/data` 保存在 `polaris-data`；直接使用 Docker 時，將 `/app/backend/data/creds` 與 `/app/backend/data/logs` 掛載至 `/opt/polaris/creds`、`/opt/polaris/logs` 等持久目錄。

PostgreSQL 為選用；MongoDB 保留相容支援，可直接運作，不需 Redis。兩者只能設定一個。初始化失敗會阻止啟動，不會靜默退回 SQLite。外部資料庫不提供水平擴充：仍僅支援一個 worker、一個副本。可攜式加密備份僅支援 SQLite，不支援儲存後端間的線上遷移。

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[資料儲存](../storage.md)

支援透過環境變數匯入憑證。可在控制台操作，或將以下變數之一設定為原始 JSON 字串，亦可使用帶 `_B64` 後綴的 Base64 編碼字串：

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

負載內容可以是單一憑證物件、憑證陣列或 `{ "credentials": [...] }` 結構。

<a id="development"></a>

## 開發指南

本節面向專案貢獻者及本地偵錯。生產環境部署請使用帶有持久化宿主機磁碟區的 Docker 方案。

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

[品質檢查](../quality-gates.md)區分工作、階段及發布驗證。`python tools/quality_gate.py --list-suites` 亦列出選用的外部即時檢查。[相容性約定](../compatibility.md)涵蓋 SDK/管理路由、遷移、結構及範例。

所有程式碼檢查均通過後啟動服務：

```bash
python backend/main.py
```

生產執行基準為 Python 3.12，CI 自動化測試涵蓋 Python 3.12 與 3.14。有關 Pull Request 提交流程與程式碼審查標準，請參閱[貢獻指南](../../CONTRIBUTING.md)。

<a id="deployment-notes"></a>

## 部署注意事項

- 切勿提交包含憑證的 JSON 檔案或 `.env` 檔案。
- 為客戶端整合配置專用的 `API_KEY`，並為控制台造訪設定獨立的 `PANEL_PASSWORD`。
- 嚴格限制對持久化憑證資料磁碟區或外部資料庫的造訪權限，並在平台層啟用靜態落盤加密；路由器必須能夠解密讀取供應商權杖。
- 當服務暴露於非 localhost 環境時，務必將 Polaris 置於配置了 TLS 的反向代理之後。
- 配置反向代理保留 `Host` 請求標頭並傳遞 `X-Forwarded-Proto`；在確認全程 HTTPS 終止時設定 `PANEL_COOKIE_SECURE=true`。
- 僅當服務完全僅經由會改寫 `X-Forwarded-For` 與 `X-Forwarded-Proto` 的受信任代理造訪時，才設定 `TRUST_PROXY_HEADERS=true`。
- 使用 `GET /health` 進行行程存活探針檢查，使用 `GET /ready` 進行包含儲存層感知的整備探針檢查。
- 外部遙測需主動啟用：Prometheus 要求 `PROMETHEUS_EXPORT_ENABLED` 及強 `METRICS_TOKEN`；OpenTelemetry 僅匯出彙整資料，不匯出提示或回應內容。參閱[可觀測性](../observability.md)。
- Docker 映像檔僅在啟動初期以 root 權限修復掛載資料目錄的權限歸屬，隨後降權切換至無特權的 `gateway` 使用者執行。
- 當瀏覽器客戶端需要跨來源造訪時，請將 `CORS_ORIGINS` 明確設定為受信任的來源。
- 升級或搬移 SQLite 前使用[經過驗證的加密備份](../backup-and-restore.md)，將封存檔與通關密語保存在 `polaris-data` 之外。
- Docker 映像檔發布使用倉庫密鑰 `DOCKERHUB_USERNAME` 與 `DOCKERHUB_TOKEN` 推送至 Docker Hub，並使用內建的 `GITHUB_TOKEN` 推送至 GitHub Packages（`ghcr.io/nguywnben/polaris`）。僅在發布到自訂 Docker Hub 映像檔名稱時才設定可選的 `IMAGE_NAME` 變數。
- 在 1.x 系列版本中，請保持 `WORKERS=1` 與單應用複本；外部儲存無法替代分散式協同機制。
- 請使用標準規範的 `/api/credentials` 管理路由。Beta 階段的 `/api/creds` 別名已在 1.0.0 中徹底移除。
- 在遷移 Beta 版本部署前，請先查閱[升級至 1.0 指南](../upgrading-to-1.0.md)。
- 升級現有執行實例或復原版本時，請參考[更新指南](../updating.md)。
- 在打 Tag 或發布映像檔前，請對照維護的[發布核對清單](../release-checklist.md)逐項確認。
- 請根據實際用量配額合理制定日誌保留與憑證輪替策略。
- 一旦程式碼倉庫或雲端平台安全掃描警示憑證洩漏，請立即撤銷並輪換該憑證。
- Render 部署清單使用的是帶有持久化硬碟的付費服務。Render 的免費服務使用暫時檔案系統，僅適合一次性測試體驗。

<a id="community-and-project-health"></a>

## 社群與專案健康度

- 在提交 Pull Request 前請閱讀[貢獻指南](../../CONTRIBUTING.md)。
- 回報安全漏洞請透過[安全政策](../../SECURITY.md)中註明的私密管道提交。
- 檢視[更新日誌](../../CHANGELOG.md)瞭解各版本的詳細變更。
- 在參與本專案的所有相關活動中均須遵守[行為準則](../../CODE_OF_CONDUCT.md)。

<a id="acknowledgements-inspirations"></a>

## 致謝與靈感來源

Polaris 站在開源 AI 路由、可觀測性與閘道社群的堅實肩膀之上。我們向以下專案的創作者與維護者致以由衷的敬意與感謝：

| 專案 | 專案描述 | Stars |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | 多供應商金鑰管理與基於 Web 的 API 聚合架構靈感來源 | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | 面向 AI 程式設計 CLI 的開創性多協定代理與格式轉換層 | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | 行業標竿級的統一 LLM 代理、負載平衡與容錯移轉路由 | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | 極速 AI 閘道架構設計、路由策略及高彈性容災模式 | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | 開源 LLM 工程化平台、調用追蹤、系統可觀測性與指標採集 | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## 開源授權

Polaris 基於 [MIT 開源授權](../../LICENSE) 發布。
