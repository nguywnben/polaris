<div align="center">
  <h1>
    <img src="../../frontend/assets/logo.png" alt="Omni Gateway Logo" width="48" height="48" style="vertical-align: middle;" /> <span style="vertical-align: middle;">Omni Gateway</span>
  </h1>
  <p><b>Universal AI Router & Cổng chuyển tiếp đa nhà cung cấp hợp nhất cho các công cụ AI Coding</b></p>

  <p>
    <a href="https://github.com/nguywnben/omni-gateway/releases"><img src="https://img.shields.io/github/v/release/nguywnben/omni-gateway?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/omni-gateway/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/omni-gateway?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/omni-gateway/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/omni-gateway/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/omni-gateway"><img src="https://img.shields.io/docker/pulls/nguywnben/omni-gateway?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/i18n-15%20languages-orange?style=flat-square" alt="15 Languages">
  </p>

  <p>
    <a href="#nha-cung-cap-duoc-ho-tro"><b>🌐 Nhà cung cấp hỗ trợ</b></a> •
    <a href="#tinh-nang-cot-loi"><b>⚡ Tính năng cốt lõi</b></a> •
    <a href="#trien-khai"><b>🐳 Triển khai Docker</b></a> •
    <a href="#khoi-dong-nhanh-tich-hop-sdk"><b>🔌 Tích hợp SDK</b></a> •
    <a href="../architecture.md"><b>📖 Kiến trúc</b></a>
  </p>

  <p>
    <b>Tài liệu được duy trì:</b><br>
    <a href="../../README.md">English</a> • <b>Tiếng Việt</b>
  </p>
</div>

---

Console hỗ trợ 15 ngôn ngữ. Tiếng Anh và tiếng Việt được rà soát ngữ nghĩa; 13 ngôn ngữ cộng đồng
còn lại thuộc lớp tương thích và sẽ dùng nội dung tiếng Anh khi thiếu thông điệp.

Một router AI vạn năng dành cho các công cụ lập trình (coding tools). Omni Gateway cung cấp khả năng tự động chuyển đổi dự phòng thông minh (smart auto-fallback), dọn dẹp ngữ cảnh nhận biết token, minh bạch hóa mức độ sử dụng và chuyển đổi định dạng liền mạch để các agent cục bộ, trợ lý IDE và script tự động hóa có thể tận dụng dung lượng LLM miễn phí lẫn trả phí thông qua một giao diện API ổn định duy nhất.

> **Phạm vi sản phẩm:** Omni Gateway đang được hoàn thiện cho mô hình tự triển khai production bởi
> một cá nhân hoặc một nhóm tin cậy. Topology production được hỗ trợ gồm một worker và một replica;
> Docker Compose, quyền chủ sở hữu cục bộ, SQLite, định tuyến nhà cung cấp và các tuyến SDK đã ghi tài
> liệu thuộc tier Core. PostgreSQL, truy cập nhóm qua OIDC, reverse proxy và telemetry bên ngoài là
> các tùy chọn Advanced. MongoDB và các ngôn ngữ không được duy trì trực tiếp thuộc tier
> Compatibility. Điều phối nhiều replica và triển khai Kubernetes nằm ngoài phạm vi sản phẩm.
> Xem [đặc tả Production Self-Hosted R1](../specs/production-self-hosted.md).

## Tại sao nên chọn Omni Gateway

Quy trình lập trình hiện đại thường kết hợp nhiều client và provider: công cụ tương thích OpenAI, SDK Gemini native, agent theo phong cách Anthropic, thông tin xác thực Google và các định tuyến mô hình thử nghiệm. Omni Gateway đóng vai trò trung gian giữa các client đó và backend mô hình, giúp mỗi công cụ duy trì định dạng giao tiếp vốn có trong khi gateway xử lý việc định tuyến, thử lại (retry), dọn dẹp request và chuẩn hóa phản hồi.

## <a id="tinh-nang-cot-loi"></a>Tính năng cốt lõi

Omni Gateway ghi lại số lần gọi nhà cung cấp, tỷ lệ thành công, thông tin xác thực được sử dụng, số token do nhà cung cấp báo cáo, lượng token ước tính tiết kiệm nhờ nén ngữ cảnh và chi phí USD ước tính cho mỗi lượt gọi theo bảng giá mô hình được duy trì. Dashboard phân biệt dữ liệu usage thật sự bằng 0 với usage không được nhà cung cấp báo cáo. Có thể ghi đè hoặc bổ sung giá bằng tệp `model_pricing.json` trong thư mục thông tin xác thực; giá được tính bằng USD trên một triệu token. Dữ liệu tổng hợp có trên dashboard, theo từng khóa ảo qua API quản trị `/api/virtual-keys` và qua endpoint Prometheus `/metrics`. Mức tiết kiệm và chi phí luôn được ghi là ước tính vì tokenizer và quy tắc tính phí của nhà cung cấp mới là căn cứ cuối cùng.

Khóa API ảo cho phép một gateway phục vụ nhiều client với giới hạn riêng. Mỗi khóa có thể đặt ngân sách USD theo ngày và tháng, giới hạn số yêu cầu và token mỗi phút, thời điểm hết hạn và danh sách mô hình cho phép theo mẫu glob. Khóa được lưu dưới dạng băm SHA-256; bí mật dạng văn bản thuần chỉ hiển thị một lần khi tạo.

## Giao diện Console

![Omni Gateway credential pool](../assets/screenshots/credential-pool.png)

## <a id="nha-cung-cap-duoc-ho-tro"></a>Nhà cung cấp được hỗ trợ

Omni Gateway chuyển đổi các yêu cầu một cách liền mạch giữa các nhà cung cấp AI hàng đầu, runtime cục bộ và các endpoint OAuth:

| Nhà cung cấp | Loại xác thực | Giao thức hỗ trợ | Tự động Failover | Hỗ trợ Streaming |
| :--- | :---: | :---: | :---: | :---: |
| <img src="../../frontend/assets/providers/google-antigravity-logo.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Gemini Native, OpenAI, Anthropic | ✅ | ✅ |
| <img src="../../frontend/assets/providers/google-ai-studio-logo.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API Key | Gemini Native, OpenAI, Anthropic | ✅ | ✅ |
| <img src="../../frontend/assets/providers/claude-code-logo.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (Anthropic) | Anthropic Messages, OpenAI, Gemini | ✅ | ✅ |
| <img src="../../frontend/assets/providers/claude-platform-logo.png" width="18" height="18" valign="middle" /> **Claude Platform** | API Key | Anthropic Messages, OpenAI, Gemini | ✅ | ✅ |
| <img src="../../frontend/assets/providers/codex-logo.png" width="18" height="18" valign="middle" /> **Codex** | OAuth (OpenAI) | OpenAI Completions & Responses | ✅ | ✅ |
| <img src="../../frontend/assets/providers/openai-platform-logo.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API Key | OpenAI Completions & Responses | ✅ | ✅ |
| <img src="../../frontend/assets/providers/grok-build-logo.png" width="18" height="18" valign="middle" /> **Grok Build** | API Key | OpenAI Tương thích, Anthropic, Gemini | ✅ | ✅ |
| <img src="../../frontend/assets/providers/spacexai-console-logo.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API Key | OpenAI Tương thích | ✅ | ✅ |
| <img src="../../frontend/assets/providers/ollama-logo.png" width="18" height="18" valign="middle" /> **Ollama (Cục bộ / Tự lưu trữ)** | Cục bộ / Base URL | OpenAI Tương thích | ✅ | ✅ |

## Kiến trúc

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | Tích hợp IDE
        |
        v
Omni Gateway
  xác thực -> chuyển đổi định dạng -> dọn dẹp nhận biết token -> định tuyến -> dự phòng -> streaming
        |
        v
provider adapters
  Google Antigravity | Google AI Studio | Grok Build | SpaceXAI Console | Codex | OpenAI Platform | Claude Code | Claude Platform | Ollama
```

API công khai luôn duy trì tính ổn định trong khi các adapter đặc thù của từng nhà cung cấp liên tục phát triển bên dưới Omni Gateway.

## Cấu trúc thư mục kho mã nguồn

```text
backend/       Gốc cấu thành FastAPI, lõi định tuyến, bộ chuyển đổi, lưu trữ và kiểm thử
frontend/      Giao diện bảng điều khiển, style, script và tài nguyên hình ảnh provider
deploy/        Định nghĩa container, manifest nền tảng và script hệ điều hành
docs/          Ghi chú kiến trúc và tài liệu bảo trì của dự án
.github/       CI, tự động hóa phụ thuộc và biểu mẫu đóng góp
```

Xem [Kiến trúc](../architecture.md) để biết thêm về ranh giới các module, luồng xử lý yêu cầu, quyền sở hữu trạng thái và các ràng buộc phát hành hiện tại.

## <a id="trien-khai"></a>Triển khai

Docker Compose là cách triển khai production chuẩn cho profile một máy, một worker được hỗ trợ.
Hãy đi theo [Hướng dẫn cài đặt chuẩn](../installation.md) từ bước kiểm tra máy chủ đến Dashboard đã
xác thực. [Ma trận hỗ trợ cài đặt](../installation.md#support-matrix) ghi rõ bằng chứng cho Windows,
Linux, macOS và kiến trúc CPU; tài liệu không ngầm tuyên bố hỗ trợ ARM64.

Profile mặc định không cần dịch vụ bên ngoài, đồng thời lưu toàn bộ dữ liệu ứng dụng trong volume
`omni-gateway-data`. Mẫu môi trường tối thiểu ghim bản phát hành `1.5.0`; việc cập nhật
production phải theo [quy trình cập nhật và rollback Compose](../updating.md). Chỉ bật lưu trữ ngoài,
Team access, proxy, guardrail, cache hoặc telemetry qua `deploy/compose.advanced.yml` sau khi bản cài
đặt cơ bản đã hoạt động tốt.

Các script Python native trong `deploy/scripts`, `docker run` trực tiếp, Render và Zeabur chỉ thuộc
tầng tương thích, không có đầy đủ bằng chứng cài đặt/cập nhật/rollback của đường chuẩn. Image
production hiện chỉ phát hành cho `linux/amd64`; bản native `linux/arm64` chưa được phát hành vì
toàn bộ stack phụ thuộc đã khóa chưa có bằng chứng build và runtime tương đương.

### Phát triển cục bộ

Sử dụng quy trình làm việc bằng Python khi phát triển hoặc gỡ lỗi gateway cục bộ:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

Trên Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Mở bảng điều khiển tại:

```text
http://127.0.0.1:4283
```

Môi trường phát triển cục bộ sử dụng cùng một màn hình thiết lập trong lần chạy đầu tiên như triển khai Docker.

## Cấu hình

Omni Gateway đọc cấu hình ưu tiên từ các biến môi trường trước, sau đó đến cấu hình đã lưu, cuối cùng là các giá trị mặc định.

| Biến môi trường | Mặc định | Mục đích |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Địa chỉ lắng nghe (bind address). |
| `PORT` | `4283` | Cổng HTTP. |
| `HOST_PORT` | `4283` | Cổng phía máy chủ host chỉ được dùng bởi Docker Compose. |
| `WORKERS` | `1` | Số lượng worker được hỗ trợ cho chuỗi phiên bản 1.x. Các giá trị khác sẽ bị từ chối cho đến khi cơ chế đặt chỗ, cooldown, phiên làm việc và tổng hợp sử dụng được phối hợp đa tiến trình. |
| `CORS_ORIGINS` | trống | Danh sách origin trình duyệt phân tách bằng dấu phẩy được phép gọi API cross-origin. Để trống cho việc sử dụng console cùng origin. |
| `CORS_ORIGIN_REGEX` | trống | Biểu thức chính quy tùy chọn cho các origin trình duyệt động được quản lý. |
| `API_KEY` | tạo tự động | Key ưu tiên cho các request API client công khai. Phải bắt đầu bằng `sk-ogw-`. |
| `PANEL_PASSWORD` | trống cho đến khi thiết lập | Mật khẩu cho bảng điều khiển web. |
| `SETUP_TOKEN` | để trống | Bắt buộc trước khi thiết lập từ xa lần đầu; dùng giá trị riêng dài ít nhất 24 ký tự. Ứng dụng không tự sinh hoặc ghi giá trị này vào log. Thiết lập trực tiếp trên localhost không cần mã. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Thời gian sống của phiên bảng điều khiển web tính bằng giây. |
| `PANEL_COOKIE_SECURE` | tự động | Đặt `true` để bắt buộc cookie bảng điều khiển chỉ truyền qua HTTPS. Để trống để tự động phát hiện HTTPS qua `X-Forwarded-Proto`. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Cửa sổ giới hạn tần suất đăng nhập tính bằng giây. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Số lần đăng nhập thất bại tối đa cho phép trên mỗi client trong cửa sổ giới hạn. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Số lượng địa chỉ client tối đa được lưu trữ bởi bộ giới hạn đăng nhập trong bộ nhớ. |
| `MAX_REQUEST_BODY_MB` | `64` | Kích thước tối đa của phần thân (body) request HTTP tính bằng MiB. Các request SDK vượt kích thước sẽ trả về cấu trúc lỗi chuẩn của giao thức tương ứng. |
| `TRUST_PROXY_HEADERS` | `false` | Chỉ chấp nhận các header chuyển tiếp client/protocol từ một reverse proxy đáng tin cậy có ghi đè chúng. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Thư mục lưu trữ thông tin xác thực. Trong Docker, lưu giữ bền vững `/app/backend/data/creds` bằng volume máy chủ. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Endpoint backend của Code Assist. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Endpoint backend của Google Antigravity. |
| `PROXY` | trống | Proxy HTTP, HTTPS hoặc SOCKS tùy chọn. |
| `RETRY_429_ENABLED` | `true` | Bật tính năng thử lại có giới hạn đối với các lỗi giới hạn tần suất và lỗi tạm thời từ upstream. Tên cũ được giữ lại để tương thích cấu hình. |
| `RETRY_429_MAX_RETRIES` | `5` | Số lần thử lại tối đa đối với các lỗi tạm thời từ phía upstream. |
| `RETRY_429_INTERVAL` | `1` | Độ trễ cơ sở giữa các lần thử lại tạm thời tính bằng giây. |
| `AUTO_DISABLE` | `false` | Vô hiệu hóa thông tin xác thực sau khi gặp các lỗi nghiêm trọng đã được cấu hình. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Danh sách mã trạng thái lỗi nghiêm trọng phân tách bằng dấu phẩy. |
| `ROUTING_STRATEGY` | `balanced` | Credential selection policy: `balanced`, `priority`, `weighted`, `least_latency`, or `lowest_cost`. |
| `PREFERRED_PROVIDER` | trống | Nhà cung cấp được ưu tiên theo chiến lược `priority`, ví dụ `google_antigravity` hoặc `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Thời gian chờ phản hồi suy luận từ provider, giới hạn từ 5 đến 900 giây. |
| `RESPONSE_CACHE_ENABLED` | `false` | Lưu đệm trong bộ nhớ các phản hồi non-streaming tất định (temperature 0). |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Thời gian sống của mỗi mục trong bộ nhớ đệm phản hồi tính bằng giây. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Số lượng phản hồi tối đa được giữ trong bộ nhớ đệm trong bộ nhớ. |
| `GUARDRAILS_ENABLED` | `false` | Bật pipeline guardrails trước khi gọi. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Che giấu email, số thẻ và API key trong văn bản request gửi đi. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Từ chối các nỗ lực prompt-injection với HTTP 400. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | trống | Danh sách từ khóa không phân biệt hoa thường, phân tách bằng dấu phẩy, sẽ chặn request. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Số lần thử tiếp tục tối đa cho tính năng streaming chống ngắt quãng (anti-truncation). |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Nén lịch sử hội thoại quá lớn trước khi định tuyến đến provider. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Ngưỡng ước tính token đầu vào để kích hoạt cơ chế nén. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Mục tiêu ước tính token đầu vào sau khi nén. Phải nhỏ hơn ngưỡng kích hoạt. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Số lượt trò chuyện gần nhất của người dùng tối thiểu được giữ lại khi nén. |
| `COMPATIBILITY_MODE` | `false` | Chuyển đổi system message cho các client/mô hình không hỗ trợ chúng. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Trả về trường suy nghĩ/lập luận của mô hình (reasoning) khi có sẵn. |
| `MONGODB_URI` | trống | Chọn đường lưu trữ MongoDB chỉ thuộc tier Compatibility. |
| `POSTGRESQL_URI` | trống | Chọn lưu trữ PostgreSQL tùy chọn thuộc tier Advanced. |
| `CODE_ASSIST_CLIENT_ID` | tích hợp sẵn | Ghi đè tùy chọn cho Client ID OAuth của Code Assist. |
| `CODE_ASSIST_CLIENT_SECRET` | tích hợp sẵn | Ghi đè tùy chọn cho Client Secret OAuth của Code Assist. |
| `ANTIGRAVITY_CLIENT_ID` | tích hợp sẵn | Ghi đè tùy chọn cho Client ID OAuth của Google Antigravity. Có thể quản lý từ trang Providers. |
| `ANTIGRAVITY_CLIENT_SECRET` | tích hợp sẵn | Ghi đè tùy chọn cho Client Secret OAuth của Google Antigravity. Cấu hình qua env hoặc trang Providers khi client upstream thay đổi. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Ghi đè tùy chọn cho endpoint Generative Language API của Google AI Studio. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Ghi đè tùy chọn cho endpoint API SpaceXAI Console đối với xác thực API key. Có thể quản lý từ trang Providers. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Ghi đè tùy chọn cho endpoint gói thuê bao Grok Build OAuth. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Ghi đè tùy chọn cho đơn vị cấp phát Grok Build OAuth. Bảng điều khiển chỉ chấp nhận các host HTTPS thuộc `x.ai`. |
| `XAI_CLIENT_ID` | tích hợp sẵn | Ghi đè tùy chọn cho Client ID OAuth PKCE của Grok Build. |
| `XAI_USER_AGENT` | `grok-cli/omni-gateway` | Ghi đè tùy chọn cho HTTP User-Agent chung dùng cho các yêu cầu Grok Build OAuth và SpaceXAI Console API. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Ghi đè tùy chọn cho endpoint API OpenAI Platform. Có thể quản lý từ trang Providers. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Ghi đè tùy chọn cho endpoint suy luận và danh mục mô hình tài khoản của Codex. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Ghi đè tùy chọn cho endpoint kiểm tra giới hạn tần suất tài khoản Codex. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Ghi đè tùy chọn cho dịch vụ ủy quyền thiết bị của Codex. |
| `CODEX_CLIENT_ID` | tích hợp sẵn | Ghi đè tùy chọn cho Client ID OAuth thiết bị của Codex. |
| `CODEX_USER_AGENT` | tương thích Codex CLI | Ghi đè tùy chọn cho User-Agent đối với các request Codex. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Ghi đè tùy chọn cho endpoint API Messages của Claude Platform và Claude Code. Có thể quản lý từ trang Providers. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Ghi đè tùy chọn cho endpoint ủy quyền PKCE của Claude Code. Bảng điều khiển chỉ chấp nhận host Anthropic và Claude. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Ghi đè tùy chọn cho endpoint lấy token của Claude Code. Bảng điều khiển chỉ chấp nhận host Anthropic và Claude. |
| `CLAUDE_CLIENT_ID` | tích hợp sẵn | Ghi đè tùy chọn cho Client ID OAuth PKCE của Claude Code. |
| `CLAUDE_USER_AGENT` | `claude-cli/omni-gateway` | Ghi đè tùy chọn cho User-Agent đối với các request Claude Code và Claude Platform. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Ghi đè tùy chọn cho User-Agent giao thức Google Antigravity. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Ghi đè tùy chọn cho trường userAgent ở cấp payload của Google Antigravity. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Bật rõ ràng endpoint Prometheus `GET /metrics` có xác thực. |
| `METRICS_TOKEN` | trống | Bearer token tối thiểu 32 byte, bắt buộc khi bật xuất Prometheus. |
| `OTEL_EXPORT_ENABLED` | `false` | Bật xuất số liệu tổng hợp, không chứa nội dung qua OTLP/HTTP. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | trống | Endpoint HTTPS của OpenTelemetry collector; không cho phép nhúng thông tin xác thực trong URL. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Chu kỳ xuất số liệu tổng hợp, giới hạn từ 15–300 giây. |
| `LANGFUSE_PUBLIC_KEY` | trống | Bật xuất trace Langfuse cùng với secret key. |
| `LANGFUSE_SECRET_KEY` | trống | Secret key của Langfuse dùng cho xuất trace. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Endpoint tiếp nhận dữ liệu của Langfuse. |
| `LOG_LEVEL` | `info` | Mức độ chi tiết của nhật ký (log level). |
| `LOG_MAX_MB` | `10` | Dung lượng tối đa của file log đang hoạt động trước khi xoay vòng (rotation). |
| `LOG_BACKUP_COUNT` | `3` | Số lượng file log xoay vòng được giữ lại. |
| `LOG_FILE` | `./backend/data/logs/omni-gateway.log` | Đường dẫn file lưu trữ log. Trong Docker, lưu giữ bền vững `/app/backend/data/logs` bằng volume máy chủ. |

### Điều khiển nén ngữ cảnh

Policy AI Quality toàn cục luôn có quyền ưu tiên cao nhất. Mỗi khóa ảo chỉ có thể kế thừa policy đó
hoặc tắt nén qua `PATCH /api/virtual-keys/{key_id}/quality-policy` với revision hiện tại:

```json
{"expected_revision": 3, "compression": "disabled"}
```

Dùng `"inherit"` để bỏ giới hạn riêng của khóa. Một request suy luận đã xác thực cũng có thể gửi
`x-omni-compression: off`; bỏ header hoặc dùng `inherit` để áp dụng kết quả global/key. Khóa và
request không thể bật lại tính năng đã bị tắt toàn cục hoặc làm cơ chế nén mạnh tay hơn. Cơ chế này
chỉ loại bỏ tiền tố lịch sử tại ranh giới an toàn và giữ nguyên payload chưa nén nếu không thể xác
nhận kết quả ước tính token hoặc các bất biến cấu trúc. Số token chỉ là ước tính; tokenizer của
provider mới là căn cứ cuối cùng.

## <a id="khoi-dong-nhanh-tich-hop-sdk"></a>Giao diện SDK

Omni Gateway được thiết kế dựa trên hành vi chuẩn về URL của các SDK Python chính thức. Hãy cấu hình từng client chính xác như hướng dẫn dưới đây; gateway không yêu cầu các tiền tố đường dẫn lặp lại phi tiêu chuẩn.

Các ví dụ dưới đây sử dụng mô hình ảo `omway`. Hãy cấu hình thứ tự ưu tiên dự phòng mô hình-nhà cung cấp cho nó trên trang Models trước, hoặc thay thế bằng một ID mô hình cụ thể.

### OpenAI Python SDK

Sử dụng `/v1` làm base URL cho OpenAI. SDK sẽ tự động nối thêm `/chat/completions`.

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:4283/v1", api_key="sk-ogw-...")

response = client.chat.completions.create(
    model="omway",
    messages=[{"role": "user", "content": "Hãy giải thích kho mã nguồn này trong một đoạn văn."}],
)
```

Client tương tự cũng có thể sử dụng OpenAI Responses API:

```python
response = client.responses.create(
    model="omway",
    instructions="Hãy trả lời ngắn gọn, súc tích.",
    input="Hãy giải thích kho mã nguồn này trong một đoạn văn.",
)

print(response.output_text)
```

Khả năng tương thích Responses hỗ trợ văn bản, hình ảnh đầu vào, non-streaming function tools và SSE text streaming. Các công cụ tích hợp sẵn do OpenAI lưu trữ, lịch sử phản hồi lưu trữ và streaming function calls sẽ bị từ chối rõ ràng vì Omni Gateway không thực thi, lưu trữ hoặc âm thầm loại bỏ những hành vi đặc thù riêng này của OpenAI.

### Anthropic Python SDK

Sử dụng origin của gateway làm base URL cho Anthropic. SDK sẽ tự động nối thêm `/v1/messages`.

```python
from anthropic import Anthropic

client = Anthropic(base_url="http://127.0.0.1:4283", api_key="sk-ogw-...")

response = client.messages.create(
    model="omway",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hãy soạn thảo một commit message ngắn gọn."}],
)
```

### Google GenAI Python SDK

Sử dụng origin của gateway làm base URL cho Google GenAI. SDK sẽ tự động nối thêm route mô hình mặc định, chẳng hạn như `/v1beta/models/{model}:generateContent`.

```python
from google import genai
from google.genai import types

client = genai.Client(
    http_options={
        "base_url": "http://127.0.0.1:4283",
    },
    api_key="sk-ogw-...",
)

response = client.models.generate_content(
    model="omway",
    contents="Hãy viết một hàm Python nhỏ.",
    config=types.GenerateContentConfig(
        system_instruction="Bạn là một trợ lý hữu ích.",
    ),
)
```

### Các Endpoint được hỗ trợ

Omni Gateway cung cấp các route tương thích SDK mà không cần namespace phân biệt sản phẩm:

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

Các lỗi xác thực, kiểm tra request, định tuyến, lỗi từ phía upstream và lỗi trước khi bắt đầu stream đều sử dụng cấu trúc lỗi gốc của giao diện SDK tương ứng. Mọi phản hồi HTTP đều bao gồm header `X-Request-ID`; client có thể gửi mã định danh an toàn trong header này để liên kết theo dõi luồng request xuyên suốt. Các phản hồi bị giới hạn tần suất (rate-limited) hoặc tạm thời không khả dụng sẽ giữ nguyên header `Retry-After` khi phía upstream cung cấp.

## Tính năng mô hình

Trang Models xây dựng mô hình ảo `omway` từ các mô hình được khám phá trên các thông tin xác thực nhà cung cấp đang bật. Hãy sắp xếp các thành viên của nó theo thứ tự ưu tiên một lần, sau đó sử dụng `omway` từ bất kỳ SDK nào được hỗ trợ. Omni Gateway sẽ cân bằng tải giữa các credential khỏe mạnh hỗ trợ mô hình đầu tiên và tiếp tục thử qua thứ tự mô hình đã cấu hình khi mô hình đó không khả dụng. Các ID mô hình cụ thể của nhà cung cấp vẫn khả dụng cho các client cần chọn mô hình tất định. Lưu danh sách trống sẽ tắt `omway` mà không ảnh hưởng đến thông tin xác thực của nhà cung cấp.

Khám phá mô hình có nhận thức về nhà cung cấp: một mô hình dùng chung có thể được hỗ trợ bởi nhiều nhà cung cấp, trong khi các mô hình đặc thù của một nhà cung cấp chỉ sử dụng các credential tương thích. Mỗi thông tin xác thực đã xác minh sẽ lưu trữ danh mục nhà cung cấp riêng của mình và router sẽ ưu tiên sự hỗ trợ được khai báo rõ ràng của credential hơn là suy đoán chung về nhà cung cấp. Làm mới danh mục sẽ kiểm tra lại tính khả dụng hiện tại của nhà cung cấp; các lựa chọn không khả dụng vẫn hiển thị trong cấu hình cho đến khi chúng được khôi phục hoặc xóa đi.

Khi một upstream trả về lỗi `404` cho một mô hình cụ thể, Omni Gateway sẽ ghi nhận một tuyến không khả dụng (unavailable route) cho credential và mô hình đó thay vì vô hiệu hóa toàn bộ nhà cung cấp. Tuyến đó sẽ tạm thời được né tránh ngay lập tức và tiếp tục hiển thị dưới mục **Unavailable Model Routes** cho đến khi nó được xóa hoặc credential được xác minh lại. Điều này ngăn việc gói đăng ký hoặc quyền hạn theo khu vực của một tài khoản ảnh hưởng đến các tài khoản khác ở cùng nhà cung cấp. Nếu không có credential đang bật nào khai báo hoặc suy đoán được khả năng hỗ trợ cho mô hình cụ thể được yêu cầu, gateway sẽ trả về lỗi không có credential tương thích rõ ràng thay vì gửi request đến một provider ngẫu nhiên.

Omni Gateway nhận diện các tiền tố và hậu tố tính năng trong tên mô hình:

- `fake-streaming/{model}` hoặc tiền tố pseudo-streaming đã cấu hình cho các client yêu cầu bắt buộc định dạng SSE.
- `streaming-anti-truncation/{model}` hoặc tiền tố anti-truncation đã cấu hình để tự động phục hồi streaming trong các văn bản dài.
- Các hậu tố suy nghĩ (thinking) như `-high`, `-medium`, `-low`, `-minimal` và `-max` cho các mô hình thuộc họ Gemini có hỗ trợ.
- Các hậu tố tìm kiếm như `-search` cho các mô hình hỗ trợ tiếp đất bằng Google Search (grounding).

Các adapter nhà cung cấp sẽ chuẩn hóa các tên tính năng này trước khi gửi request lên upstream.

## Mức độ sử dụng và Minh bạch chi phí

Omni Gateway ghi lại số lần gọi nhà cung cấp, tỷ lệ thành công, phân bổ theo thông tin xác thực, số token do nhà cung cấp báo cáo, lượng token ước tính tiết kiệm được qua nén ngữ cảnh và chi phí USD ước tính mỗi lượt gọi. Mỗi lần thử lại hoặc chuyển tuyến dự phòng là một lần gọi nhà cung cấp riêng, còn request trace giữ kết quả cuối của yêu cầu logic. Tổng token phân biệt đầu vào thông thường, cache read, cache write, đầu ra và suy luận khi nhà cung cấp có báo cáo; dashboard chỉ rõ các lần gọi thành công bị thiếu usage thay vì coi dữ liệu thiếu là số 0 chính xác. Khi khởi động và mặc định mỗi 24 giờ, gateway đồng bộ [catalog giá mô hình LiteLLM](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json), kiểm tra các mục trực tiếp của OpenAI, Anthropic, Gemini và xAI rồi lưu nguyên tử snapshot hợp lệ gần nhất. Đồng bộ lỗi không làm gián đoạn inference. Có thể ghi đè hoặc bổ sung giá bằng tệp `model_pricing.json` trong thư mục thông tin xác thực; giá thủ công luôn được ưu tiên và tính bằng USD trên một triệu token. Dữ liệu tổng hợp có trên dashboard, theo từng khóa ảo qua API quản trị `/api/virtual-keys` và qua Prometheus `/metrics`. Lượng tiết kiệm từ nén và chi phí vẫn là ước tính vì tokenizer và quy tắc thanh toán của nhà cung cấp mới là căn cứ cuối cùng.

Khóa API ảo (Virtual API Keys) cho phép một gateway phục vụ nhiều client dưới các giới hạn riêng biệt. Mỗi khóa mang ngân sách USD tùy chọn theo ngày và tháng được thực thi từ sổ cái chi phí, cửa sổ trượt giới hạn số yêu cầu mỗi phút (RPM) và số token mỗi phút (TPM), mốc thời gian hết hạn và danh sách mô hình cho phép theo mẫu glob. Các khóa được lưu dưới dạng hàm băm SHA-256; chuỗi bí mật dạng văn bản thuần chỉ hiển thị đúng một lần khi tạo.


## Quy trình làm việc với thông tin xác thực

1. Khởi động Omni Gateway.
2. Mở `http://IP_SERVER_CUA_BAN:4283` trên VPS, hoặc `http://127.0.0.1:4283` khi phát triển cục bộ.
3. Tạo mật khẩu bảng điều khiển trên màn hình thiết lập lần đầu. Đối với thiết lập từ xa, nhập bootstrap token từ log ứng dụng; hoặc cấu hình sẵn `PANEL_PASSWORD`.
4. Thêm tài khoản, API key hoặc kết nối Ollama từ trang Providers.
5. Xác minh thông tin xác thực và theo dõi trạng thái cooldown/lỗi trong bảng điều khiển.
6. Trỏ công cụ lập trình của bạn đến một trong các giao diện API nêu trên.

Khi thêm thông tin xác thực Google Antigravity, Google sẽ chuyển hướng trình duyệt về `http://localhost:4283/callback` sau khi đăng nhập. Trên máy cục bộ, Omni Gateway sẽ hiển thị trang thành công OAuth. Trên VPS, địa chỉ `localhost` đó thuộc về máy của trình duyệt người dùng nên trang có thể không tải được; hãy sao chép toàn bộ URL từ thanh địa chỉ trình duyệt, quay lại trang Providers, dán vào ô `Callback URL` và nhấn `Save credential`.

Google AI Studio sử dụng xác thực bằng API key thay vì OAuth. Thêm một key từ trang Providers; Omni Gateway sẽ kiểm tra tính hợp lệ của nó với danh mục mô hình của Google, lưu trữ dưới dạng credential nhà cung cấp và định tuyến các request Gemini hoặc Gemma tương thích qua đó. Router thông minh có thể chuyển đổi dự phòng giữa AI Studio và Google Antigravity cho các mô hình Gemini dùng chung trong khi vẫn giữ các mô hình đặc thù trên các credential tương thích.

Nhập hàng loạt Google AI Studio chấp nhận các file JSON và file nén ZIP chứa file JSON. Tài liệu JSON có thể chứa một key đơn lẻ, một mảng `api_keys` hoặc một mảng các đối tượng key:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

Mỗi key được nhập đều được xác thực trước khi lưu trữ. Các key trùng lặp trong cùng một lần nhập sẽ bị bỏ qua, các key đã tồn tại được xác thực lại và cập nhật, và các mục không hợp lệ được báo cáo mà không để lộ giá trị key.

Grok Build hỗ trợ thông tin xác thực OAuth PKCE, trong khi SpaceXAI Console hỗ trợ API key. Key SpaceXAI Console được kiểm tra tính hợp lệ với danh mục mô hình Grok Build trước khi lưu trữ. Đối với Grok Build OAuth, Omni Gateway tạo một liên kết ủy quyền; sau khi ủy quyền, hãy sao chép mã hiển thị trên trang ủy quyền Grok Build và dán vào biểu mẫu Grok Build OAuth. Token truy cập được tự động làm mới khi có refresh token, và cả hai loại credential chỉ hiển thị các mô hình Grok Build được khai báo bởi danh mục hiện tại của chúng. Trang Pool có thể truy xuất mức sử dụng tín dụng hàng tháng và mức sử dụng hàng tuần (khi xAI cung cấp) cho các tài khoản Grok Build OAuth. Chế độ xem thanh toán cấp tài khoản này không khả dụng cho các API key SpaceXAI Console.

Codex sử dụng quy trình ủy quyền thiết bị của OpenAI. Tạo một mã thiết bị từ trang Providers, mở URL xác minh được hiển thị, nhập mã, hoàn tất đăng nhập và quay lại để kiểm tra ủy quyền. Omni Gateway lưu trữ danh mục mô hình theo phạm vi tài khoản do Codex trả về, làm mới token truy cập OAuth khi cần và gửi các request tương thích qua giao vận Codex Responses. OpenAI Platform sử dụng xác thực API key; các key được xác thực thông qua danh mục mô hình tài khoản trước khi đưa vào nhóm. Cả hai sản phẩm đều hỗ trợ nhập JSON và ZIP với khả năng xác thực và chống trùng lặp theo từng nhà cung cấp.

Claude Code sử dụng quy trình OAuth PKCE của Anthropic. Tạo liên kết ủy quyền, hoàn tất ủy quyền, sau đó dán mã ủy quyền nhận được vào trang Providers. Claude Platform chấp nhận Anthropic API key. Cả hai sản phẩm đều khám phá các mô hình hiển thị cho từng credential, sử dụng giao vận Anthropic Messages, làm mới token truy cập Claude Code khi có thể và hỗ trợ nhập JSON hoặc ZIP đã qua xác thực.

Các kết nối Ollama được cấu hình theo từng endpoint và có thể bao gồm một bearer API key tùy chọn cho các máy chủ bảo mật hoặc đám mây. Omni Gateway khám phá các mô hình qua `/api/tags` và định tuyến suy luận qua `/api/chat`. Khi Omni Gateway chạy trong Docker, `localhost` trỏ đến chính container đó; hãy sử dụng địa chỉ host-gateway hoặc một endpoint Ollama có thể truy cập qua mạng.

Nhập Pool và nhập hàng loạt Google Antigravity chấp nhận các file lưu trữ lên đến 10 MB, tối đa 500 file, mỗi file credential riêng lẻ tối đa 2 MB và tổng dữ liệu chưa nén tối đa 25 MB. Việc nhập nhà cung cấp Google AI Studio, OpenAI, Anthropic và Ollama sử dụng các giới hạn chặt chẽ hơn: 2 MB cho mỗi file được nhập, 200 mục JSON và 5 MB dữ liệu chưa nén.

Trang Pool cũng cung cấp quy trình sao lưu độc lập với nhà cung cấp. `Download ZIP` xuất toàn bộ nhóm credential đang hoạt động, và `Import ZIP` khôi phục file nén đó bằng cách tự động nhận diện từng credential là Google Antigravity, Google AI Studio, Grok Build, SpaceXAI Console, Codex, OpenAI Platform, Claude Code, Claude Platform hoặc Ollama. Các tài khoản OAuth giữ nguyên cơ chế chống trùng lặp danh tính theo phạm vi nhà cung cấp, trong khi các API key được xác thực và chống trùng lặp bằng mã băm fingerprint không thể đảo ngược trong phạm vi nhà cung cấp. Các mục không được hỗ trợ hoặc bị lỗi định dạng được báo cáo riêng lẻ mà không làm gián đoạn các credential hợp lệ khác trong cùng một file nén.

Thông tin xác thực Google Antigravity sử dụng định dạng `google-antigravity-{account_fingerprint}.json`, trong đó fingerprint được lấy từ email tài khoản đã chuẩn hóa mà không để lộ email đó. Thông tin xác thực Google AI Studio sử dụng `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth sử dụng `grok-{account_fingerprint}.json`, SpaceXAI Console sử dụng `xai-console-{key_fingerprint}.json`, Codex sử dụng `openai-codex-{account_fingerprint}.json`, OpenAI Platform sử dụng `openai-platform-{key_fingerprint}.json`, Claude Code sử dụng `claude-code-{account_fingerprint}.json`, Claude Platform sử dụng `claude-platform-{key_fingerprint}.json` và kết nối Ollama sử dụng `ollama-{connection_fingerprint}.json`. Các credential cũ theo chuẩn `provider_*.json` và `xai-grok-*.json` vẫn tương thích và được xuất ra với tên chuẩn hóa.

Tên chế độ xác thực (Credential mode names):

- `code_assist`: nhóm thông tin xác thực Code Assist tiêu chuẩn.
- `provider`: nhóm thông tin xác thực backend của nhà cung cấp.

## Lưu trữ

Triển khai đơn tiến trình sử dụng bộ lưu trữ SQLite trong thư mục dữ liệu ứng dụng. Docker Compose
lưu toàn bộ `/app/backend/data` trong volume có tên `omni-gateway-data`. Khi dùng trực tiếp
`docker run`, hãy gắn `/app/backend/data/creds` và `/app/backend/data/logs` vào các đường dẫn bền
vững trên máy chủ như `/opt/omni-gateway/creds` và `/opt/omni-gateway/logs`.

SQLite là nguồn lưu trữ Core và là lựa chọn production được khuyến nghị. PostgreSQL là tùy chọn
Advanced dành cho người vận hành tự quản lý vòng đời cơ sở dữ liệu. MongoDB chỉ được giữ ở tier
Compatibility cho các bản triển khai hiện có; R1 không tiếp tục mở rộng tính năng ngang hàng:

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=omni_gateway
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/omni_gateway
```

Bộ lưu trữ bên ngoài không làm cho runtime có thể mở rộng theo chiều ngang. Môi trường
production phải chạy một worker và một replica. Chỉ cấu hình một trong hai: MongoDB hoặc PostgreSQL;
lỗi khởi tạo cơ sở dữ liệu bên ngoài sẽ dừng quá trình khởi động thay vì âm thầm quay về SQLite.
Quy trình backup/restore mã hóa di động chỉ hỗ trợ SQLite và R1 không cung cấp lệnh chuyển đổi trực
tiếp giữa các backend đang chạy. Hãy đọc [hỗ trợ lưu trữ và khôi phục](../storage.md) trước khi chọn
cơ sở dữ liệu bên ngoài.

Khả năng nhập thông tin xác thực từ môi trường có sẵn từ bảng điều khiển. Đặt một trong các biến sau thành chuỗi JSON thô hoặc sử dụng biến thể `_B64` tương ứng cho chuỗi JSON mã hóa base64:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

Payload có thể là một đối tượng credential đơn lẻ, một mảng hoặc `{ "credentials": [...] }`.

## Phát triển

Phần này dành cho người đóng góp và gỡ lỗi cục bộ. Triển khai sản xuất nên sử dụng Docker với các volume host bền vững.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
ruff check backend
ruff format --check backend
python -m compileall -q backend
python -m backend.tests
for script in frontend/js/*.js; do node --check "$script"; done
yamllint --strict .github deploy .yamllint.yml
python -m pip_audit --local --progress-spinner off
```

Khởi chạy dịch vụ sau khi toàn bộ kiểm tra vượt qua:

```bash
python backend/main.py
```

Nền tảng tiêu chuẩn cho môi trường sản xuất là Python 3.12, và CI hiện đang kiểm tra xác thực Python 3.12 và 3.14. Xem [Đóng góp](../../CONTRIBUTING.md) để biết quy trình tạo pull request và các kỳ vọng đánh giá mã.

## Ghi chú triển khai

- Tuyệt đối không commit các file JSON chứa credential hoặc file `.env`.
- Sử dụng `API_KEY` riêng cho các tích hợp client và một `PANEL_PASSWORD` riêng biệt cho việc truy cập bảng điều khiển.
- Giới hạn quyền truy cập vào volume credential bền vững hoặc cơ sở dữ liệu bên ngoài và bật mã hóa ở cấp nền tảng khi lưu trữ (encryption at rest); router phải có khả năng đọc lại token của nhà cung cấp.
- Đặt Omni Gateway phía sau một reverse proxy có bật TLS khi cho phép truy cập ngoài localhost.
- Cấu hình reverse proxy để bảo toàn `Host` và truyền `X-Forwarded-Proto`; đặt `PANEL_COOKIE_SECURE=true` khi đã đảm bảo đầu cuối HTTPS.
- Chỉ đặt `TRUST_PROXY_HEADERS=true` khi dịch vụ chỉ có thể truy cập duy nhất qua một proxy đáng tin cậy có ghi đè `X-Forwarded-For` và `X-Forwarded-Proto`.
- Sử dụng `GET /health` cho kiểm tra tiến trình còn sống (liveness) và `GET /ready` cho kiểm tra sẵn sàng kèm lưu trữ (readiness).
- Telemetry bên ngoài mặc định bị tắt. Chỉ bật `PROMETHEUS_EXPORT_ENABLED` cùng
  `METRICS_TOKEN` đủ mạnh hoặc cấu hình bộ xuất OpenTelemetry chỉ chứa số liệu tổng hợp theo
  [tài liệu quan sát vận hành](../observability.md). Nội dung prompt và phản hồi không bao giờ được xuất.
- Docker image chỉ chạy với quyền root trong khoảng thời gian đủ ngắn để sửa chữa quyền sở hữu thư mục dữ liệu được gắn kết, sau đó chạy dịch vụ dưới người dùng không có đặc quyền `gateway`.
- Đặt `CORS_ORIGINS` thành các origin đáng tin cậy rõ ràng khi các client trên trình duyệt cần quyền truy cập cross-origin.
- Luôn sao lưu volume Compose `omni-gateway-data`, hoặc `/opt/omni-gateway` khi chạy Docker trực
  tiếp, trước khi nâng cấp hoặc chuyển máy chủ.
- Quy trình xuất bản Docker image sử dụng secret kho lưu trữ `DOCKERHUB_USERNAME` và `DOCKERHUB_TOKEN` cho Docker Hub, và `GITHUB_TOKEN` tích hợp sẵn cho GitHub Packages tại `ghcr.io/nguywnben/omni-gateway`. Chỉ đặt biến kho lưu trữ `IMAGE_NAME` tùy chọn khi xuất bản sang một tên image Docker Hub tùy chỉnh.
- Duy trì `WORKERS=1` và một replica ứng dụng duy nhất cho toàn bộ chuỗi phiên bản 1.x; bộ lưu trữ bên ngoài không thể thay thế cho việc điều phối phân tán.
- Sử dụng các route quản lý chuẩn tắc `/api/credentials`. Các route bí danh `/api/creds` trong giai đoạn beta đã bị loại bỏ từ bản 1.0.0.
- Làm theo hướng dẫn [Nâng cấp lên 1.0](../upgrading-to-1.0.md) trước khi di chuyển một bản triển khai beta.
- Làm theo [hướng dẫn cập nhật](../updating.md) khi nâng cấp một instance đang triển khai hoặc khôi phục về phiên bản trước.
- Làm theo [danh sách kiểm tra phát hành](../release-checklist.md) được duy trì trước khi gắn tag hoặc phát hành một image.
- Đảm bảo chính sách lưu giữ log và xoay vòng thông tin xác thực phù hợp với hạn mức sử dụng của bạn.
- Thu hồi và đổi thông tin xác thực ngay lập tức nếu bộ quét kho lưu trữ hoặc nền tảng báo cáo bí mật bị rò rỉ.
- Render Blueprint sử dụng dịch vụ trả phí có đĩa lưu trữ bền vững. Các dịch vụ miễn phí của Render sử dụng hệ thống file tạm thời và chỉ phù hợp cho việc đánh giá thử nghiệm dùng rồi bỏ.

## Cộng đồng và Tình trạng dự án

- Đọc [Đóng góp](../../CONTRIBUTING.md) trước khi mở một pull request.
- Báo cáo lỗ hổng bảo mật thông qua quy trình riêng tư tại [Chính sách bảo mật](../../SECURITY.md).
- Xem lại [Nhật ký thay đổi](../../CHANGELOG.md) để biết các thay đổi theo từng bản phát hành.
- Tuân thủ [Quy tắc ứng xử](../../CODE_OF_CONDUCT.md) trong tất cả các không gian thuộc dự án.

## Lời cảm ơn & Nguồn cảm hứng

Omni Gateway được kế thừa và phát triển từ cộng đồng mã nguồn mở về định tuyến AI, telemetry và gateway. Chúng tôi bày tỏ lòng biết ơn sâu sắc đến những người sáng lập và duy trì các dự án sau:

| Dự án | Mô tả | Lượt Star |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Nguồn cảm hứng về quản lý khóa đa nhà cung cấp và tổng hợp API trên nền web | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Tiên phong trong lớp proxy đa định dạng và chuyển đổi giao thức cho các AI coding CLI | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Chuẩn mực trong proxy LLM hợp nhất, cân bằng tải và định tuyến dự phòng | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Kiến trúc AI gateway siêu nhanh, chiến lược định tuyến và mô hình dự phòng linh hoạt | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Nền tảng LLM engineering mã nguồn mở, theo dõi trace, khả năng quan sát và thu thập số liệu | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

## Giấy phép

Omni Gateway được phát hành theo [Giấy phép MIT](../../LICENSE).
