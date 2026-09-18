<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>AI 코딩 도구를 위한 범용 AI 라우터 및 통합 멀티 프로바이더 게이트웨이</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">지원하는 제공자</a> • <a href="#core-capabilities">핵심 기능</a> • <a href="#deployment">배포</a> • <a href="#sdk-surfaces">빠른 시작 SDK 연동</a> • <a href="#architecture">아키텍처</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <b>한국어</b> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

이 README는 같은 기능 범위로 15개 언어를 제공합니다. 연결된 기술 문서는 원문의 언어를 유지합니다.

코딩 도구를 위한 범용 AI 라우터입니다. Polaris는 스마트 자동 장애 조치(auto-fallback), 토큰 인식 컨텍스트 정리, 사용량 가시성 및 원활한 포맷 변환을 제공하여 로컬 에이전트, IDE 어시스턴트 및 자동화 스크립트가 단일 안정적인 API 인터페이스를 통해 무료 및 유료 LLM 용량을 활용할 수 있도록 합니다.

> Polaris는 개인 또는 신뢰할 수 있는 팀의 자체 호스팅을 대상으로 하며 worker와 복제본은 각각 하나만 지원합니다. Docker Compose, 로컬 소유자 로그인, SQLite, 라우팅 및 문서화된 SDK 인터페이스가 핵심입니다. PostgreSQL, OIDC, 역방향 프록시, 외부 원격 측정은 선택 사항이며 MongoDB는 호환용입니다. 다중 복제본 조정 및 Kubernetes는 지원 범위 밖입니다. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Polaris를 선택하는 이유

현대 코딩 워크플로는 OpenAI 호환 도구, Gemini 네이티브 SDK, Anthropic 스타일 에이전트, Google 지원 자격 증명 및 실험적 모델 라우트 등 여러 클라이언트와 제공자를 혼합하여 사용하는 경우가 많습니다. Polaris는 이러한 클라이언트와 모델 백엔드 사이에 위치하여 각 도구가 기본 이해 형식을 그대로 유지하면서 게이트웨이가 라우팅, 재시도, 요청 정리 및 응답 정규화를 처리하도록 합니다.

<a id="core-capabilities"></a>

## 핵심 기능

- 요청별 예약, 공정한 순환, 대기 시간 및 소진된 할당량을 고려한 자동 장애 조치.
- 시스템 지시, 도구 및 최근 대화를 보존하는 긴 기록 정리.
- OpenAI Chat Completions/Responses, Gemini, Anthropic Messages 변환 및 스트리밍.
- 공급자별 검증과 중복 제거를 지원하는 OAuth 계정 및 API 키 관리.
- 계정 권한을 반영한 자격 증명별 모델 카탈로그.
- 사용 불가 모델 경로 기록 및 Models 페이지에서 복구.
- SSE, 유사 스트리밍, 잘린 응답의 제한된 재시도.
- 균형, 우선순위, 가중치, 최소 지연, 최소 비용 라우팅.
- 일/월 예산, RPM/TPM, 만료 및 허용 모델을 갖춘 가상 키.
- 호출별 USD 추정 비용과 대시보드·Prometheus 집계.
- 선택적 프롬프트 주입 감지, 금지 단어 및 개인정보 마스킹.
- 결정적 응답에 대한 선택적 정확 일치 캐시.
- Prometheus, 선택적 Langfuse 내보내기 및 사용량 추적.
- 자격 증명, 로그, 설정, 사용량, 버전 관리 콘솔.

<a id="console-preview"></a>

## 콘솔 미리보기

스크린샷은 격리된 오프라인 데모의 가상 데이터를 사용합니다.

### 대시보드

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — 대시보드" />
</picture>

### 자격 증명

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — 콘솔 미리보기" />
</picture>

<a id="supported-providers"></a>

## 지원하는 제공자

카탈로그에는 공급자 23개가 있습니다. 사용 가능한 모델과 기능은 각 자격 증명의 권한에 따라 달라집니다.

| 공급자 | 연결 방식 | 서비스 / 범위 |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API 키 | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API 키 | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth(기기 코드) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API 키 | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | API 키 | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | 엔드포인트, API 키 선택 사항 | 로컬 / 자체 호스팅 |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | API 키 | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | API 토큰 + 계정 ID | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | API 키 | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | API 키 | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | API 키, 조직 ID 선택 사항 | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | API / 서비스 키 | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | API 키 | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | 브라우저 OAuth / AWS 기기 로그인 / API 키 | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth(Meta 기기 코드) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | API 키 | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | API 키 | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | API 키 | NVIDIA 호스팅 추론 |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | API 키 + Zen/Go 요금제 | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | API 키 | Poolside API |

클라이언트는 공통 [SDK 인터페이스](#sdk-surfaces)를 사용합니다. 변환, 스트리밍, 장애 조치는 모델 기능에 따라 달라지며 지원하지 않는 옵션은 명시적으로 거부됩니다. **Providers**에서 공급자 또는 자격 증명별로 설정합니다. Muse Code와 Meta Model API의 자격 증명 및 모델 이름 공간은 별개입니다.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## 아키텍처

```text
클라이언트 도구
  OpenAI SDK | Google GenAI SDK | Anthropic SDK | IDE 통합 플러그인
        |
        v
Polaris
  인증 -> 포맷 변환 -> 토큰 인식 정리 -> 라우팅 -> 장애 조치 -> 스트리밍
        |
        v
제공자 어댑터
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

Polaris 백엔드 어댑터가 지속적으로 발전하는 동안에도 외부에 노출되는 공개 API 계약은 변함없이 안정적으로 유지됩니다.

<a id="repository-structure"></a>

## 저장소 구조

```text
backend/       FastAPI 컴포지션 루트, 라우팅 코어, 프로토콜 변환기, 스토리지 및 테스트
frontend/      관리 콘솔 UI 구조, 스타일, 스크립트 및 제공자 아이콘 에셋
deploy/        컨테이너 정의, 플랫폼 배포 매니페스트 및 OS 시작 스크립트
docs/          아키텍처 설계 문서 및 프로젝트 유지 관리 가이드
.github/       CI 워크플로, 의존성 자동화 및 기여 템플릿
```

모듈 경계, 요청 처리 흐름, 상태 소유권 및 현재 릴리스 제약 조건에 대한 자세한 내용은 [아키텍처](../architecture.md) 문서를 참조하세요.

<a id="deployment"></a>

## 배포

단일 머신·단일 worker의 Docker Compose가 기본 배포 경로입니다. [설치](../installation.md) 및 [지원 표](../installation.md#support-matrix)를 따르세요.

기본 구성은 외부 서비스가 필요 없으며 `polaris-data`에 데이터를 보관합니다. 템플릿은 `1.0.0`을 대상으로 합니다. 공개된 동일 버전의 Polaris 태그와 이미지로만 설치하세요. 미공개 소스를 사용하는 경우 [출시 체크리스트](../releases/1.0.0-preparation.md)에 따라 별도의 로컬 이미지를 빌드하세요. [업데이트·롤백](../updating.md) 절차를 따르고 고급 옵션은 `deploy/compose.advanced.yml`로 활성화합니다.

[식별자 규약](../migrations/polaris.md)과 [문제 해결](../troubleshooting.md)을 참고하세요. 네이티브 스크립트, `docker run`, Render, Zeabur는 호환 경로로, 동일한 설치·복구 검증 범위가 아닙니다. 이미지는 `linux/amd64`로 게시하며 `linux/arm64` 게시는 중단 상태입니다.

### 로컬 개발 또는 진단:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

콘솔을 여세요. 초기 설정은 Docker와 같습니다:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## 설정

우선순위는 환경 변수, 저장된 설정, 기본값 순입니다. [생성된 설정 참조](../reference/configuration.md)는 형식, 그룹, 담당 모듈, 즉시 적용/재시작/환경 전용 수명 주기를 설명합니다. 잘못된 값은 시작을 차단하며 변수 이름을 표시하고, `POLARIS_*` 오타는 경고합니다.

| 환경 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | 바인드 주소. |
| `PORT` | `4283` | HTTP 포트. |
| `HOST_PORT` | `4283` | Docker Compose에서만 사용하는 호스트 포트. |
| `WORKERS` | `1` | worker 하나만 지원합니다. |
| `POLARIS_RUNTIME_MODE` | `standalone` | `standalone`만 지원합니다. |
| `POLARIS_REPLICA_COUNT` | `1` | 복제본 하나만 지원합니다. |
| `CORS_ORIGINS` | 비어 있음 | 크로스 오리진 API 호출을 허용할 브라우저 오리진 목록(쉼표 구분). 동일 오리진 콘솔 접속 시 비워 둡니다. |
| `CORS_ORIGIN_REGEX` | 비어 있음 | 동적 브라우저 오리진을 일치시키기 위한 선택적 정규식. |
| `API_KEY` | 자동 생성 | `sk-polaris-` 접두사의 클라이언트 API 키. |
| `PANEL_PASSWORD` | 설정 전까지 비어 있음 | 웹 제어판 접속 비밀번호. |
| `SETUP_TOKEN` | 비어 있음 | 원격 초기 설정용 24자 이상의 고유 토큰. 자동 생성·로깅하지 않음. 직접 localhost 접속에는 불필요. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | 웹 제어판 세션 유효 기간(초). |
| `PANEL_COOKIE_SECURE` | 자동 | `true`로 설정 시 쿠키를 HTTPS로만 전송하도록 강제합니다. 비워 두면 `X-Forwarded-Proto`를 통해 자동 감지합니다. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | 로그인 속도 제한 윈도우(초). |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | 윈도우 내 단일 클라이언트에 허용되는 최대 로그인 실패 횟수. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | 메모리 내 로그인 제한기가 추적하는 최대 클라이언트 주소 수. |
| `MAX_REQUEST_BODY_MB` | `64` | 최대 HTTP 요청 본문 크기(MiB). 초과하는 SDK 요청은 해당 프로토콜의 표준 에러 구조를 반환합니다. |
| `TRUST_PROXY_HEADERS` | `false` | 전달 헤더를 덮어쓰는 신뢰할 수 있는 역방향 프록시 뒤에 있을 때만 활성화합니다. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | 자격 증명 저장 디렉터리. Docker에서는 `/app/backend/data/creds`를 호스트 볼륨에 마운트합니다. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Code Assist 백엔드 엔드포인트. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Google Antigravity 백엔드 엔드포인트. |
| `PROXY` | 비어 있음 | 선택적 HTTP, HTTPS 또는 SOCKS 프록시. |
| `RETRY_429_ENABLED` | `true` | 요청 제한 및 일시적 업스트림 오류에 대한 유계 재시도 활성화. 기존 설정 호환성을 위해 이전 이름을 유지합니다. |
| `RETRY_429_MAX_RETRIES` | `5` | 일시적 업스트림 오류에 대한 최대 재시도 횟수. |
| `RETRY_429_INTERVAL` | `1` | 일시적 재시도의 기본 백오프 간격(초). |
| `AUTO_DISABLE` | `false` | 구성된 치명적 오류 발생 시 해당 자격 증명을 자동으로 비활성화. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | 치명적 오류로 간주할 상태 코드 목록(쉼표 구분). |
| `ROUTING_STRATEGY` | `balanced` | 전략: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | 비어 있음 | `priority` 정책에서 우선 선택할 제공자(예: `google_antigravity`, `google_ai_studio`). |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | 제공자 추론 타임아웃(5~900초). |
| `RESPONSE_CACHE_ENABLED` | `false` | 온도 0, 비스트리밍 결정적 응답의 메모리 캐시. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | 캐시 유효 기간(초). |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | 최대 캐시 응답 수. |
| `GUARDRAILS_ENABLED` | `false` | 호출 전 보호 활성화. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | 전송 텍스트의 이메일, 카드, API 키 마스킹. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | 프롬프트 주입을 HTTP 400으로 거부. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | 비어 있음 | 쉼표로 구분하는 금지어, 대소문자 구분 없음. |
| `PRICING_SYNC_ENABLED` | `true` | LiteLLM 가격을 백그라운드 갱신하고 오프라인 시 마지막 정상 사본 유지. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | 가격 갱신 간격: 1–168시간. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | 스트리밍 끊김 방지 기능의 최대 연속 재시도 횟수. |
| `TOKEN_COMPRESSION_ENABLED` | `true` | 제공자로 라우팅하기 전에 과도한 대화 기록을 압축. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | 컨텍스트 압축을 트리거할 예상 입력 토큰 임계값. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | 압축 후 목표 예상 입력 토큰 수. 트리거 임계값보다 낮아야 합니다. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | 압축 시 반드시 보존할 최소 최근 사용자 턴 수. |
| `COMPATIBILITY_MODE` | `false` | 시스템 메시지를 지원하지 않는 클라이언트/모델을 위해 자동 변환. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | 사용 가능한 경우 모델의 추론 과정(reasoning)을 반환. |
| `MONGODB_URI` | 비어 있음 | MongoDB 호환 저장소. |
| `POSTGRESQL_URI` | 비어 있음 | 선택적 PostgreSQL 저장소. |
| `CODE_ASSIST_CLIENT_ID` | 포함된 데스크톱 클라이언트 | Code Assist OAuth Client ID에 대한 선택적 재정의. |
| `CODE_ASSIST_CLIENT_SECRET` | 포함된 데스크톱 클라이언트 | Code Assist OAuth Client Secret에 대한 선택적 재정의. |
| `ANTIGRAVITY_CLIENT_ID` | 포함된 데스크톱 클라이언트 | Google Antigravity OAuth Client ID에 대한 선택적 재정의(제공자 페이지에서도 구성 가능). |
| `ANTIGRAVITY_CLIENT_SECRET` | 포함된 데스크톱 클라이언트 | Google Antigravity OAuth Client Secret에 대한 선택적 재정의. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Google AI Studio Generative Language API 엔드포인트에 대한 선택적 재정의. |
| `XAI_API_URL` | `https://api.x.ai/v1` | SpaceXAI Console API 키 인증용 엔드포인트에 대한 선택적 재정의(제공자 페이지에서도 구성 가능). |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Grok Build OAuth 구독 엔드포인트에 대한 선택적 재정의. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Grok Build OAuth Issuer에 대한 선택적 재정의. 콘솔은 `x.ai` 도메인의 HTTPS 호스트만 허용합니다. |
| `XAI_CLIENT_ID` | 포함된 공개 클라이언트 | Grok Build PKCE OAuth Client ID에 대한 선택적 재정의. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Grok Build OAuth 및 SpaceXAI Console API 요청에 공통 적용할 선택적 HTTP User-Agent 재정의. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | OpenAI Platform API 엔드포인트에 대한 선택적 재정의(제공자 페이지에서도 구성 가능). |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Codex 추론 및 계정 모델 목록 엔드포인트에 대한 선택적 재정의. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Codex 계정 요청 제한 확인 엔드포인트에 대한 선택적 재정의. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Codex 디바이스 인증 서비스에 대한 선택적 재정의. |
| `CODEX_CLIENT_ID` | 포함된 공개 클라이언트 | Codex 디바이스 OAuth Client ID에 대한 선택적 재정의. |
| `CODEX_USER_AGENT` | Codex CLI 호환 값 | Codex 요청을 위한 선택적 User-Agent 재정의. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Claude Code 전용 Messages 엔드포인트. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Claude Code PKCE 인증 엔드포인트에 대한 선택적 재정의. Anthropic / Claude 공식 호스트만 허용. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Claude Code 토큰 엔드포인트에 대한 선택적 재정의. Anthropic / Claude 공식 호스트만 허용. |
| `CLAUDE_CLIENT_ID` | 포함된 공개 클라이언트 | Claude Code PKCE OAuth Client ID에 대한 선택적 재정의. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | Claude Code 전용 User-Agent. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Providers의 별도 Claude Platform 엔드포인트. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | 독립된 Claude Platform User-Agent. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Google Antigravity 프로토콜 레벨 요청을 위한 선택적 User-Agent 재정의. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Google Antigravity 페이로드 레벨 userAgent 필드에 대한 선택적 재정의. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | 인증된 `GET /metrics` 활성화. |
| `METRICS_TOKEN` | 비어 있음 | Prometheus용 UTF-8 최소 32바이트 Bearer 토큰. |
| `OTEL_EXPORT_ENABLED` | `false` | 본문 없는 OTLP/HTTP 집계 내보내기 활성화. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 비어 있음 | HTTPS 수집기. URL 내 자격 증명 금지. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | 내보내기 간격: 15–300초. |
| `LANGFUSE_PUBLIC_KEY` | 비어 있음 | 비밀 키와 함께 Langfuse 활성화. |
| `LANGFUSE_SECRET_KEY` | 비어 있음 | 추적용 Langfuse 비밀 키. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse 수집 엔드포인트. |
| `LOG_LEVEL` | `info` | 런타임 로그 레벨. |
| `LOG_MAX_MB` | `10` | 로그 파일이 로테이션되기 전 최대 크기(MB). |
| `LOG_BACKUP_COUNT` | `3` | 보관할 로테이션 로그 파일 개수. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | 파일 로그 출력 경로. Docker에서는 `/app/backend/data/logs`를 호스트 볼륨에 마운트합니다. |

### 압축 제어

전역 AI Quality 정책이 최종 기준입니다. 가상 키는 상속하거나 압축을 끌 수만 있습니다. 현재 리비전을 포함해 `PATCH /api/virtual-keys/{key_id}/quality-policy`를 사용하고 `inherit`로 키 제한을 해제합니다. 인증된 요청은 `x-polaris-compression: off`를 보낼 수 있으며 생략 또는 `inherit`는 전역/키 정책을 따릅니다. 전역에서 금지한 압축을 다시 켜거나 강화할 수 없습니다. 안전한 기록의 앞부분만 제거하고, 구조나 추정이 불확실하면 원본을 전송합니다. 토큰 수는 추정값입니다.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## 빠른 시작 SDK 연동

Polaris는 공식 Python SDK의 표준 URL 동작에 맞춰 설계되었습니다. 게이트웨이에는 비표준 중복 경로 접두사가 필요하지 않으므로 아래와 같이 클라이언트를 구성하세요.

아래 예제에서는 가상 모델 `polaris`를 사용합니다. 모델 페이지에서 대체 우선순위를 미리 구성하거나 특정 제공자 모델 ID로 교체하세요.

### OpenAI Python SDK

OpenAI의 Base URL로 `/v1`을 설정합니다. SDK가 자동으로 끝에 `/chat/completions`를 추가합니다.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "이 코드 저장소를 한 단락으로 설명해 주세요."}]
)
```

동일한 클라이언트로 OpenAI Responses API를 직접 호출할 수도 있습니다:

```python
response = client.responses.create(
    model="polaris",
    instructions="간결하게 답변해 주세요.",
    input="이 코드 저장소를 한 단락으로 설명해 주세요."
)

print(response.output_text)
```

Responses 호환성 계층은 텍스트 입력, 이미지 입력, 비스트리밍 Function Tool 및 SSE 텍스트 스트리밍을 지원합니다. OpenAI 호스팅 내장 도구, 영구 보관 응답 이력 및 스트리밍 함수 호출의 경우 Polaris가 이러한 OpenAI 고유 동작을 실행, 영구 보관 또는 묵시적으로 삭제하지 않으므로 명확하게 에러를 반환하여 거부합니다.

### Anthropic Python SDK

Anthropic의 Base URL로 게이트웨이 오리진을 직접 지정합니다. SDK가 자동으로 끝에 `/v1/messages`를 추가합니다.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "간결한 커밋 메시지를 작성해 주세요."}]
)
```

### Google GenAI Python SDK

Google GenAI의 Base URL로 게이트웨이 오리진을 직접 지정합니다. SDK가 `/v1beta/models/{model}:generateContent`와 같은 기본 모델 라우트를 자동으로 추가합니다.

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
    contents="간단한 Python 함수를 작성해 주세요.",
    config=types.GenerateContentConfig(
        system_instruction="당신은 유능한 코딩 어시스턴트입니다."
    )
)
```

### 지원 엔드포인트 목록

Polaris는 별도의 제품 네임스페이스 접두사 없이 표준 SDK 호환 라우트를 제공합니다:

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

인증 오류, 요청 검증 오류, 라우팅 오류, 업스트림 오류 및 스트리밍 시작 전 실패는 모두 해당 SDK 인터페이스의 기본 에러 구조로 래핑됩니다. 모든 HTTP 응답에는 `X-Request-ID` 헤더가 포함되며, 클라이언트는 이 헤더에 식별자를 전달하여 요청 흐름을 추적할 수 있습니다. 업스트림에서 속도 제한 또는 일시적 사용 불가를 반환할 경우 게이트웨이는 `Retry-After` 헤더를 그대로 투명하게 보존합니다.

<a id="model-features"></a>

## 모델 기능 및 고급 제어

콘솔의 '모델' 페이지에서는 활성화된 제공자 자격 증명에서 발견된 모델을 집계하여 가상 모델 `polaris`를 구성합니다. 각 기본 모델의 우선순위를 한 번만 설정하면 지원되는 모든 SDK에서 `polaris`를 사용할 수 있습니다. Polaris는 1순위 모델을 지원하는 정상 자격 증명 간에 부하를 분산하며, 해당 모델을 사용할 수 없게 되면 설정된 순서에 따라 자동으로 대체 시도합니다. 특정 모델을 결정론적으로 지정해야 하는 클라이언트를 위해 제공자 고유의 물리적 모델 ID도 계속 사용할 수 있습니다. 빈 목록을 저장하면 제공자 자격 증명에 영향을 주지 않고 `polaris`를 비활성화할 수 있습니다.

모델 발견 메커니즘은 제공자 인식형입니다. 범용 모델은 여러 제공자가 함께 지원할 수 있지만, 전용 모델은 호환 가능한 자격 증명으로만 처리됩니다. 검증된 각 자격 증명은 독립된 자체 제공자 카탈로그를 유지하며, 라우터는 일반적인 제공자 추론보다 자격 증명이 명시적으로 선언한 지원을 우선시합니다. 카탈로그를 새로 고치면 현재 제공자의 실시간 가용성을 다시 확인하며, 사용할 수 없게 된 항목도 복구되거나 수동으로 제거될 때까지 구성 내에 계속 표시됩니다.

특정 물리적 모델에 대해 업스트림이 `404`를 반환하는 경우, Polaris는 제공자 전체를 비활성화하는 대신 해당 자격 증명 및 모델 범위에 사용할 수 없는 라우트를 기록합니다. 해당 라우트는 즉시 일시적으로 우회되며, 지워지거나 자격 증명이 다시 검증될 때까지 **사용할 수 없는 모델 라우트** 목록에 계속 표시됩니다. 이를 통해 단일 계정의 구독 권한이나 지역 제한이 동일한 제공자 아래의 다른 정상 계정에 영향을 미치지 않도록 방지합니다. 활성화된 자격 증명 중 어느 것도 요청된 모델을 선언하거나 추론하지 못하는 경우, 게이트웨이는 일치하지 않는 제공자에게 무작위로 전달하지 않고 명확한 호환 자격 증명 없음 오류를 반환합니다.

Polaris는 모델 이름에 포함된 기능 접두사 및 접미사를 해석합니다:

- `fake-streaming/{model}` 또는 구성된 의사 스트리밍 접두사(SSE 형식을 필수로 요구하는 클라이언트용).
- `streaming-anti-truncation/{model}` 또는 구성된 끊김 방지 접두사(긴 텍스트 스트리밍 생성 시 자동 이어쓰기 복구용).
- 사고 깊이 접미사(`-high`, `-medium`, `-low`, `-minimal`, `-max` 등 지원되는 Gemini 계열 모델용).
- 검색 접지 접미사(`-search` 등 Google Search 접지 지원 모델용).

제공자 어댑터는 업스트림으로 요청을 보내기 전에 이러한 기능 식별자를 자동으로 정규화합니다.

<a id="usage-and-cost-visibility"></a>

## 사용량 및 비용 투명성

공급자 시도, 재시도 및 장애 조치마다 별도로 집계하며 추적은 논리 요청의 최종 결과를 보존합니다. 결과, 자격 증명, 공급자가 보고한 입력/출력/캐시/추론 토큰, 추정 절감량과 USD 비용을 기록합니다. 누락된 사용량은 측정된 0이 아닙니다. 기간은 브라우저 시간대의 고정 경계이며 일별 보기는 00:00–23:00입니다. LiteLLM 공개 가격은 기본적으로 시작 시 및 24시간마다 갱신하고 마지막 정상 사본을 원자적으로 보존합니다. 실패해도 추론은 계속됩니다. 자격 증명 디렉터리의 `model_pricing.json`이 우선하며 가격은 백만 토큰 단위입니다. 대시보드, `/api/virtual-keys`, `/metrics`에서 집계를 제공합니다. 공급자 청구와 tokenizer가 기준입니다.

가상 키는 일/월 예산, RPM/TPM 슬라이딩 윈도, 만료 및 glob 모델 규칙을 지원합니다. SHA-256 해시만 저장하고 비밀 값은 생성 시 한 번만 표시합니다.

<a id="credential-workflow"></a>

## 자격 증명 설정 워크플로

1. Polaris를 시작합니다.
2. VPS에서는 `http://서버_IP:4283`에 접속하거나 로컬 개발 시 `http://127.0.0.1:4283`에 접속합니다.
3. 검사를 완료하고 소유자 비밀번호를 만드세요. 원격 초기 설정 전에 24자 이상의 고유한 `SETUP_TOKEN` 또는 `PANEL_PASSWORD`를 설정하세요. 토큰은 자동 생성하거나 로그에 기록하지 않습니다.
4. '제공자' 페이지에서 계정, API 키 또는 Ollama 연결을 추가합니다.
5. 자격 증명 유효성을 검증하고 패널에서 쿨다운 및 오류 상태를 모니터링합니다. **Credentials** (`/credentials`).
6. 코딩 도구를 위의 지원되는 API 인터페이스 중 하나에 연결합니다.

Google Antigravity 자격 증명을 추가할 때 Google은 로그인 완료 후 브라우저를 `http://localhost:4283/callback`으로 리디렉션합니다. 로컬 머신에서는 Polaris가 OAuth 성공 화면을 직접 표시합니다. VPS의 경우 해당 `localhost`가 사용자의 로컬 브라우저 머신을 가리키므로 페이지가 열리지 않을 수 있습니다. 브라우저 주소 표시줄에서 전체 URL을 복사하여 제공자 페이지로 돌아와 `Callback URL` 상자에 붙여넣고 `자격 증명 저장`을 클릭하세요.

Google AI Studio는 OAuth 대신 API 키 인증을 사용합니다. 제공자 페이지에서 키를 추가하면 Polaris가 Google 모델 카탈로그와 대조하여 유효성을 검증하고 제공자 자격 증명으로 저장한 후 호환되는 Gemini 또는 Gemma 요청을 라우팅합니다. 스마트 라우터는 공유 Gemini 모델에 대해 AI Studio와 Google Antigravity 간에 자동 장애 조치를 수행하며 전용 모델은 호환 자격 증명에서만 처리되도록 보장합니다.

Google AI Studio 일괄 가져오기는 JSON 파일 및 JSON 파일이 포함된 ZIP 압축 파일을 지원합니다. JSON 문서는 단일 키, `api_keys` 배열 또는 키 객체 배열을 포함할 수 있습니다:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

파일 가져오기는 오프라인으로 처리됩니다. Polaris는 JSON/ZIP 구조를 확인하고 새 키를 `unverified` 상태로 저장하며, Google에 연결하지 않고 중복 키와 기존 키를 건너뜁니다. 가져온 모델 목록은 검증된 것으로 간주하지 않습니다. 형식 오류는 키를 노출하지 않고 보고합니다. 이후 자격 증명 검증/모델 검색을 명시적으로 실행하세요. **Test model**은 추론 권한을 별도로 확인하며 할당량을 소모하거나 비용이 발생할 수 있습니다.

Grok Build는 PKCE OAuth 자격 증명을 지원하고 SpaceXAI Console은 API 키를 지원합니다. SpaceXAI Console 키는 저장 전에 SpaceXAI Console API 모델 카탈로그와 대조하여 유효성을 검증합니다. Grok Build OAuth의 경우 Polaris가 인증 링크를 생성합니다. 인증 완료 후 인증 페이지에 표시된 코드를 복사하여 양식에 붙여넣으세요. 리프레시 토큰이 있는 경우 액세스 토큰이 자동으로 갱신되며, 두 자격 증명 유형 모두 각 카탈로그에서 선언된 모델만 노출합니다. Credentials 페이지에서는 Grok Build OAuth 계정의 월간 크레딧 사용량과 xAI에서 제공하는 경우 주간 사용량을 확인할 수 있습니다. 이 계정 수준 청구 뷰는 SpaceXAI Console API 키에서는 지원되지 않습니다.

Codex는 OpenAI 디바이스 인증 플로우를 사용합니다. 제공자 페이지에서 디바이스 코드를 생성하고 표시된 확인 URL을 열어 코드를 입력하고 로그인을 완료한 후 인증 상태를 확인합니다. Polaris는 Codex가 반환한 계정 범위의 모델 카탈로그를 저장하고 필요 시 OAuth 액세스 토큰을 갱신하며 Codex Responses 전송 프로토콜을 통해 호환 요청을 전달합니다. OpenAI Platform은 API 키 인증을 사용하며 키는 계정 모델 카탈로그를 통해 유효성이 검증된 후 Credentials에 추가됩니다. 두 제품 모두 제공자별 검증 및 중복 제거 기능을 갖춘 JSON 및 ZIP 가져오기를 지원합니다.

Claude Code는 Anthropic의 PKCE OAuth 플로우를 사용합니다. 인증 링크를 생성하고 인증을 완료한 후 반환된 인증 코드를 제공자 페이지에 붙여넣습니다. Claude Platform은 Anthropic API 키를 수락합니다. 두 제품 모두 각 자격 증명별로 지원되는 모델 목록을 검색하고 Anthropic Messages 전송 프로토콜을 사용하며 가능한 경우 Claude Code 액세스 토큰을 자동 갱신하고 검증된 JSON 또는 ZIP 가져오기를 지원합니다.

Muse Code는 Meta 기기 인증을 사용합니다. **Providers → Muse Code**에서 링크를 얻고 Meta에서 코드를 승인한 뒤 **Save credential**로 돌아옵니다. CLI, Linux, VPS 없이 직접 연결하며 모델 접두사는 `muse-code/`입니다. 표시 이름은 선택 사항입니다. 요금제, 세션/주간 할당량, 재설정 및 관측 시각은 공급자가 반환할 때만 표시합니다. 누락은 잔여 100%를 뜻하지 않습니다. 새로 고침은 현재 세션으로 구독을 확인하고 추론 키를 받습니다. 세션이 만료되면 다시 로그인하세요.

Kiro는 Google/GitHub 브라우저 OAuth, AWS 기기 인증 및 API 키를 지원합니다. 고급 필드는 방식에 따라 실행 리전, AWS 토큰 리전/시작 URL 또는 API 키 프로필 ARN입니다.

Ollama 연결은 엔드포인트별로 구성되며 보안 서버 또는 클라우드 서버를 위한 선택적 Bearer API 키를 포함할 수 있습니다. Polaris는 `/api/tags`를 통해 가용 모델을 검색하고 `/api/chat`을 통해 추론 라우팅을 수행합니다. Polaris가 Docker 내에서 실행 중인 경우 `localhost`는 컨테이너 자체를 가리킵니다. 호스트 게이트웨이 주소 또는 네트워크로 접근 가능한 다른 Ollama 엔드포인트를 사용하세요.

전체 자격 증명 가져오기 및 Google Antigravity 일괄 가져오기는 최대 10MB 압축 파일, 최대 500개 파일, 개별 자격 증명 파일 최대 2MB 및 압축 해제 후 최대 25MB의 데이터를 지원합니다. Google AI Studio, OpenAI, Anthropic 및 Ollama 개별 제공자 가져오기에는 파일당 최대 2MB, 최대 200개 JSON 항목, 압축 해제 후 최대 5MB의 더 엄격한 제한이 적용됩니다.

**Credentials**(`/credentials`)는 계정과 키를 공급자별로 묶습니다. 관리 대화상자는 식별 정보, 모델, 상태 및 가능한 작업을 보여줍니다. OAuth는 요금제, 크레딧, 기간별/모델별 할당량을 제공할 수 있습니다. API 키가 이메일, 요금제 또는 청구 정보를 자동으로 제공하는 것은 아닙니다. 없는 데이터는 이용 불가로 남깁니다.

**Download ZIP**은 자격 증명을 내보내며 **Import ZIP**은 공급자별 검증·중복 제거와 항목별 오류 보고를 수행합니다. 가져오기나 카탈로그 조회 성공이 추론 권한을 보장하지 않습니다. **Test model**은 실제 호출로 할당량이나 비용이 발생할 수 있습니다. ZIP에는 비밀 정보가 포함됩니다. 전체 SQLite 및 설정은 **Settings**의 암호화 백업을 사용하세요.

Google Antigravity 자격 증명은 `google-antigravity-{account_fingerprint}.json` 형식으로 저장되며 핑거프린트는 평문을 노출하지 않고 정규화된 계정 이메일에서 파생됩니다. Google AI Studio는 `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth는 `grok-{account_fingerprint}.json`, SpaceXAI Console은 `xai-console-{key_fingerprint}.json`, Codex는 `openai-codex-{account_fingerprint}.json`, OpenAI Platform은 `openai-platform-{key_fingerprint}.json`, Claude Code는 `claude-code-{account_fingerprint}.json`, Claude Platform은 `claude-platform-{key_fingerprint}.json`, Ollama 연결은 `ollama-{connection_fingerprint}.json`을 사용합니다. 레거시 `provider_*.json` 및 `xai-grok-*.json` 자격 증명과의 하위 호환성도 유지되며 내보내기 시 표준 이름으로 자동 정규화됩니다.

자격 증명 모드 이름:

- `code_assist`: 표준 Code Assist 자격 증명.
- `provider`: 범용 제공자 백엔드 자격 증명.

<a id="storage"></a>

## 데이터 스토리지

SQLite를 권장합니다. Compose는 `/app/backend/data`를 `polaris-data`에 저장합니다. 직접 Docker를 사용하면 `/app/backend/data/creds`와 `/app/backend/data/logs`를 `/opt/polaris/creds`, `/opt/polaris/logs` 같은 영구 경로에 마운트하세요.

PostgreSQL은 선택 사항이며 MongoDB는 Redis 없는 호환 옵션입니다. 하나만 설정하세요. 초기화 실패는 시작을 중단하며 SQLite로 조용히 전환하지 않습니다. 외부 DB도 수평 확장을 제공하지 않으며 worker와 복제본은 하나씩입니다. 이동 가능한 암호화 백업은 SQLite만 지원하고 백엔드 간 실시간 마이그레이션은 지원하지 않습니다.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[데이터 스토리지](../storage.md)

환경 변수를 통한 자격 증명 가져오기도 지원됩니다. 제어판에서 작업하거나 다음 변수 중 하나에 원본 JSON 문자열을 설정하거나 Base64로 인코딩된 `_B64` 접미사 변수를 사용합니다:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

페이로드 내용은 단일 자격 증명 객체, 배열 또는 `{ "credentials": [...] }` 구조일 수 있습니다.

<a id="development"></a>

## 개발 가이드

이 섹션은 프로젝트 기여자 및 로컬 디버깅을 위한 것입니다. 프로덕션 배포는 영구 호스트 볼륨이 있는 Docker를 사용하세요.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

[품질 게이트](../quality-gates.md)는 작업, 단계, 출시 검사를 구분합니다. `python tools/quality_gate.py --list-suites`는 선택적 외부 실시간 검사도 나열합니다. [호환성 규약](../compatibility.md)은 SDK/관리 경로, 마이그레이션, 스키마 및 예제를 보호합니다.

모든 코드 검사가 통과한 후 서비스를 시작합니다:

```bash
python backend/main.py
```

프로덕션 실행 기준은 Python 3.12이며 CI 자동화 테스트는 Python 3.12 및 3.14를 포함합니다. Pull Request 제출 절차 및 코드 리뷰 기준은 [기여 가이드](../../CONTRIBUTING.md)를 참조하세요.

<a id="deployment-notes"></a>

## 배포 시 주의사항

- 자격 증명이 포함된 JSON 파일이나 `.env` 파일은 절대 커밋하지 마세요.
- 클라이언트 연동용 전용 `API_KEY`와 콘솔 접속용 개별 `PANEL_PASSWORD`를 각각 구성하세요.
- 영구 자격 증명 데이터 볼륨이나 외부 데이터베이스에 대한 접근 권한을 엄격히 제한하고 플랫폼 계층에서 저장 시 암호화(encryption at rest)를 활성화하세요. 라우터는 제공자 토큰을 복호화하여 읽을 수 있어야 합니다.
- 서비스를 localhost 외부로 노출할 때는 반드시 TLS가 구성된 역방향 프록시 뒤에 Polaris를 배치하세요.
- 역방향 프록시가 `Host` 요청 헤더를 유지하고 `X-Forwarded-Proto`를 전달하도록 구성하세요. 완전한 HTTPS 종료가 보장된 경우 `PANEL_COOKIE_SECURE=true`를 설정합니다.
- `X-Forwarded-For` 및 `X-Forwarded-Proto`를 덮어쓰는 신뢰할 수 있는 프록시를 통해서만 서비스에 접근할 수 있는 경우에만 `TRUST_PROXY_HEADERS=true`를 설정하세요.
- 프로세스 생존 확인에는 `GET /health`를 사용하고 스토리지 계층을 포함한 준비 상태 확인에는 `GET /ready`를 사용하세요.
- 외부 원격 측정은 선택 사항입니다. Prometheus에는 `PROMETHEUS_EXPORT_ENABLED`와 강력한 `METRICS_TOKEN`이 필요합니다. OpenTelemetry는 집계만 내보내며 프롬프트/응답 본문은 보내지 않습니다. [관측 가능성](../observability.md)을 참고하세요.
- Docker 이미지는 시작 초기에 마운트된 데이터 디렉터리의 소유권을 수정하는 동안에만 root 권한으로 실행되며 이후 권한이 없는 `gateway` 사용자로 전환하여 실행됩니다.
- 브라우저 클라이언트에서 크로스 오리진 접근이 필요한 경우 `CORS_ORIGINS`에 신뢰할 수 있는 오리진을 명시적으로 설정하세요.
- SQLite 업데이트·이동 전에 [인증된 암호화 백업](../backup-and-restore.md)을 사용하고 파일과 암호문구를 `polaris-data` 밖에 보관하세요.
- Docker 이미지 게시는 Docker Hub용 저장소 시크릿 `DOCKERHUB_USERNAME` 및 `DOCKERHUB_TOKEN`을 사용하고 GitHub Packages(`ghcr.io/nguywnben/polaris`)용 기본 제공 `GITHUB_TOKEN`을 사용합니다. 사용자 정의 Docker Hub 이미지 이름으로 게시할 때만 선택적 `IMAGE_NAME` 변수를 설정하세요.
- 1.x 시리즈 버전에서는 `WORKERS=1` 및 단일 애플리케이션 복제본을 유지하세요. 외부 스토리지가 분산 조율 메커니즘을 대체할 수는 없습니다.
- 표준 규격의 `/api/credentials` 관리 라우트를 사용하세요. 베타 버전의 `/api/creds` 별칭은 1.0.0에서 완전히 제거되었습니다.
- 베타 배포를 마이그레이션하기 전에 [1.0 업그레이드 가이드](../upgrading-to-1.0.md)를 확인하세요.
- 기존 실행 인스턴스를 업그레이드하거나 롤백할 때는 [업데이트 가이드](../updating.md)를 참조하세요.
- 태그를 지정하거나 이미지를 릴리스하기 전에 관리되는 [릴리스 체크리스트](../release-checklist.md)를 순서대로 확인하세요.
- 실제 사용량 쿼터에 맞춰 로그 보존 및 자격 증명 로테이션 정책을 적절히 수립하세요.
- 코드 저장소나 클라우드 플랫폼 보안 검색에서 자격 증명 유출이 감지되면 즉시 해당 자격 증명을 해지하고 교체하세요.
- Render 배포 매니페스트는 영구 디스크가 포함된 유료 서비스를 사용합니다. Render의 무료 서비스는 휘발성 파일 시스템을 사용하므로 일회성 테스트 용도로만 적합합니다.

<a id="community-and-project-health"></a>

## 커뮤니티 및 프로젝트 건전성

- Pull Request를 제출하기 전에 [기여 가이드](../../CONTRIBUTING.md)를 읽어주세요.
- 보안 취약점 보고는 [보안 정책](../../SECURITY.md)에 명시된 비공개 절차를 통해 제출해 주세요.
- 각 릴리스의 세부 변경 사항은 [변경 로그](../../CHANGELOG.md)를 참조하세요.
- 본 프로젝트의 모든 관련 활동에서 [행동 강령](../../CODE_OF_CONDUCT.md)을 준수해야 합니다.

<a id="acknowledgements-inspirations"></a>

## 감사의 글 & 영감의 원천

Polaris는 오픈 소스 AI 라우팅, 관측 가능성 및 게이트웨이 커뮤니티의 탄탄한 토대 위에 구축되었습니다. 다음 프로젝트의 창립자 및 유지 관리자분들께 깊은 존경과 감사를 표합니다:

| 프로젝트 | 프로젝트 설명 | Stars |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | 멀티 프로바이더 키 관리 및 웹 기반 API 집계 아키텍처의 영감 원천 | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | AI 코딩 CLI를 위한 선구적인 다중 프로토콜 프록시 및 포맷 변환 계층 | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | 업계 표준의 통합 LLM 프록시, 로드 밸런싱 및 장애 조치 라우팅 | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | 초고속 AI 게이트웨이 아키텍처, 라우팅 전략 및 고탄력 장애 대응 모드 | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | 오픈 소스 LLM 엔지니어링 플랫폼, 호출 추적, 시스템 관측 가능성 및 지표 수집 | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## 오픈 소스 라이선스

Polaris는 [MIT 오픈 소스 라이선스](../../LICENSE)에 따라 배포됩니다.
