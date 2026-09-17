<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>AI コーディングツール向けユニバーサル AI ルーター & 統合マルチプロバイダーゲートウェイ</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">対応プロバイダー</a> • <a href="#core-capabilities">主要機能</a> • <a href="#deployment">デプロイ</a> • <a href="#sdk-surfaces">クイックスタート SDK 連携</a> • <a href="#architecture">アーキテクチャ</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <b>日本語</b> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

この README は同じ機能範囲で 15 言語に対応しています。リンク先の技術ガイドは原文の言語で提供されます。

コーディングツールのためのユニバーサル AI ルーター。Polaris は、スマートな自動フォールバック、トークン対応のコンテキストクリーンアップ、利用状況の可視化、シームレスなフォーマット変換を提供し、ローカルエージェント、IDE アシスタント、自動化スクリプトが単一の安定した API インターフェースを通じて無料および有料の LLM 処理能力を活用できるようにします。

> Polaris は個人または信頼できるチーム向けのセルフホストを対象とし、worker とレプリカは各 1 つです。Docker Compose、ローカル所有者ログイン、SQLite、ルーティング、文書化された SDK インターフェースが中核です。PostgreSQL、OIDC、リバースプロキシ、外部テレメトリは任意、MongoDB は互換用途です。複数レプリカの協調動作と Kubernetes は対象外です。 [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Polaris を選ぶ理由

現代のコーディングワークフローでは、OpenAI 互換ツール、Gemini ネイティブ SDK、Anthropic スタイルのエージェント、Google 認証情報、実験的なモデルルートなど、複数のクライアントとプロバイダーが混在することがよくあります。Polaris はこれらのクライアントとモデルバックエンドの間に位置し、ゲートウェイがルーティング、リトライ、リクエストのクリーンアップ、レスポンスの正規化を処理する間、各ツールがネイティブフォーマットで通信し続けられるようにします。

<a id="core-capabilities"></a>

## 主要機能

- リクエスト単位の予約、公平なローテーション、クールダウン、クォータ枯渇を考慮した自動フォールバック。
- システム指示、ツール、直近の会話を維持した長い履歴の整理。
- OpenAI Chat Completions/Responses、Gemini、Anthropic Messages 間の変換とストリーミング。
- OAuth アカウントと API キーの検証、プロバイダー別重複排除。
- アカウントの権限を反映した認証情報別モデルカタログ。
- 利用不能なモデルルートの記録と Models 画面からの復旧。
- SSE、擬似ストリーミング、切り詰められた応答への回数制限付き再試行。
- 均等、優先度、重み、最低遅延、最低コストのルーティング。
- 日次/月次予算、RPM/TPM、有効期限、許可モデル付き仮想キー。
- 呼び出し別の推定 USD コストとダッシュボード・Prometheus 集計。
- 任意のプロンプトインジェクション検出、禁止語、個人情報マスキング。
- 決定的な応答を完全一致で再利用する任意のキャッシュ。
- Prometheus、任意の Langfuse 出力、使用量追跡。
- 認証情報、ログ、設定、使用量、バージョンを管理するコンソール。

<a id="console-preview"></a>

## コンソールプレビュー

![Polaris — コンソールプレビュー](../assets/screenshots/credential-pool.png)

<a id="supported-providers"></a>

## 対応プロバイダー

カタログには 23 プロバイダーがあります。利用できるモデルと機能は各認証情報の権限に依存します。

| プロバイダー | 接続方法 | サービス / 範囲 |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API キー | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API キー | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth（デバイスコード） | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API キー | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | API キー | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | エンドポイント、API キーは任意 | ローカル / セルフホスト |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | API キー | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | API トークン + アカウント ID | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | API キー | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | API キー | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | API キー、組織 ID は任意 | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | API / サービスキー | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | API キー | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | ブラウザー OAuth / AWS デバイス認証 / API キー | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth（Meta デバイスコード） | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | API キー | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | API キー | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | API キー | NVIDIA ホステッド推論 |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | API キー + Zen/Go プラン | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | API キー | Poolside API |

クライアントは共通の [SDK インターフェース](#sdk-surfaces)を使います。変換、ストリーミング、フォールバックはモデルの能力に依存し、非対応オプションは明示的に拒否されます。**Providers** でプロバイダーまたは認証情報別に設定します。Muse Code と Meta Model API は認証情報とモデル名前空間が別です。

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## アーキテクチャ

```text
クライアントツール
  OpenAI SDK | Google GenAI SDK | Anthropic SDK | IDE 連携プラグイン
        |
        v
Polaris
  認証 -> フォーマット変換 -> トークン対応クリーンアップ -> ルーティング -> フォールバック -> ストリーミング
        |
        v
プロバイダーアダプター
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

Polaris バックエンドアダプターが進化し続ける中でも、外部向けのパブリック API コントラクトは安定性を維持します。

<a id="repository-structure"></a>

## リポジトリ構成

```text
backend/       FastAPI 構成ルート、ルーティングコア、プロトコル変換、ストレージ、テスト
frontend/      管理コンソール UI、スタイル、スクリプト、プロバイダーアイコンアセット
deploy/        コンテナ定義、プラットフォームマニフェスト、OS 起動スクリプト
docs/          アーキテクチャ設計書およびプロジェクト保守ドキュメント
.github/       CI ワークフロー、依存関係自動化、コントリビューションテンプレート
```

モジュール境界、リクエスト処理フロー、状態の所有権、現行リリースの制約については、[アーキテクチャ](../architecture.md)を参照してください。

<a id="deployment"></a>

## デプロイ

単一マシン・単一 worker の Docker Compose が推奨経路です。[インストール](../installation.md)と[対応表](../installation.md#support-matrix)に従ってください。

基本構成は外部サービス不要で、データを `polaris-data` に保存します。テンプレートの固定バージョンは `0.1.0-beta.1` です。[更新・ロールバック手順](../updating.md)に従い、高度な機能は `deploy/compose.advanced.yml` で任意に追加します。

[識別子の契約](../migrations/polaris.md)と[トラブルシューティング](../troubleshooting.md)も参照してください。ネイティブスクリプト、`docker run`、Render、Zeabur は互換経路であり、同等の導入・復旧検証対象ではありません。公開イメージは `linux/amd64` 用で、`linux/arm64` の公開は停止中です。

### ローカル開発・診断：

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

コンソールを開きます。初期設定は Docker と同じです：

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## 設定

優先順位は環境変数、保存済み設定、既定値です。[生成された設定リファレンス](../reference/configuration.md)に型、グループ、担当モジュール、即時適用・再起動・環境限定の区分があります。不正な値は起動を止めて変数を示し、`POLARIS_*` の誤記候補は警告されます。

| 環境変数 | デフォルト値 | 説明 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | バインドアドレス。 |
| `PORT` | `4283` | HTTP ポート。 |
| `HOST_PORT` | `4283` | ホスト側ポート（Docker Compose 専用）。 |
| `WORKERS` | `1` | worker は 1 つのみ対応。 |
| `POLARIS_RUNTIME_MODE` | `standalone` | `standalone` のみ対応。 |
| `POLARIS_REPLICA_COUNT` | `1` | レプリカは 1 つのみ対応。 |
| `CORS_ORIGINS` | 空 | クロスオリジン API 呼び出しを許可するブラウザオリジンのカンマ区切りリスト。同一オリジンのコンソールアクセスの場合は空のままにします。 |
| `CORS_ORIGIN_REGEX` | 空 | 動的ブラウザオリジンを照合するためのオプションの正規表現。 |
| `API_KEY` | 自動生成 | 接頭辞 `sk-polaris-` のクライアント API キー。 |
| `PANEL_PASSWORD` | 初期設定まで空 | Web コントロールパネルのアクセスパスワード。 |
| `SETUP_TOKEN` | 空 | リモート初期設定用の一意な 24 文字以上のトークン。生成・ログ出力しない。直接 localhost では不要。 |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Web コントロールパネルセッションの有効期間（秒）。 |
| `PANEL_COOKIE_SECURE` | 自動 | `true` に設定すると Cookie の送信を HTTPS に強制します。空の場合は `X-Forwarded-Proto` から自動検出します。 |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | ログインレート制限ウィンドウ（秒）。 |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | ウィンドウ期間内に単一クライアントに許可される最大ログイン失敗回数。 |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | メモリ内ログイン制限機能が追跡する最大クライアントアドレス数。 |
| `MAX_REQUEST_BODY_MB` | `64` | 最大 HTTP リクエストボディサイズ（MiB）。超過したリクエストにはプロトコル固有のエラーが返されます。 |
| `TRUST_PROXY_HEADERS` | `false` | 転送ヘッダーを上書きする信頼できるリバースプロキシ配下にある場合のみ有効にします。 |
| `CREDENTIALS_DIR` | `./backend/data/creds` | 認証情報の保存ディレクトリ。Docker では `/app/backend/data/creds` をホストにマウントします。 |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Code Assist バックエンドエンドポイント。 |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Google Antigravity バックエンドエンドポイント。 |
| `PROXY` | 空 | オプションの HTTP、HTTPS、または SOCKS プロキシ。 |
| `RETRY_429_ENABLED` | `true` | レート制限および一時的なアップストリームエラーに対する有界リトライを有効化。既存設定との互換性のために旧名を維持。 |
| `RETRY_429_MAX_RETRIES` | `5` | 一時的なアップストリームエラーに対する最大リトライ回数。 |
| `RETRY_429_INTERVAL` | `1` | 一時的リトライの基本バックオフ間隔（秒）。 |
| `AUTO_DISABLE` | `false` | 設定された重大なエラーの発生時に認証情報を自動無効化。 |
| `AUTO_DISABLE_ERROR_CODES` | `403` | 重大なエラーとみなすステータスコードのカンマ区切りリスト。 |
| `ROUTING_STRATEGY` | `balanced` | 方式：`balanced`、`priority`、`weighted`、`least_latency`、`lowest_cost`。 |
| `PREFERRED_PROVIDER` | 空 | `priority` ポリシーで優先されるプロバイダー（例: `google_antigravity`、`google_ai_studio`）。 |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | プロバイダー推論タイムアウト（5〜900 秒）。 |
| `RESPONSE_CACHE_ENABLED` | `false` | 温度 0、非ストリームの決定的応答のメモリキャッシュ。 |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | キャッシュ有効秒数。 |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | キャッシュ応答の最大件数。 |
| `GUARDRAILS_ENABLED` | `false` | 呼び出し前の保護を有効化。 |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | 送信文のメール、カード、API キーをマスク。 |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | プロンプトインジェクションを HTTP 400 で拒否。 |
| `GUARDRAILS_BLOCKED_KEYWORDS` | 空 | カンマ区切りの禁止語。大文字小文字を区別しない。 |
| `PRICING_SYNC_ENABLED` | `true` | LiteLLM 価格をバックグラウンド更新し、オフラインでは最後の正常コピーを保持。 |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | 価格更新間隔：1～168 時間。 |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | ストリーミング途切れ防止機能の最大継続リトライ回数。 |
| `TOKEN_COMPRESSION_ENABLED` | `true` | プロバイダーへのルーティング前に長大な会話履歴を圧縮。 |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | コンテキスト圧縮を開始する推定入力トークンしきい値。 |
| `TOKEN_COMPRESSION_TARGET` | `24000` | 圧縮後の目標推定入力トークン数。しきい値未満にする必要があります。 |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | 圧縮時に必ず保持する最新のユーザーターン最小数。 |
| `COMPATIBILITY_MODE` | `false` | システムメッセージをサポートしないクライアント/モデル向けに自動変換。 |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | 利用可能な場合にモデルの思考プロセス（reasoning）を返却。 |
| `MONGODB_URI` | 空 | MongoDB 互換ストレージ。 |
| `POSTGRESQL_URI` | 空 | 任意の PostgreSQL ストレージ。 |
| `CODE_ASSIST_CLIENT_ID` | 同梱デスクトップクライアント | Code Assist OAuth Client ID のオプションの上書き。 |
| `CODE_ASSIST_CLIENT_SECRET` | 同梱デスクトップクライアント | Code Assist OAuth Client Secret のオプションの上書き。 |
| `ANTIGRAVITY_CLIENT_ID` | 同梱デスクトップクライアント | Google Antigravity OAuth Client ID のオプションの上書き（プロバイダー画面でも設定可能）。 |
| `ANTIGRAVITY_CLIENT_SECRET` | 同梱デスクトップクライアント | Google Antigravity OAuth Client Secret のオプションの上書き。 |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Google AI Studio Generative Language API エンドポイントのオプションの上書き。 |
| `XAI_API_URL` | `https://api.x.ai/v1` | SpaceXAI Console API キー認証用エンドポイントのオプションの上書き（プロバイダー画面でも設定可能）。 |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Grok Build OAuth サブスクリプションエンドポイントのオプションの上書き。 |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Grok Build OAuth Issuer のオプションの上書き。コンソールは `x.ai` ドメイン配下の HTTPS ホストのみを受け入れます。 |
| `XAI_CLIENT_ID` | 同梱公開クライアント | Grok Build PKCE OAuth Client ID のオプションの上書き。 |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Grok Build OAuth および SpaceXAI Console API リクエスト共通の HTTP User-Agent のオプションの上書き。 |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | OpenAI Platform API エンドポイントのオプションの上書き（プロバイダー画面でも設定可能）。 |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Codex 推論およびアカウントモデルリストエンドポイントのオプションの上書き。 |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Codex アカウントレート制限確認エンドポイントのオプションの上書き。 |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Codex デバイス認可サービスのオプションの上書き。 |
| `CODEX_CLIENT_ID` | 同梱公開クライアント | Codex デバイス OAuth Client ID のオプションの上書き。 |
| `CODEX_USER_AGENT` | Codex CLI 互換値 | Codex リクエスト用のオプションの User-Agent 上書き。 |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Claude Code 専用 Messages エンドポイント。 |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Claude Code PKCE 認可エンドポイントのオプションの上書き。Anthropic / Claude 公式ホストのみ受付。 |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Claude Code トークンエンドポイントのオプションの上書き。Anthropic / Claude 公式ホストのみ受付。 |
| `CLAUDE_CLIENT_ID` | 同梱公開クライアント | Claude Code PKCE OAuth Client ID のオプションの上書き。 |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | Claude Code 専用 User-Agent。 |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Providers の独立した Claude Platform エンドポイント。 |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | Claude Platform 独自の User-Agent。 |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Google Antigravity プロトコルレベルリクエスト用のオプションの User-Agent 上書き。 |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Google Antigravity ペイロード層 userAgent フィールドのオプションの上書き。 |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | 認証付き `GET /metrics` を有効化。 |
| `METRICS_TOKEN` | 空 | Prometheus に必要な UTF-8 で 32 バイト以上の Bearer トークン。 |
| `OTEL_EXPORT_ENABLED` | `false` | 本文を含まない OTLP/HTTP 集計出力を有効化。 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 空 | HTTPS コレクター。URL 内の認証情報は禁止。 |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | 出力間隔：15～300 秒。 |
| `LANGFUSE_PUBLIC_KEY` | 空 | 秘密キーと併せて Langfuse を有効化。 |
| `LANGFUSE_SECRET_KEY` | 空 | トレース用 Langfuse 秘密キー。 |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse 取り込み先。 |
| `LOG_LEVEL` | `info` | 実行時のログレベル。 |
| `LOG_MAX_MB` | `10` | ログファイルがローテーションされるまでの最大サイズ（MB）。 |
| `LOG_BACKUP_COUNT` | `3` | 保持するローテーションログファイルの世代数。 |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | ファイルログの出力先パス。Docker では `/app/backend/data/logs` をホストにマウントします。 |

### 圧縮の制御

グローバルな AI Quality ポリシーが上限です。仮想キーは継承または無効化のみ可能で、現在のリビジョン付きで `PATCH /api/virtual-keys/{key_id}/quality-policy` を使います。`inherit` はキーの制限を解除します。認証済みリクエストは `x-polaris-compression: off` を指定でき、省略または `inherit` ならグローバル/キーの設定に従います。全体で無効な圧縮の再有効化や強化はできません。安全な履歴の先頭部分だけを削除し、構造や推定が不確かな場合は無変更で送ります。トークン数は推定です。

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## クイックスタート SDK 連携

Polaris は、公式 Python SDK の標準 URL 動作に合わせて設計されています。ゲートウェイには非標準の重複パスプレフィックスは不要ですので、以下のようにクライアントを設定してください。

以下の例では仮想モデル `polaris` を使用しています。事前にモデル管理画面でフォールバック優先順位を設定するか、特定のプロバイダーモデル ID に置き換えてください。

### OpenAI Python SDK

OpenAI のベース URL に `/v1` を指定します。SDK は自動的に `/chat/completions` を末尾に追加します。

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "このリポジトリについて1段落で説明してください。"}]
)
```

同一クライアントで OpenAI Responses API を呼び出すこともできます:

```python
response = client.responses.create(
    model="polaris",
    instructions="簡潔に回答してください。",
    input="このリポジトリについて1段落で説明してください。"
)

print(response.output_text)
```

Responses 互換レイヤーは、テキスト入力、画像入力、非ストリーミング Function Tool、および SSE テキストストリーミングをサポートします。OpenAI ホスト型の組み込みツール、永続化されたレスポンス履歴、ストリーミング関数呼び出しについては、Polaris がこれらの OpenAI 独自仕様を実行、永続化、または暗黙的に破棄しないため、明確にエラーを返して拒否します。

### Anthropic Python SDK

Anthropic のベース URL にはゲートウェイのオリジンを直接指定します。SDK は自動的に `/v1/messages` を末尾に追加します。

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "簡潔なコミットメッセージを作成してください。"}]
)
```

### Google GenAI Python SDK

Google GenAI のベース URL にはゲートウェイのオリジンを直接指定します。SDK は自動的に `/v1beta/models/{model}:generateContent` などのデフォルトモデルルートを追加します。

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
    contents="短い Python 関数を書いてください。",
    config=types.GenerateContentConfig(
        system_instruction="あなたは有能なアシスタントです。"
    )
)
```

### 対応エンドポイント一覧

Polaris は、余分な製品名前空間プレフィックスなしで標準の SDK 互換ルートを提供します:

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

認証エラー、リクエスト検証エラー、ルーティングエラー、アップストリームエラー、ストリーミング開始前の失敗は、すべて対応する SDK インターフェースのネイティブエラー構造でラップされます。すべての HTTP レスポンスには `X-Request-ID` ヘッダーが含まれ、クライアントはこのヘッダーに識別子を渡すことでリクエストフローの追跡が可能です。アップストリームからレート制限または一時的な利用不可が返された場合、ゲートウェイは `Retry-After` ヘッダーをそのまま透過的に保持します。

<a id="model-features"></a>

## モデル機能と高度な制御

コンソールの「モデル」ページでは、有効なプロバイダー認証情報から検出されたモデルを集約して仮想モデル `polaris` を構築します。各基礎モデルの優先順位を一度設定すれば、サポートされている任意の SDK から `polaris` を利用できます。Polaris は第 1 順位のモデルをサポートする健全な認証情報間で負荷分散を行い、そのモデルが利用不可になった場合は設定順に従って自動的にフォールバックを試行します。特定のモデルを決定論的に指定する必要があるクライアントのために、プロバイダー固有のモデル ID もそのまま利用可能です。空のリストを保存すると、プロバイダー認証情報に影響を与えることなく `polaris` を無効化できます。

モデル検出はプロバイダー認識型です。共通モデルは複数のプロバイダーでサポートされ、固有モデルは互換性のある認証情報でのみ処理されます。検証済みの各認証情報は独自のプロバイダーカタログを保持し、ルーターは一般的なプロバイダーの推測よりも認証情報が明示的に宣言したサポートを優先します。カタログを更新するとプロバイダーの現在の可用性が再取得され、利用不可となった項目も復旧または削除されるまで設定内に表示され続けます。

特定のモデルに対してアップストリームが `404` を返した場合、Polaris はプロバイダー全体を無効化するのではなく、その認証情報とモデルのスコープで利用不可ルートを記録します。そのルートは直ちに一時的に回避され、クリアされるか認証情報が再検証されるまで**利用不可モデルルート**一覧に表示されます。これにより、単一アカウントのサブスクリプション権限やリージョン制限が同じプロバイダー配下の他の健全なアカウントに影響を与えるのを防ぎます。有効な認証情報のいずれも要求されたモデルを宣言または推測できない場合、ゲートウェイは不適切なプロバイダーにランダムに転送することなく、互換性のある認証情報が存在しない旨のエラーを明確に返します。

Polaris は、モデル名に含まれる機能プレフィックスおよびサフィックスを解釈します:

- `fake-streaming/{model}` または設定された疑似ストリーミングプレフィックス（SSE 形式を必須とするクライアント用）。
- `streaming-anti-truncation/{model}` または設定された途切れ防止プレフィックス（長文ストリーミング生成時の自動復旧用）。
- 思考深度サフィックス（`-high`、`-medium`、`-low`、`-minimal`、`-max` など、サポートされている Gemini 系モデル用）。
- 検索グラウンディングサフィックス（`-search` など、Google Search グラウンディング対応モデル用）。

プロバイダーアダプターは、アップストリームにリクエストを送信する前にこれらの機能識別子を自動的に正規化します。

<a id="usage-and-cost-visibility"></a>

## 利用状況とコストの透明性

各プロバイダー試行、再試行、フォールバックを別々に数え、トレースは論理リクエストの最終結果を保持します。結果、認証情報、申告された入力/出力/キャッシュ/推論トークン、推定削減量、USD コストを記録します。未報告の使用量は実測ゼロではありません。期間はブラウザーのタイムゾーンの固定境界で、日次表示は 00:00–23:00 です。LiteLLM 公開価格は既定で起動時と 24 時間ごとに更新し、最後の正常なコピーをアトミックに維持します。失敗しても推論は止まりません。認証情報ディレクトリの `model_pricing.json` が優先され、単価は 100 万トークン当たりです。ダッシュボード、`/api/virtual-keys`、`/metrics` に集計を公開します。プロバイダーの請求と tokenizer が基準です。

仮想キーは日次/月次予算、RPM/TPM のスライディングウィンドウ、有効期限、glob モデル規則に対応します。SHA-256 ハッシュのみ保存し、秘密値は作成時だけ表示します。

<a id="credential-workflow"></a>

## 認証情報の設定ワークフロー

1. Polaris を起動します。
2. VPS では `http://サーバーのIP:4283`、ローカル開発では `http://127.0.0.1:4283` にアクセスします。
3. チェックを完了し所有者パスワードを作成します。リモート初期設定前に、24 文字以上の一意な `SETUP_TOKEN` または `PANEL_PASSWORD` を設定してください。トークンは自動生成・ログ出力されません。
4. 「プロバイダー」ページでアカウント、API キー、または Ollama 接続を追加します。
5. 認証情報の有効性を検証し、パネル内でクールダウンやエラー状態を監視します。 **Credentials** (`/credentials`).
6. コーディングツールを上記のサポートされている API インターフェースのいずれかに接続します。

Google Antigravity 認証情報を追加する際、ログイン完了後に Google はブラウザを `http://localhost:4283/callback` にリダイレクトします。ローカルマシンでは OAuth 成功画面が直接表示されます。VPS の場合、その `localhost` はユーザーのローカルブラウザを指すためページが開かないことがあります。ブラウザのアドレスバーから URL 全体をコピーし、プロバイダー画面に戻って `Callback URL` 欄に貼り付け、`認証情報を保存` をクリックしてください。

Google AI Studio は OAuth ではなく API キー認証を使用します。プロバイダー画面でキーを追加すると、Polaris は Google のモデルカタログと照合して検証し、プロバイダー認証情報として保存して、互換性のある Gemini または Gemma リクエストをルーティングします。スマートルーターは、共通の Gemini モデルについて AI Studio と Google Antigravity 間で自動フェイルオーバーを行い、固有モデルは互換性のある認証情報にのみ送信します。

Google AI Studio の一括インポートは、JSON ファイルおよび JSON ファイルを含む ZIP アーカイブをサポートしています。JSON ドキュメントには単一のキー、`api_keys` 配列、またはキーオブジェクトの配列を含めることができます:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

インポートされた各キーは保存前に厳格に検証されます。同一バッチ内の重複キーはスキップされ、既存のキーは再検証されて更新され、無効なレコードはキーの平文を漏洩することなく個別に報告されます。

Grok Build は PKCE OAuth 認証情報をサポートし、SpaceXAI Console は API キーをサポートします。SpaceXAI Console キーは保存前に Grok Build モデルカタログと照合して検証されます。Grok Build OAuth の場合、Polaris は認可リンクを生成します。認可完了後、認可画面に表示されたコードをコピーしてフォームに貼り付けてください。リフレッシュトークンが存在する場合はアクセストークンが自動更新され、両方の認証情報タイプともに現在のカタログで宣言された Grok Build モデルのみを公開します。Credentials 画面では、Grok Build OAuth アカウントの月間クレジット消費量、および xAI から提供されている場合は週間使用量を確認できます。このアカウントレベルの請求ビューは SpaceXAI Console API キーでは利用できません。

Codex は OpenAI デバイス認可フローを使用します。プロバイダー画面でデバイスコードを生成し、表示された検証 URL を開き、コードを入力してログインを完了した後、認可状態を確認します。Polaris は Codex が返したアカウントスコープのモデルカタログを保存し、必要に応じて OAuth アクセストークンを更新し、Codex Responses トランスポートを通じて互換リクエストを転送します。OpenAI Platform は API キー認証を使用し、キーはアカウントモデルカタログを通じて検証された後にCredentials へ追加されます。両製品ともに JSON および ZIP インポートをサポートし、プロバイダー固有の検証と重複排除が行われます。

Claude Code は Anthropic の PKCE OAuth フローを使用します。認可リンクを生成して認可を完了し、取得した認可コードをプロバイダー画面に貼り付けます。Claude Platform は Anthropic API キーを受け入れます。両製品ともに認証情報ごとにサポートされているモデルを検出し、Anthropic Messages トランスポートを使用し、可能な場合は Claude Code アクセストークンを自動更新し、検証付きの JSON / ZIP インポートをサポートします。

Muse Code は Meta デバイス認証を使います。**Providers → Muse Code** でリンクを取得し、Meta でコードを承認して **Save credential** に戻ります。直接接続のため CLI、Linux、VPS は不要です。モデル接頭辞は `muse-code/`、表示名は任意です。プラン、セッション/週クォータ、リセット・観測日時はプロバイダーが返した場合だけ表示します。未取得は残量 100% を意味しません。更新では現在のセッションで契約を確認して推論キーを取得します。セッション失効時は再ログインしてください。

Kiro は Google/GitHub のブラウザー OAuth、AWS デバイス認証、API キーに対応します。詳細設定は方式別で、実行リージョン、AWS トークンリージョン/開始 URL、API キーのプロファイル ARN を扱います。

Ollama 接続はエンドポイントごとに設定され、保護されたサーバーやクラウドサーバー向けのオプションの Bearer API キーを含めることができます。Polaris は `/api/tags` を通じてモデルを検出し、`/api/chat` を介して推論をルーティングします。Polaris が Docker 内で動作している場合、`localhost` はコンテナ自身を指します。ホストゲートウェイアドレスまたはネットワーク経由でアクセス可能な Ollama エンドポイントを使用してください。

認証情報全体のインポートおよび Google Antigravity の一括インポートは、最大 10 MB のアーカイブ、最大 500 ファイル、単一認証情報ファイル最大 2 MB、解凍後合計最大 25 MB をサポートします。Google AI Studio、OpenAI、Anthropic、Ollama の個別プロバイダーインポートには、ファイルあたり最大 2 MB、最大 200 件の JSON レコード、解凍後最大 5 MB という厳格な制限が適用されます。

**Credentials**（`/credentials`）はアカウントとキーをプロバイダー別にまとめます。管理ダイアログには識別情報、モデル、状態、利用可能な操作を表示します。OAuth はプラン、クレジット、期間別/モデル別クォータを返す場合があります。API キーからメール、契約、請求を自動取得できるとは限らず、不明な項目は取得不可とします。

**Download ZIP** は認証情報を出力し、**Import ZIP** は複数プロバイダーを検証・重複排除して項目別にエラーを報告します。読み込みやカタログ取得の成功は推論権限の証明ではありません。**Test model** は実際の呼び出しで、クォータ消費や課金が発生し得ます。ZIP は秘密情報を含みます。SQLite と設定全体には **Settings** の暗号化バックアップを使ってください。

Google Antigravity 認証情報は `google-antigravity-{account_fingerprint}.json` の形式で保存され、フィンガープリントは平文を漏洩することなく正規化されたメールアドレスから生成されます。Google AI Studio は `google-ai-studio-{key_fingerprint}.json`、Grok Build OAuth は `grok-{account_fingerprint}.json`、SpaceXAI Console は `xai-console-{key_fingerprint}.json`、Codex は `openai-codex-{account_fingerprint}.json`、OpenAI Platform は `openai-platform-{key_fingerprint}.json`、Claude Code は `claude-code-{account_fingerprint}.json`、Claude Platform は `claude-platform-{key_fingerprint}.json`、Ollama 接続は `ollama-{connection_fingerprint}.json` を使用します。レガシーな `provider_*.json` および `xai-grok-*.json` 認証情報との下位互換性も維持されており、エクスポート時には標準名に正規化されます。

認証情報モード名:

- `code_assist`: 標準の Code Assist 認証情報。
- `provider`: 汎用プロバイダーバックエンド認証情報。

<a id="storage"></a>

## データストレージ

SQLite を推奨します。Compose は `/app/backend/data` を `polaris-data` に永続化します。直接 Docker を使う場合は `/app/backend/data/creds` と `/app/backend/data/logs` を `/opt/polaris/creds`、`/opt/polaris/logs` などにマウントします。

PostgreSQL は任意、MongoDB は互換用で Redis 不要です。外部 DB は一方だけ設定してください。初期化失敗時は停止し、SQLite に黙って戻りません。外部 DB でも水平拡張はできず、worker・レプリカは各 1 つです。可搬な暗号化バックアップは SQLite のみで、バックエンド間のライブ移行は非対応です。

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[データストレージ](../storage.md)

環境変数経由での認証情報のインポートもサポートされています。コントロールパネルから操作するか、以下のいずれかの変数に生の JSON 文字列を設定するか、Base64 エンコードされた `_B64` サフィックス付きの変数を使用します:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

ペイロードには単一の認証情報オブジェクト、配列、または `{ "credentials": [...] }` 構造を使用できます。

<a id="development"></a>

## 開発ガイド

本セクションはプロジェクト貢献者およびローカルデバッグ向けです。本番環境のデプロイには、永続化ホストボリュームを備えた Docker を使用してください。

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

[品質ゲート](../quality-gates.md)はタスク、フェーズ、リリースを区別します。`python tools/quality_gate.py --list-suites` は任意の外部実接続チェックも一覧化します。[互換性契約](../compatibility.md)は SDK/管理ルート、移行、スキーマ、例を保護します。

すべてのチェックを通過後、サービスを起動します:

```bash
python backend/main.py
```

本番稼働のベースラインは Python 3.12 であり、CI 自動テストは Python 3.12 および 3.14 をカバーしています。Pull Request の提出手順とコードレビュー基準については、[貢献ガイド](../../CONTRIBUTING.md)を参照してください。

<a id="deployment-notes"></a>

## デプロイ時の注意事項

- 認証情報を含む JSON ファイルや `.env` ファイルは絶対にコミットしないでください。
- クライアント連携用には専用の `API_KEY` を、コンソールアクセス用には個別の `PANEL_PASSWORD` を設定してください。
- 永続化された認証情報ボリュームや外部データベースへのアクセスを厳格に制限し、プラットフォームレベルで保存時暗号化（encryption at rest）を有効にしてください。ルーターはプロバイダートークンを復号して読み取れる必要があります。
- サービスを localhost 以外に公開する場合は、必ず TLS が有効なリバースプロキシの背後に Polaris を配置してください。
- リバースプロキシが `Host` ヘッダーを保持し、`X-Forwarded-Proto` を渡すように設定してください。HTTPS 終端が保証されている場合は `PANEL_COOKIE_SECURE=true` を設定します。
- `X-Forwarded-For` および `X-Forwarded-Proto` を上書きする信頼できるプロキシ経由でのみアクセス可能な場合にのみ、`TRUST_PROXY_HEADERS=true` を設定してください。
- プロセス生存確認（liveness）には `GET /health` を、ストレージ層を含む準備完了確認（readiness）には `GET /ready` を使用してください。
- 外部テレメトリは任意です。Prometheus には `PROMETHEUS_EXPORT_ENABLED` と強力な `METRICS_TOKEN` が必要です。OpenTelemetry は集計のみを出力し、プロンプト/応答本文は出力しません。[可観測性](../observability.md)を参照。
- Docker イメージは起動初期にマウントされたデータディレクトリの所有権を修正する間のみ root 権限で動作し、その後は非特権ユーザー `gateway` に降格して実行されます。
- ブラウザクライアントからクロスオリジンアクセスが必要な場合は、`CORS_ORIGINS` に信頼できるオリジンを明示的に指定してください。
- SQLite の更新・移動前に[認証付き暗号化バックアップ](../backup-and-restore.md)を使用し、アーカイブとパスフレーズを `polaris-data` の外に保存してください。
- Docker イメージの公開では、Docker Hub 用にリポジトリシークレット `DOCKERHUB_USERNAME` と `DOCKERHUB_TOKEN` を使用し、GitHub Packages（`ghcr.io/nguywnben/polaris`）用に組み込みの `GITHUB_TOKEN` を使用します。カスタムの Docker Hub イメージ名に公開する場合のみ、オプションの `IMAGE_NAME` 変数を設定してください。
- 1.x 系では `WORKERS=1` および単一のアプリケーションレプリカを維持してください。外部ストレージは分散オーケストレーションの代替にはなりません。
- 標準的な正規管理ルート `/api/credentials` を使用してください。ベータ版の別名 `/api/creds` は 1.0.0 で完全に削除されました。
- ベータ版のデプロイを移行する前に、[1.0 へのアップグレードガイド](../upgrading-to-1.0.md)を確認してください。
- 既存のインスタンスをアップグレードまたはロールバックする際は、[アップデートガイド](../updating.md)を参照してください。
- タグ付けやイメージのリリース前に、整備されている[リリースチェックリスト](../release-checklist.md)を順に確認してください。
- 利用制限やクォータに合わせて、適切なログ保持ポリシーと認証情報ローテーションポリシーを策定してください。
- リポジトリやクラウドプラットフォームのスキャンによってシークレットの漏洩が検出された場合は、直ちにその認証情報を失効・ローテーションしてください。
- Render デプロイマニフェストは永続ディスクを備えた有料サービスを使用します。Render の無料サービスはエフェメラルなファイルシステムを使用するため、一時的な試用目的にのみ適しています。

<a id="community-and-project-health"></a>

## コミュニティと健全性

- Pull Request を作成する前に[貢献ガイド](../../CONTRIBUTING.md)をお読みください。
- セキュリティ脆弱性の報告は、[セキュリティポリシー](../../SECURITY.md)に記載された非公開の手順に従ってください。
- 各リリースの変更内容については[変更履歴](../../CHANGELOG.md)をご確認ください。
- 本プロジェクトのすべての活動において[行動規範](../../CODE_OF_CONDUCT.md)を遵守してください。

<a id="acknowledgements-inspirations"></a>

## 謝辞 & インスピレーション

Polaris は、オープンソースの AI ルーティング、オブザーバビリティ、ゲートウェイコミュニティの成果の上に築かれています。以下のプロジェクトの創設者およびメンテナーに深く感謝いたします:

| プロジェクト | 説明 | Stars |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | マルチプロバイダーのキー管理および Web ベース API 集約のアーキテクチャインスピレーション | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | AI コーディング CLI 向けマルチプロトコルプロキシおよびフォーマット変換レイヤーの先駆的実装 | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | 業界標準の統合 LLM プロキシ、ロードバランシング、フォールバックルーティング | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | 超高速 AI ゲートウェイアーキテクチャ、ルーティング戦略、高耐障害性フォールバック | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | オープンソース LLM エンジニアリングプラットフォーム、トレース、可観測性、メトリクス収集 | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## ライセンス

Polaris は [MIT ライセンス](../../LICENSE) のもとで公開されています。
