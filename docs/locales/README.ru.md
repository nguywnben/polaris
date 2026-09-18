<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Универсальный AI-маршрутизатор и единый мультипровайдерный шлюз для AI-инструментов разработки</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">Поддерживаемые провайдеры</a> • <a href="#core-capabilities">Основные возможности</a> • <a href="#deployment">Развертывание</a> • <a href="#sdk-surfaces">Интерфейсы SDK</a> • <a href="#architecture">Архитектура</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <b>Русский</b> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

Этот README доступен на 15 языках с одинаковым функциональным охватом. Связанные технические руководства сохраняют исходный язык.

Универсальный AI-маршрутизатор для инструментов разработки. Polaris обеспечивает интеллектуальное автоматическое переключение при сбоях (smart auto-fallback), очистку контекста с учетом токенов, прозрачность использования и бесшовную трансляцию форматов, позволяя локальным агентам, IDE-ассистентам и скриптам автоматизации задействовать бесплатные и платные мощности LLM через единый стабильный API-интерфейс.

> Polaris поддерживает самостоятельное размещение для одного человека или доверенной команды: один worker и одна реплика. Ядро включает Docker Compose, локального владельца, SQLite, маршрутизацию и описанные SDK-интерфейсы. PostgreSQL, OIDC, обратный прокси и внешняя телеметрия необязательны; MongoDB оставлен для совместимости. Координация нескольких реплик и Kubernetes не поддерживаются. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Почему Polaris

Современные рабочие процессы разработки часто объединяют множество клиентов и провайдеров: OpenAI-совместимые инструменты, нативные SDK Gemini, агенты в стиле Anthropic, учетные записи Google и экспериментальные маршруты моделей. Polaris выступает связующим звеном между этими клиентами и бэкендами моделей, позволяя каждому инструменту взаимодействовать в привычном ему формате, в то время как шлюз берет на себя маршрутизацию, повторные попытки (retries), очистку запросов и нормализацию ответов.

<a id="core-capabilities"></a>

## Основные возможности

- Автоматическое переключение с резервированием на запрос, равномерной ротацией, паузами и учётом исчерпанных квот.
- Очистка длинной истории с сохранением системных инструкций, инструментов и последних сообщений.
- Преобразование OpenAI Chat Completions/Responses, Gemini и Anthropic Messages, включая потоковую передачу.
- Управление OAuth-аккаунтами и API-ключами с проверкой и дедупликацией по провайдеру.
- Каталог моделей для каждой учётной записи с учётом её прав.
- Учёт недоступных маршрутов моделей и восстановление со страницы Models.
- SSE, псевдопотоковая передача и ограниченные повторы обрезанных ответов.
- Балансировка, приоритеты, веса, минимальная задержка или минимальная стоимость.
- Виртуальные ключи с дневным/месячным бюджетом, RPM/TPM, сроком действия и разрешёнными моделями.
- Оценка стоимости каждого вызова в USD и агрегаты в панели и Prometheus.
- Необязательная защита от инъекций, запрещённых слов и утечки персональных данных.
- Необязательный кэш детерминированных ответов по точному совпадению.
- Prometheus, необязательный экспорт Langfuse и учёт использования.
- Консоль для учётных данных, журналов, настроек, использования и версий.

<a id="console-preview"></a>

## Интерфейс консоли

![Polaris — Интерфейс консоли](../assets/screenshots/credential-pool.png)

<a id="supported-providers"></a>

## Поддерживаемые провайдеры

В каталоге 23 провайдера. Доступные модели и функции зависят от прав конкретных учётных данных.

| Провайдер | Подключение | Сервис / область |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API-ключ | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API-ключ | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (код устройства) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API-ключ | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | API-ключ | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Адрес API; ключ необязателен | Локально / собственный сервер |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | API-ключ | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | API-токен + ID аккаунта | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | API-ключ | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | API-ключ | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | API-ключ; ID организации необязателен | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | API-ключ / ключ сервиса | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | API-ключ | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | OAuth в браузере / устройство AWS / API-ключ | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (устройство Meta) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | API-ключ | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | API-ключ | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | API-ключ | Размещённый инференс NVIDIA |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | API-ключ + план Zen/Go | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | API-ключ | Poolside API |

Клиенты используют общие [SDK-интерфейсы](#sdk-surfaces). Преобразование, потоковая передача и переключение зависят от возможностей модели; несовместимые параметры явно отклоняются. Подключения задаются по провайдеру или учётным данным в **Providers**. Muse Code и Meta Model API используют отдельные учётные данные и пространства имён моделей.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## Архитектура

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | Интеграции IDE
        |
        v
Polaris
  аутентификация -> трансляция форматов -> очистка с учетом токенов -> маршрутизация -> failover -> стриминг
        |
        v
provider adapters
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

Публичный API остается стабильным, в то время как специализированные адаптеры провайдеров развиваются внутри Polaris.

<a id="repository-structure"></a>

## Структура репозитория

```text
backend/       Корень композиции FastAPI, ядро маршрутизации, трансляторы, хранилище и тесты
frontend/      Разметка консоли управления, стили, скрипты и визуальные ресурсы провайдеров
deploy/        Определения контейнеров, манифесты платформ и скрипты операционной системы
docs/          Заметки по архитектуре и документация проекта
.github/       CI, автоматизация зависимостей и шаблоны для участников
```

Подробнее о границах модулей, потоках запросов, владении состоянием и ограничениях текущего релиза см. в документе [Архитектура](../architecture.md).

<a id="deployment"></a>

## Развертывание

Основной путь — Docker Compose на одной машине с одним worker. Следуйте [установке](../installation.md) и [матрице поддержки](../installation.md#support-matrix).

Базовый профиль не требует внешних сервисов и хранит данные в `polaris-data`. Шаблон рассчитан на `1.0.0`. Используйте опубликованные теги и образы Polaris одной версии; для неопубликованного исходного кода соберите отдельный локальный образ по [контрольному списку выпуска](../releases/1.0.0-preparation.md). Используйте [процедуру обновления и отката](../updating.md); расширенные функции подключаются через `deploy/compose.advanced.yml`.

См. [контракт идентификаторов](../migrations/polaris.md) и [устранение неполадок](../troubleshooting.md). Нативные скрипты, `docker run`, Render и Zeabur — совместимые альтернативы без равноценной проверки установки/восстановления. Образы выпускаются для `linux/amd64`; выпуск `linux/arm64` приостановлен.

### Локальная разработка или диагностика:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

В Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Откройте консоль; первоначальная настройка совпадает с Docker:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## Конфигурация

Приоритет: окружение, сохранённые настройки, значения по умолчанию. [Генерируемый справочник](../reference/configuration.md) описывает типы, группы, ответственные модули и применение сразу, после перезапуска или только через окружение. Некорректное значение блокирует запуск с указанием переменной; вероятные опечатки `POLARIS_*` вызывают предупреждение.

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Адрес прослушивания (bind address). |
| `PORT` | `4283` | HTTP-порт. |
| `HOST_PORT` | `4283` | Порт на стороне хоста, используемый только в Docker Compose. |
| `WORKERS` | `1` | Поддерживается один worker. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Поддерживается только `standalone`. |
| `POLARIS_REPLICA_COUNT` | `1` | Поддерживается одна реплика. |
| `CORS_ORIGINS` | пусто | Список разрешенных источников браузера (origins) через запятую для cross-origin вызовов API. Оставьте пустым для работы с консолью из того же источника. |
| `CORS_ORIGIN_REGEX` | пусто | Необязательное регулярное выражение для динамически управляемых источников браузера. |
| `API_KEY` | создаётся автоматически | Клиентский API-ключ с префиксом `sk-polaris-`. |
| `PANEL_PASSWORD` | пусто до настройки | Пароль для веб-панели управления. |
| `SETUP_TOKEN` | пусто | Уникальный токен удалённой настройки от 24 символов; не создаётся и не журналируется. Для прямого localhost не нужен. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Время жизни сессии веб-консоли в секундах. |
| `PANEL_COOKIE_SECURE` | автоматически | Установите `true` для принудительного использования cookie панели только по HTTPS. Оставьте пустым для автоопределения HTTPS через `X-Forwarded-Proto`. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Окно ограничения частоты попыток входа в секундах. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Максимальное количество неудачных попыток входа на клиента в пределах окна. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Максимальное число клиентских адресов, отслеживаемых ограничителем входа в памяти. |
| `MAX_REQUEST_BODY_MB` | `64` | Максимальный размер тела HTTP-запроса в МиБ. Запросы SDK, превышающие лимит, возвращают нативную структуру ошибок соответствующего протокола. |
| `TRUST_PROXY_HEADERS` | `false` | Принимать заголовки переадресации клиента/протокола только от доверенного обратного прокси, который перезаписывает их. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Каталог хранения учетных данных. В Docker монтируйте `/app/backend/data/creds` как том хоста. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Бэкенд-эндпоинт Code Assist. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Бэкенд-эндпоинт Google Antigravity. |
| `PROXY` | пусто | Необязательный прокси HTTP, HTTPS или SOCKS. |
| `RETRY_429_ENABLED` | `true` | Включить ограниченные повторные попытки при превышении лимитов и временных сбоях апстрима. Устаревшее имя сохранено для совместимости. |
| `RETRY_429_MAX_RETRIES` | `5` | Максимальное количество повторных попыток при временных ошибках апстрима. |
| `RETRY_429_INTERVAL` | `1` | Базовая задержка между повторными попытками в секундах. |
| `AUTO_DISABLE` | `false` | Отключать учетные данные после критических ошибок из списка. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Список статус-кодов критических ошибок через запятую. |
| `ROUTING_STRATEGY` | `balanced` | Стратегия: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | пусто | Предпочитаемый провайдер для стратегии `priority`, например `google_antigravity` или `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Таймаут генерации ответа провайдером, в диапазоне от 5 до 900 секунд. |
| `RESPONSE_CACHE_ENABLED` | `false` | Кэш в памяти для детерминированных непотоковых ответов с температурой 0. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Срок кэша в секундах. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Максимум ответов в кэше. |
| `GUARDRAILS_ENABLED` | `false` | Включить защиту до вызова. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Маскировать email, карты и API-ключи в исходящем тексте. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Отклонять инъекции с HTTP 400. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | пусто | Запрещённые слова через запятую, без учёта регистра. |
| `PRICING_SYNC_ENABLED` | `true` | Обновлять цены LiteLLM в фоне; сохранять последнюю корректную копию офлайн. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Период обновления цен: 1–168 часов. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Максимальное количество попыток продолжения генерации для предотвращения обрыва стриминга. |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Сжимать избыточную историю диалога перед отправкой провайдеру. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Оценочный порог входных токенов для активации сжатия. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Целевой объем входных токенов после сжатия. Должен быть меньше порога активации. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Минимальное количество последних реплик пользователя, сохраняемых при сжатии. |
| `COMPATIBILITY_MODE` | `false` | Преобразовывать системные сообщения для клиентов/моделей, которые их не поддерживают. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Возвращать блоки рассуждений модели (reasoning), если они доступны. |
| `MONGODB_URI` | пусто | Совместимое хранилище MongoDB. |
| `POSTGRESQL_URI` | пусто | Необязательное хранилище PostgreSQL. |
| `CODE_ASSIST_CLIENT_ID` | встроенный настольный клиент | Необязательное переопределение Client ID OAuth для Code Assist. |
| `CODE_ASSIST_CLIENT_SECRET` | встроенный настольный клиент | Необязательное переопределение Client Secret OAuth для Code Assist. |
| `ANTIGRAVITY_CLIENT_ID` | встроенный настольный клиент | Необязательное переопределение Client ID OAuth для Google Antigravity. Можно настроить на странице Providers. |
| `ANTIGRAVITY_CLIENT_SECRET` | встроенный настольный клиент | Необязательное переопределение Client Secret OAuth для Google Antigravity. Настраивается через env или страницу Providers. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Необязательное переопределение эндпоинта Generative Language API в Google AI Studio. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Необязательное переопределение эндпоинта SpaceXAI Console API для API-ключей. Можно настроить на странице Providers. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Необязательное переопределение эндпоинта подписки Grok Build OAuth. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Необязательное переопределение эмитента Grok Build OAuth. Консоль принимает только HTTPS-хосты домена `x.ai`. |
| `XAI_CLIENT_ID` | встроенный публичный клиент | Необязательное переопределение Client ID для Grok Build PKCE OAuth. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Необязательное общее переопределение HTTP User-Agent для запросов Grok Build OAuth и SpaceXAI Console API. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Необязательное переопределение эндпоинта OpenAI Platform API. Можно настроить на странице Providers. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Необязательное переопределение эндпоинта инференса и каталога моделей аккаунта Codex. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Необязательное переопределение эндпоинта проверки лимитов частоты аккаунта Codex. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Необязательное переопределение службы авторизации устройств Codex. |
| `CODEX_CLIENT_ID` | встроенный публичный клиент | Необязательное переопределение Client ID для OAuth-авторизации устройств Codex. |
| `CODEX_USER_AGENT` | значение, совместимое с Codex CLI | Необязательное переопределение User-Agent для запросов Codex. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Отдельный Messages endpoint Claude Code. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Необязательное переопределение эндпоинта авторизации PKCE для Claude Code. Допустимы только хосты Anthropic и Claude. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Необязательное переопределение эндпоинта получения токена Claude Code. Допустимы только хосты Anthropic и Claude. |
| `CLAUDE_CLIENT_ID` | встроенный публичный клиент | Необязательное переопределение Client ID для Claude Code PKCE OAuth. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | Отдельный User-Agent Claude Code. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Независимый endpoint Claude Platform в Providers. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | Независимый User-Agent Claude Platform. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Необязательное переопределение протокольного User-Agent для Google Antigravity. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Необязательное переопределение поля userAgent на уровне payload для Google Antigravity. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Включить защищённый `GET /metrics`. |
| `METRICS_TOKEN` | пусто | Bearer-токен для Prometheus: не менее 32 байт UTF-8. |
| `OTEL_EXPORT_ENABLED` | `false` | Включить OTLP/HTTP-экспорт агрегатов без содержимого. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | пусто | HTTPS-коллектор; учётные данные в URL запрещены. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Интервал экспорта: 15–300 секунд. |
| `LANGFUSE_PUBLIC_KEY` | пусто | Включить Langfuse вместе с секретным ключом. |
| `LANGFUSE_SECRET_KEY` | пусто | Секретный ключ Langfuse для трассировки. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Адрес приёма данных Langfuse. |
| `LOG_LEVEL` | `info` | Уровень детализации журналов (log level). |
| `LOG_MAX_MB` | `10` | Максимальный размер активного файла журнала перед ротацией. |
| `LOG_BACKUP_COUNT` | `3` | Количество сохраняемых архивных файлов журнала. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | Путь к файлу журнала. В Docker монтируйте `/app/backend/data/logs` как том хоста. |

### Управление сжатием

Глобальная политика AI Quality имеет приоритет. Виртуальный ключ может только наследовать её или отключать сжатие через `PATCH /api/virtual-keys/{key_id}/quality-policy` с текущей ревизией; `inherit` снимает ограничение ключа. Авторизованный запрос может передать `x-polaris-compression: off`; отсутствие заголовка или `inherit` применяет глобальную политику и политику ключа. Нельзя включить запрещённое сжатие или усилить его. Удаляется только безопасный префикс истории; при неопределённости структуры или оценки запрос отправляется без изменений. Число токенов оценочное.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## Интерфейсы SDK

Polaris спроектирован с учетом стандартного поведения URL официальных SDK Python. Настраивайте каждый клиент строго по приведенным инструкциям; шлюз не требует нестандартных дублирующихся префиксов путей.

В примерах используется виртуальная модель `polaris`. Предварительно настройте приоритеты резервных моделей на странице Models или укажите конкретный идентификатор модели.

### OpenAI Python SDK

Используйте `/v1` в качестве базового URL для OpenAI. SDK автоматически добавит `/chat/completions`.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Объясни назначение этого репозитория в одном абзаце."}],
)
```

Тот же клиент может использовать OpenAI Responses API:

```python
response = client.responses.create(
    model="polaris",
    instructions="Отвечай кратко и емко.",
    input="Объясни назначение этого репозитория в одном абзаце.",
)

print(response.output_text)
```

Совместимость с Responses поддерживает текст, изображения на входе, нестриминговые function tools и SSE-стриминг текста. Встроенные облачные инструменты OpenAI, сохранение истории ответов и потоковые вызовы функций явно отклоняются, поскольку Polaris не исполняет, не сохраняет и не отбрасывает скрытно эти проприетарные механизмы OpenAI.

### Anthropic Python SDK

Используйте адрес шлюза как базовый URL для Anthropic. SDK автоматически добавит `/v1/messages`.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Составь краткое сообщение коммита."}],
)
```

### Google GenAI Python SDK

Используйте адрес шлюза как базовый URL для Google GenAI. SDK автоматически добавит маршрут модели по умолчанию, например `/v1beta/models/{model}:generateContent`.

```python
from google import genai
from google.genai import types

client = genai.Client(
    http_options={
        "base_url": "http://127.0.0.1:4283",
    },
    api_key="sk-polaris-..."
)

response = client.models.generate_content(
    model="polaris",
    contents="Напиши небольшую функцию на Python.",
    config=types.GenerateContentConfig(
        system_instruction="Ты — полезный ассистент.",
    ),
)
```

### Поддерживаемые маршруты

Polaris предоставляет маршруты, совместимые с поCredentialsярными SDK, без префиксов продуктов:

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

Ошибки аутентификации, валидации запросов, маршрутизации, апстрима и сбои до старта потока возвращаются в нативном формате ошибок выбранного интерфейса SDK. Каждый HTTP-ответ содержит заголовок `X-Request-ID`; клиенты могут передавать безопасный идентификатор в этом заголовке для сквозного отслеживания запросов. Ответы с ограничением частоты запросов или временной недоступностью сохраняют заголовок `Retry-After`, если он предоставлен апстримом.

<a id="model-features"></a>

## Возможности моделей

Страница Models формирует виртуальную модель `polaris` на основе моделей, обнаруженных среди активных учетных записей провайдеров. Расставьте входящие модели по приоритету один раз и используйте `polaris` в любом поддерживаемом SDK. Polaris распределяет нагрузку между работоспособными аккаунтами с поддержкой первой модели и переходит к следующим по списку в случае недоступности. Прямые ID моделей провайдеров остаются доступными для клиентов, которым требуется детерминированный выбор. Сохранение пустого списка отключает `polaris` без влияния на учетные данные провайдеров.

Обнаружение моделей учитывает специфику провайдеров: общая модель может обслуживаться несколькими провайдерами, тогда как уникальные модели используют только совместимые учетные данные. Каждый проверенный аккаунт сохраняет свой собственный каталог, и маршрутизатор отдает приоритет явно заявленной поддержке учетной записи, а не общим предположениям о возможностях провайдера. Обновление каталога повторно проверяет текущую доступность моделей; недоступные позиции остаются в конфигурации до их восстановления или удаления.

Когда апстрим возвращает ошибку `404` для конкретной модели, Polaris фиксирует недоступный маршрут для данной учетной записи и модели вместо отключения провайдера целиком. Этот маршрут временно исключается из ротации и отображается в разделе **Unavailable Model Routes** до его удаления или перепроверки учетных данных. Это предотвращает влияние региональных ограничений или уровней подписки одного аккаунта на другие аккаунты того же провайдера. Если ни одна активная учетная запись не поддерживает запрошенную модель, шлюз возвращает понятную ошибку отсутствия совместимых учетных данных вместо отправки запроса случайному провайдеру.

Polaris распознает префиксы и суффиксы возможностей в названиях моделей:

- `fake-streaming/{model}` или настроенный префикс псевдостриминга для клиентов, требующих обязательный вывод SSE.
- `streaming-anti-truncation/{model}` или настроенный префикс anti-truncation для автоматического восстановления стриминга при длинных ответах.
- Суффиксы рассуждений (thinking), такие как `-high`, `-medium`, `-low`, `-minimal` и `-max` для поддерживаемых моделей семейства Gemini.
- Суффиксы поиска, такие как `-search` для моделей с поддержкой поиска через Google Search (grounding).

Адаптеры провайдеров нормализуют эти модификаторы имен перед отправкой запроса апстриму.

<a id="usage-and-cost-visibility"></a>

## Использование и Прозрачность расходов

Каждая попытка провайдера, повтор и переключение считаются отдельно; трассировка сохраняет окончательный результат логического запроса. Учитываются результат, учётные данные, заявленные токены ввода/вывода/кэша/рассуждений, оценка экономии и стоимость USD. Отсутствующие данные — не измеренный ноль. Периоды имеют фиксированные границы в часовом поясе браузера; дневной вид охватывает 00:00–23:00. Цены LiteLLM по умолчанию обновляются при запуске и каждые 24 часа с атомарным сохранением последней корректной копии. Ошибка не блокирует инференс. `model_pricing.json` в каталоге учётных данных имеет приоритет; цены за миллион токенов. Агрегаты доступны в панели, `/api/virtual-keys` и `/metrics`. Счёт и tokenizer провайдера остаются источником истины.

Виртуальные ключи поддерживают дневной/месячный бюджет, скользящие окна RPM/TPM, срок действия и glob-правила моделей. Хранятся SHA-256-хэши; секрет показывается только при создании.

<a id="credential-workflow"></a>

## Работа с учетными данными

1. Запустите Polaris.
2. Откройте `http://IP_ВАШЕГО_СЕРВЕРА:4283` на VPS или `http://127.0.0.1:4283` при локальной разработке.
3. Пройдите проверки и создайте пароль владельца. До удалённой первоначальной настройки задайте уникальный `SETUP_TOKEN` длиной не менее 24 символов или `PANEL_PASSWORD`. Токен не создаётся автоматически и не записывается в журнал.
4. Добавьте аккаунт, API-ключ или подключение Ollama на странице Providers.
5. Проверьте учетные данные и отслеживайте статусы кулдаунов и ошибок в панели. **Credentials** (`/credentials`).
6. Направьте ваш инструмент разработки на один из описанных выше API-интерфейсов.

При добавлении учетных данных Google Antigravity сервис Google перенаправляет браузер на `http://localhost:4283/callback` после входа. На локальной машине Polaris покажет страницу успешной авторизации OAuth. На VPS адрес `localhost` относится к компьютеру с браузером пользователя, поэтому страница может не открыться; скопируйте полный URL из адресной строки браузера, вернитесь на страницу Providers, вставьте его в поле `Callback URL` и нажмите `Save credential`.

Google AI Studio использует аутентификацию по API-ключам вместо OAuth. Добавьте ключ на странице Providers; Polaris проверит его по каталогу моделей Google, сохранит как учетные данные провайдера и будет маршрутизировать через него совместимые запросы Gemini или Gemma. Интеллектуальный маршрутизатор может переключаться между AI Studio и Google Antigravity для общих моделей Gemini, сохраняя специфичные модели на совместимых аккаунтах.

Пакетный импорт для Google AI Studio принимает файлы JSON и ZIP-архивы с JSON. JSON-документ может содержать один ключ, массив `api_keys` или массив объектов ключей:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

Импорт файлов выполняется офлайн: Polaris проверяет структуру JSON/ZIP, сохраняет новые ключи со статусом `unverified` и пропускает дубликаты и существующие ключи без обращения к Google. Импортированные списки моделей не считаются проверенными. Ошибки формата сообщаются без раскрытия ключей. Затем явно запустите проверку учётных данных и обнаружение моделей; **Test model** отдельно проверяет доступ к инференсу и может расходовать квоту или приводить к списаниям.

Grok Build поддерживает учетные данные PKCE OAuth, а SpaceXAI Console — API-ключи. Ключи SpaceXAI Console проверяются по каталогу моделей API SpaceXAI Console перед сохранением. Для Grok Build OAuth шлюз генерирует ссылку авторизации; после подтверждения скопируйте код со страницы Grok Build и вставьте его в форму Grok Build OAuth. Токены доступа обновляются автоматически при наличии refresh-токена, и оба типа учетных данных предоставляют только модели, заявленные в их текущем каталоге. Страница Credentials позволяет запрашивать ежемесячный расход кредитов и еженедельный расход (если предоставляется xAI) для аккаунтов Grok Build OAuth. Этот просмотр биллинга на уровне аккаунта недоступен для API-ключей SpaceXAI Console.

Codex использует протокол авторизации устройств OpenAI. Сгенерируйте код устройства на странице Providers, перейдите по отображаемому URL, введите код, завершите вход и вернитесь для проверки авторизации. Polaris сохраняет каталог моделей аккаунта, возвращенный Codex, обновляет токены OAuth по мере необходимости и направляет совместимые запросы через транспорт Codex Responses. OpenAI Platform использует API-ключи; ключи проверяются через каталог моделей аккаунта перед добавлением в Credentials. Оба сервиса поддерживают импорт JSON и ZIP с проверкой и дедупликацией для каждого провайдера.

Claude Code использует протокол Anthropic PKCE OAuth. Сгенерируйте ссылку авторизации, завершите процесс в браузере и вставьте полученный код авторизации на странице Providers. Claude Platform принимает API-ключи Anthropic. Оба варианта определяют доступные модели для каждой учетной записи, используют транспорт Anthropic Messages, обновляют токены Claude Code при возможности и поддерживают проверенный импорт JSON или ZIP.

Muse Code использует авторизацию устройства Meta. В **Providers → Muse Code** получите ссылку, подтвердите код в Meta и вернитесь к **Save credential**. Подключение прямое: CLI, Linux и VPS не нужны; префикс моделей `muse-code/`, отображаемое имя необязательно. План, квоты сессии/недели, сбросы и время наблюдения показываются только при наличии данных провайдера. Отсутствие данных не означает остаток 100%. Обновление проверяет подписку и получает ключ инференса через текущую сессию; если она недействительна, войдите снова.

Kiro поддерживает браузерный OAuth Google/GitHub, устройства AWS и API-ключ. Расширенные поля зависят от метода: регион выполнения, регион токена/начальный URL AWS или ARN профиля API-ключа.

Подключения к Ollama настраиваются индивидуально для каждого эндпоинта и могут содержать необязательный Bearer API-ключ для защищенных или облачных серверов. Polaris опрашивает модели через `/api/tags` и маршрутизирует генерацию через `/api/chat`. При работе Polaris в Docker `localhost` указывает на сам контейнер; используйте адрес host-gateway или сетевой эндпоинт Ollama.

Импорт Credentials и пакетный импорт Google Antigravity принимают архивы размером до 10 МБ, содержащие не более 500 файлов, файлы отдельных учетных данных до 2 МБ и суммарный объем распакованных данных до 25 МБ. Для импорта Google AI Studio, OpenAI, Anthropic и Ollama действуют более строгие ограничения: 2 МБ на файл, 200 записей JSON и до 5 МБ распакованных данных.

**Credentials** (`/credentials`) группирует аккаунты и ключи по провайдерам. Диалог управления показывает идентичность, модели, состояние и доступные действия. OAuth может возвращать план, кредиты и квоты по окнам или моделям. API-ключи не предоставляют email, подписку и оплату автоматически; отсутствующие сведения остаются недоступными.

**Download ZIP** экспортирует учётные данные; **Import ZIP** проверяет и устраняет дубликаты по провайдеру с ошибками по каждой записи. Импорт или обнаружение каталога не доказывают доступ к инференсу. **Test model** выполняет реальный вызов, который может расходовать квоту или деньги. Архивы содержат секреты. Для всей SQLite и настроек используйте зашифрованную копию в **Settings**.

Учетные данные Google Antigravity сохраняются в формате `google-antigravity-{account_fingerprint}.json`, где отпечаток вычисляется из нормализованного email аккаунта без его раскрытия. Google AI Studio использует `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth — `grok-{account_fingerprint}.json`, SpaceXAI Console — `xai-console-{key_fingerprint}.json`, Codex — `openai-codex-{account_fingerprint}.json`, OpenAI Platform — `openai-platform-{key_fingerprint}.json`, Claude Code — `claude-code-{account_fingerprint}.json`, Claude Platform — `claude-platform-{key_fingerprint}.json`, а подключения Ollama — `ollama-{connection_fingerprint}.json`. Устаревшие файлы `provider_*.json` и `xai-grok-*.json` остаются совместимыми и экспортируются с каноническими именами.

Названия режимов учетных данных (Credential mode names):

- `code_assist`: стандартный учётные данные Code Assist.
- `provider`: учётные данные бэкенда провайдеров.

<a id="storage"></a>

## Хранилище

Рекомендуется SQLite. Compose сохраняет `/app/backend/data` в `polaris-data`; при прямом Docker подключите `/app/backend/data/creds` и `/app/backend/data/logs` к постоянным путям, например `/opt/polaris/creds` и `/opt/polaris/logs`.

PostgreSQL необязателен; MongoDB оставлен для совместимости и работает без Redis. Настройте только один. Ошибка инициализации останавливает запуск без скрытого возврата к SQLite. Внешняя БД не даёт горизонтального масштабирования: один worker и одна реплика. Переносимое зашифрованное резервирование доступно только для SQLite; живая миграция между хранилищами не поддерживается.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[Хранилище](../storage.md)

Импорт учетных данных из переменных окружения доступен из панели управления. Укажите одну из следующих переменных с необработанной строкой JSON или используйте соответствующий вариант `_B64` для base64-кодированного JSON:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

Тело может представлять собой один объект учетных данных, массив или структуру вида `{ "credentials": [...] }`.

<a id="development"></a>

## Разработка

Этот раздел предназначен для контрибьюторов и локальной отладки. Для производственных сред следует использовать Docker с постоянными томами хоста.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

[Проверки качества](../quality-gates.md) разделены на задачу, этап и релиз. `python tools/quality_gate.py --list-suites` также перечисляет необязательные проверки внешних сервисов. [Контракт совместимости](../compatibility.md) защищает SDK/управляющие маршруты, миграции, схемы и примеры.

Запустите сервис после успешного прохождения всех проверок:

```bash
python backend/main.py
```

Базовой версией для продакшена является Python 3.12, а CI в настоящее время проверяет совместимость с Python 3.12 и 3.14. Ознакомьтесь с [Руководством для контрибьюторов](../../CONTRIBUTING.md) относительно рабочего процесса pull request и требований к ревью кода.

<a id="deployment-notes"></a>

## Примечания по развертыванию

- Никогда не фиксируйте в коммитах JSON-файлы с учетными данными или файлы `.env`.
- Используйте выделенный `API_KEY` для интеграции с клиентами и отдельный `PANEL_PASSWORD` для доступа к веб-консоли.
- Ограничьте доступ к постоянному тому учетных данных или внешней базе данных и включите шифрование данных на уровне платформы (encryption at rest); шлюз должен иметь возможность считывать токены провайдеров.
- Размещайте Polaris за обратным прокси-сервером с поддержкой TLS при доступе за пределами localhost.
- Настройте обратный прокси для сохранения заголовка `Host` и передачи `X-Forwarded-Proto`; укажите `PANEL_COOKIE_SECURE=true`, если гарантирована терминация HTTPS.
- Устанавливайте `TRUST_PROXY_HEADERS=true` только тогда, когда сервис доступен исключительно через доверенный прокси, перезаписывающий `X-Forwarded-For` и `X-Forwarded-Proto`.
- Используйте `GET /health` для проверки жизнеспособности процесса (liveness) и `GET /ready` для проверки готовности с учетом хранилища (readiness).
- Внешняя телеметрия необязательна. Prometheus требует `PROMETHEUS_EXPORT_ENABLED` и надёжный `METRICS_TOKEN`; OpenTelemetry экспортирует только агрегаты, без содержимого запросов и ответов. См. [наблюдаемость](../observability.md).
- Docker-образ запускается с правами root лишь на время исправления прав доступа к примонтированному каталогу данных, а затем запускает сервис от имени непривилегированного пользователя `gateway`.
- Задайте `CORS_ORIGINS` с точным списком доверенных источников, если клиентам браузера требуется cross-origin доступ.
- Перед обновлением или переносом SQLite используйте [аутентифицированную зашифрованную копию](../backup-and-restore.md). Храните архив и пароль вне `polaris-data`.
- Публикация Docker-образов использует секреты репозитория `DOCKERHUB_USERNAME` и `DOCKERHUB_TOKEN` для Docker Hub, а также встроенный `GITHUB_TOKEN` для GitHub Packages по адресу `ghcr.io/nguywnben/polaris`. Задавайте переменную `IMAGE_NAME` только при публикации под пользовательским именем образа.
- Сохраняйте `WORKERS=1` и одну реплику приложения для всей линейки версий 1.x; внешнее хранилище не заменяет распределенную координацию.
- Используйте канонические маршруты управления `/api/credentials`. Бета-алиасы `/api/creds` были удалены в версии 1.0.0.
- Следуйте руководству [Обновление до 1.0](../upgrading-to-1.0.md) перед миграцией бета-развертываний.
- Следуйте [руководству по обновлению](../updating.md) при повышении версии работающего инстанса или откате на предыдущую версию.
- Выполняйте пункты [чек-листа релиза](../release-checklist.md) перед присвоением тега или публикацией образа.
- Согласуйте политики хранения логов и ротации учетных данных с вашими лимитами использования.
- Немедленно отзывайте и обновляйте учетные данные, если сканеры репозитория или платформы зафиксировали утечку секрета.
- Render Blueprint использует платный тариф с постоянным диском. Бесплатные сервисы Render используют временную файловую систему и подходят только для ознакомительного тестирования.

<a id="community-and-project-health"></a>

## Сообщество и Состояние проекта

- Прочтите [Руководство по участию](../../CONTRIBUTING.md) перед открытием pull request.
- Сообщайте об уязвимостях через конфиденциальный процесс в [Политике безопасности](../../SECURITY.md).
- Ознакомьтесь с [Историей изменений](../../CHANGELOG.md) для информации об изменениях в конкретных релизах.
- Соблюдайте [Кодекс поведения](../../CODE_OF_CONDUCT.md) во всех пространствах проекта.

<a id="acknowledgements-inspirations"></a>

## Благодарности и Вдохновение

Polaris создан благодаря наработкам сообщества разработчиков открытого исходного кода в области AI-маршрутизации, телеметрии и шлюзов. Мы выражаем искреннюю благодарность создателям и мейнтейнерам следующих проектов:

| Проект | Описание | Звезды |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Вдохновение для мультипровайдерного управления ключами и веб-агрегации API | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Первопроходец в области мультиформатного проксирования и трансляции протоколов для AI-инструментов разработки | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Эталон в области унифицированного LLM-проксирования, балансировки нагрузки и отказоустойчивой маршрутизации | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Сверхбыстрая архитектура AI-шлюза, гибкие стратегии маршрутизации и надежные шаблоны failover | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Open-source платформа для LLM-инжиниринга, трассировки, мониторинга и сбора метрик | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## Лицензия

Polaris распространяется под [Лицензией MIT](../../LICENSE).
