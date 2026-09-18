<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Router universal de IA y pasarela multiproveedor unificada para herramientas de desarrollo con IA</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">Proveedores compatibles</a> • <a href="#core-capabilities">Capacidades principales</a> • <a href="#deployment">Despliegue</a> • <a href="#sdk-surfaces">Inicio rápido: Integración SDK</a> • <a href="#architecture">Arquitectura</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <b>Español</b> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

Este README está disponible en 15 idiomas con el mismo alcance funcional. Las guías enlazadas conservan su idioma original.

Un router de IA universal para herramientas de desarrollo. Polaris ofrece conmutación por error automática inteligente (smart auto-fallback), limpieza de contexto consciente de tokens, visibilidad de uso y traducción de formatos transparente para que los agentes locales, asistentes de IDE y scripts de automatización puedan aprovechar la capacidad de LLM gratuitos y de pago mediante una única interfaz de API estable.

> Polaris admite alojamiento propio para una persona o un equipo de confianza con un worker y una réplica. Docker Compose, acceso del propietario local, SQLite, enrutamiento e interfaces SDK documentadas forman el núcleo. PostgreSQL, OIDC, proxy inverso y telemetría externa son opcionales; MongoDB es una opción de compatibilidad. La coordinación entre varias réplicas y Kubernetes quedan fuera del alcance admitido. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Por qué elegir Polaris

Los flujos de trabajo de desarrollo modernos a menudo combinan múltiples clientes y proveedores: herramientas compatibles con OpenAI, SDK nativos de Gemini, agentes con estilo de Anthropic, credenciales respaldadas por Google y rutas de modelos experimentales. Polaris se sitúa entre esos clientes y los backends de modelos para que cada herramienta pueda seguir utilizando el formato que ya comprende, mientras la pasarela se encarga del enrutamiento, reintentos, limpieza de solicitudes y normalización de respuestas.

<a id="core-capabilities"></a>

## Capacidades principales

- Conmutación automática con reservas por solicitud, rotación justa, pausas y consideración de cuotas agotadas.
- Limpieza de historiales extensos conservando instrucciones del sistema, herramientas y turnos recientes.
- Conversión entre OpenAI Chat Completions/Responses, Gemini y Anthropic Messages, incluido streaming.
- Gestión de cuentas OAuth y claves API con verificación, estado y deduplicación por proveedor.
- Catálogo por credencial para respetar los permisos de cada cuenta.
- Registro de rutas de modelos no disponibles por credencial y recuperación desde Models.
- SSE, pseudo-streaming y reintentos limitados de respuestas truncadas.
- Enrutamiento equilibrado, por prioridad, ponderado, menor latencia o menor coste.
- Claves virtuales con presupuestos diarios/mensuales, RPM/TPM, caducidad y modelos permitidos.
- Coste estimado en USD por llamada con agregados en el panel y Prometheus.
- Protecciones opcionales contra inyecciones, palabras bloqueadas y datos personales.
- Caché opcional de respuestas deterministas con coincidencia exacta.
- Prometheus, exportación opcional a Langfuse y seguimiento del uso.
- Consola para credenciales, registros, configuración, uso y versiones.

<a id="console-preview"></a>

## Vista previa de la consola

Las capturas muestran datos ficticios de una demo sin conexión y aislada.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — Panel de control" width="1600" height="1100" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — Vista previa de la consola" width="1600" height="1100" />
</picture>

<a id="supported-providers"></a>

## Proveedores compatibles

El catálogo contiene 23 proveedores. Los modelos y funciones disponibles dependen de los permisos de cada credencial.

| Proveedor | Conexión | Servicio / alcance |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | Clave API | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | Clave API | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (código de dispositivo) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | Clave API | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | Clave API | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Endpoint; clave API opcional | Local / alojamiento propio |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | Clave API | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | Token API + ID de cuenta | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | Clave API | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | Clave API | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | Clave API; ID de organización opcional | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | Clave API / servicio | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | Clave API | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | OAuth de navegador / dispositivo AWS / clave API | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (dispositivo Meta) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | Clave API | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | Clave API | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | Clave API | Inferencia alojada de NVIDIA |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | Clave API + plan Zen/Go | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | Clave API | Poolside API |

Los clientes usan las [interfaces SDK](#sdk-surfaces) comunes. Conversión, streaming y conmutación dependen del modelo; las opciones incompatibles se rechazan explícitamente. La conexión se configura por proveedor o credencial en **Providers**. Muse Code y Meta Model API tienen credenciales y espacios de modelos separados.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## Arquitectura

```text
herramientas de cliente
  SDKs de OpenAI | SDKs de Google GenAI | SDKs de Anthropic | Integraciones IDE
        |
        v
Polaris
  autenticación -> traducción de formato -> limpieza consciente de tokens -> enrutamiento -> failover -> streaming
        |
        v
adaptadores de proveedores
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

La API pública mantiene su estabilidad mientras los adaptadores específicos de cada proveedor evolucionan continuamente dentro de Polaris.

<a id="repository-structure"></a>

## Estructura del repositorio

```text
backend/       Raíz de composición de FastAPI, núcleo de enrutamiento, adaptadores, almacenamiento y pruebas
frontend/      Interfaz de consola web, estilos, scripts y activos de logotipos de proveedores
deploy/        Definiciones de contenedores, manifiestos de plataforma y scripts de inicio de SO
docs/          Notas de arquitectura y documentación de mantenimiento del proyecto
.github/       Flujos de CI, automatización de dependencias y plantillas de contribución
```

Consulte [Arquitectura](../architecture.md) para conocer más sobre los límites de módulos, flujos de solicitudes, propiedad de estado y restricciones de la versión actual.

<a id="deployment"></a>

## Despliegue

Docker Compose es la vía principal para una máquina y un worker. Siga la [instalación](../installation.md) y su [matriz de soporte](../installation.md#support-matrix) hasta el panel autenticado, sin asumir soporte ARM64 adicional.

El perfil básico no requiere servicios externos y guarda datos en `polaris-data`. La plantilla está orientada a `1.0.0`. Instale solo con etiquetas e imágenes publicadas de Polaris de la misma versión; para código aún no publicado, cree una imagen local independiente siguiendo la [lista de publicación](../releases/1.0.0-preparation.md). Utilice el [procedimiento de actualización y reversión](../updating.md); las opciones avanzadas se activan mediante `deploy/compose.advanced.yml`.

Consulte el [contrato de identificadores](../migrations/polaris.md) y la [resolución de problemas](../troubleshooting.md). Scripts nativos, `docker run`, Render y Zeabur son alternativas de compatibilidad sin las mismas pruebas de instalación/recuperación. La imagen se publica para `linux/amd64`; `linux/arm64` sigue suspendida.

### Para desarrollo o diagnóstico local:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

En Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Abra la consola; usa la misma configuración inicial que Docker:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## Configuración

Prioridad: variables de entorno, configuración guardada y valores predeterminados. La [referencia generada](../reference/configuration.md) indica tipos, grupos, responsables y aplicación inmediata, tras reinicio o solo por entorno. Un valor inválido impide iniciar e identifica la variable; se advierten posibles errores en nombres `POLARIS_*`.

| Variable de entorno | Valor predeterminado | Descripción |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Dirección de escucha (bind address). |
| `PORT` | `4283` | Puerto HTTP. |
| `HOST_PORT` | `4283` | Puerto del host utilizado únicamente por Docker Compose. |
| `WORKERS` | `1` | Solo se admite un worker. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Solo se admite `standalone`. |
| `POLARIS_REPLICA_COUNT` | `1` | Solo se admite una réplica. |
| `CORS_ORIGINS` | vacío | Lista separada por comas de orígenes de navegador autorizados para llamadas a la API de origen cruzado. Dejar vacío para uso de consola en el mismo origen. |
| `CORS_ORIGIN_REGEX` | vacío | Expresión regular opcional para orígenes de navegador dinámicos. |
| `API_KEY` | generada automáticamente | Clave API del cliente con prefijo `sk-polaris-`. |
| `PANEL_PASSWORD` | vacío hasta configurar | Contraseña de acceso al panel de control web. |
| `SETUP_TOKEN` | vacío | Configuración remota inicial: valor único de al menos 24 caracteres, no generado ni registrado. No requerido en localhost directo. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Tiempo de vida de la sesión del panel de control web en segundos. |
| `PANEL_COOKIE_SECURE` | automático | Establezca en `true` para forzar cookies solo a través de HTTPS. Vacío para autodetección mediante `X-Forwarded-Proto`. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Ventana de límite de tasa de inicio de sesión en segundos. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Intentos máximos de inicio de sesión fallidos permitidos por cliente dentro de la ventana de límite. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Número máximo de direcciones de clientes rastreadas en memoria por el limitador de inicio de sesión. |
| `MAX_REQUEST_BODY_MB` | `64` | Tamaño máximo del cuerpo de solicitud HTTP en MiB. Las solicitudes que excedan el límite devolverán errores con la estructura nativa del protocolo correspondiente. |
| `TRUST_PROXY_HEADERS` | `false` | Acepte encabezados de reenvío de cliente/protocolo solo si provienen de un proxy inverso de confianza que los sobrescriba. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Directorio de almacenamiento de credenciales. En Docker, mantenga `/app/backend/data/creds` persistente mediante volúmenes de host. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Endpoint del backend de Code Assist. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Endpoint del backend de Google Antigravity. |
| `PROXY` | vacío | Proxy HTTP, HTTPS o SOCKS opcional. |
| `RETRY_429_ENABLED` | `true` | Habilita reintentos acotados para límites de tasa y fallos temporales de upstream. El nombre antiguo se mantiene por compatibilidad. |
| `RETRY_429_MAX_RETRIES` | `5` | Número máximo de reintentos para fallos temporales de upstream. |
| `RETRY_429_INTERVAL` | `1` | Intervalo base de retroceso (backoff) entre reintentos temporales en segundos. |
| `AUTO_DISABLE` | `false` | Deshabilita automáticamente credenciales tras errores graves configurados. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Lista separada por comas de códigos de estado de error grave. |
| `ROUTING_STRATEGY` | `balanced` | Estrategia: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | vacío | Proveedor preferido para la estrategia `priority`, por ejemplo `google_antigravity` o `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Tiempo de espera para inferencia del proveedor (5 a 900 segundos). |
| `RESPONSE_CACHE_ENABLED` | `false` | Caché en memoria de respuestas deterministas sin streaming, temperatura 0. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Duración del caché en segundos. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Máximo de respuestas en caché. |
| `GUARDRAILS_ENABLED` | `false` | Activar protecciones previas a la llamada. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Ocultar correos, tarjetas y claves API en texto saliente. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Rechazar inyección de prompts con HTTP 400. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | vacío | Palabras bloqueadas separadas por comas, sin distinguir mayúsculas. |
| `PRICING_SYNC_ENABLED` | `true` | Actualizar precios LiteLLM en segundo plano; conservar última copia válida sin conexión. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Actualización de precios: 1–168 horas. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Intentos máximos de continuación para la función de streaming contra truncamiento (anti-truncation). |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Comprime historiales de conversación excesivamente largos antes de enrutarlos al proveedor. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Umbral estimado de tokens de entrada para activar la compresión de contexto. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Objetivo de tokens de entrada tras la compresión. Debe ser inferior al umbral de activación. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Número mínimo de turnos de usuario recientes que deben preservarse durante la compresión. |
| `COMPATIBILITY_MODE` | `false` | Convierte mensajes del sistema para clientes/modelos que no los admiten de forma nativa. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Devuelve el proceso de razonamiento del modelo (reasoning) cuando esté disponible. |
| `MONGODB_URI` | vacío | Almacenamiento MongoDB de compatibilidad. |
| `POSTGRESQL_URI` | vacío | Almacenamiento PostgreSQL opcional. |
| `CODE_ASSIST_CLIENT_ID` | cliente de escritorio incluido | Anulación opcional del Client ID OAuth de Code Assist. |
| `CODE_ASSIST_CLIENT_SECRET` | cliente de escritorio incluido | Anulación opcional del Client Secret OAuth de Code Assist. |
| `ANTIGRAVITY_CLIENT_ID` | cliente de escritorio incluido | Anulación opcional del Client ID OAuth de Google Antigravity (configurable también en la página de Proveedores). |
| `ANTIGRAVITY_CLIENT_SECRET` | cliente de escritorio incluido | Anulación opcional del Client Secret OAuth de Google Antigravity. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Anulación opcional del endpoint Generative Language API de Google AI Studio. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Anulación opcional del endpoint de API para credenciales de API Key de SpaceXAI Console. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Anulación opcional del endpoint de suscripción Grok Build OAuth. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Anulación opcional del emisor OAuth de Grok Build. La consola solo acepta hosts HTTPS bajo el dominio `x.ai`. |
| `XAI_CLIENT_ID` | cliente público incluido | Anulación opcional del Client ID OAuth PKCE de Grok Build. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Anulación opcional del User-Agent HTTP compartido para solicitudes OAuth de Grok Build y API de SpaceXAI Console. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Anulación opcional del endpoint de API de OpenAI Platform (configurable también en la página de Proveedores). |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Anulación opcional del endpoint de inferencia y catálogo de modelos de cuenta de Codex. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Anulación opcional del endpoint de verificación de límites de cuenta de Codex. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Anulación opcional del servicio de autorización de dispositivos de Codex. |
| `CODEX_CLIENT_ID` | cliente público incluido | Anulación opcional del Client ID OAuth de dispositivos de Codex. |
| `CODEX_USER_AGENT` | compatible con Codex CLI | Anulación opcional de User-Agent para solicitudes de Codex. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Endpoint Messages exclusivo de Claude Code. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Anulación opcional del endpoint de autorización PKCE de Claude Code. Solo hosts oficiales de Anthropic y Claude. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Anulación opcional del endpoint de token de Claude Code. Solo hosts oficiales de Anthropic y Claude. |
| `CLAUDE_CLIENT_ID` | cliente público incluido | Anulación opcional del Client ID OAuth PKCE de Claude Code. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | User-Agent exclusivo de Claude Code. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Endpoint separado de Claude Platform en Providers. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | User-Agent independiente de Claude Platform. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Anulación opcional de User-Agent para solicitudes a nivel de protocolo de Google Antigravity. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Anulación opcional del campo userAgent a nivel de carga útil de Google Antigravity. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Activar exportación autenticada `GET /metrics`. |
| `METRICS_TOKEN` | vacío | Token Bearer de al menos 32 bytes UTF-8 requerido para Prometheus. |
| `OTEL_EXPORT_ENABLED` | `false` | Activar exportación agregada OTLP/HTTP sin contenido. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | vacío | Collector HTTPS; no se permiten credenciales en la URL. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Intervalo de exportación: 15–300 segundos. |
| `LANGFUSE_PUBLIC_KEY` | vacío | Activar Langfuse junto con su clave secreta. |
| `LANGFUSE_SECRET_KEY` | vacío | Clave secreta Langfuse para trazas. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Endpoint de recepción Langfuse. |
| `LOG_LEVEL` | `info` | Nivel de detalle de los registros (log level). |
| `LOG_MAX_MB` | `10` | Tamaño máximo en MB de un archivo de registro activo antes de rotar. |
| `LOG_BACKUP_COUNT` | `3` | Cantidad de archivos de registro rotados que se conservan. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | Ruta del archivo de registro. En Docker, mantenga `/app/backend/data/logs` persistente mediante volúmenes de host. |

### Control de compresión

La política global AI Quality manda. Una clave solo puede heredarla o desactivar compresión mediante `PATCH /api/virtual-keys/{key_id}/quality-policy` con su revisión actual; `inherit` elimina esa restricción. Una solicitud autenticada puede usar `x-polaris-compression: off`; omitirlo o usar `inherit` aplica la política global/de clave. No puede reactivar compresión deshabilitada globalmente ni hacerla más agresiva. Solo se elimina un prefijo seguro del historial; ante estimación o estructura incierta se envía sin comprimir. Los tokens son estimaciones.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## Inicio rápido: Integración SDK

Polaris está diseñado respetando el comportamiento estándar de URL de los SDK oficiales de Python. Configure cada cliente exactamente como se indica a continuación; la pasarela no requiere prefijos de ruta redundantes o no estándar.

Los siguientes ejemplos utilizan el modelo virtual `polaris`. Configure su orden de prioridad de fallback en la página de Modelos previamente, o reemplácelo por el ID de un modelo específico de un proveedor.

### OpenAI Python SDK

Utilice `/v1` como Base URL para OpenAI. El SDK agregará automáticamente `/chat/completions` al final.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Explica este repositorio de código en un solo párrafo."}],
)
```

El mismo cliente puede invocar directamente la API OpenAI Responses:

```python
response = client.responses.create(
    model="polaris",
    instructions="Responde de manera concisa y clara.",
    input="Explica este repositorio de código en un solo párrafo.",
)

print(response.output_text)
```

La compatibilidad con Responses admite entrada de texto, imágenes, Function Tools sin streaming y streaming de texto por SSE. Las herramientas integradas alojadas por OpenAI, el historial persistente de respuestas y las llamadas a funciones en streaming serán rechazadas explícitamente, ya que Polaris no ejecuta, persiste ni descarta silenciosamente estos comportamientos propietarios de OpenAI.

### Anthropic Python SDK

Utilice el origen de la pasarela como Base URL para Anthropic. El SDK agregará automáticamente `/v1/messages` al final.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Escribe un mensaje de commit breve."}],
)
```

### Google GenAI Python SDK

Utilice el origen de la pasarela como Base URL para Google GenAI. El SDK agregará automáticamente la ruta predeterminada del modelo, como `/v1beta/models/{model}:generateContent`.

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
    contents="Escribe una función corta en Python.",
    config=types.GenerateContentConfig(
        system_instruction="Eres un asistente útil y competente.",
    ),
)
```

### Endpoints compatibles

Polaris proporciona rutas compatibles con los SDK estándar sin necesidad de prefijos de espacio de nombres adicionales:

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

Los errores de autenticación, validación de solicitudes, enrutamiento, fallos de upstream y errores previos al inicio del streaming utilizan las estructuras de error nativas de cada interfaz de SDK. Todas las respuestas HTTP incluyen el encabezado `X-Request-ID`; los clientes pueden enviar un identificador en este encabezado para rastrear el flujo de solicitudes. Las respuestas con límite de tasa o no disponibles temporalmente conservan el encabezado `Retry-After` de forma transparente cuando el upstream lo proporciona.

<a id="model-features"></a>

## Gestión avanzada de modelos

La página de Modelos construye el modelo virtual `polaris` agregando los modelos descubiertos a partir de las credenciales de proveedores habilitadas. Defina una única vez el orden de prioridad de los modelos subyacentes y utilice `polaris` desde cualquiera de los SDK compatibles. Polaris balanceará la carga entre las credenciales saludables que admitan el modelo principal y pasará automáticamente al siguiente modelo configurado si el primero deja de estar disponible. Los IDs de modelos físicos de los proveedores siguen estando disponibles para clientes que requieran una selección determinista. Guardar una lista vacía desactivará `polaris` sin afectar las credenciales de los proveedores.

El descubrimiento de modelos es consciente de cada proveedor: los modelos compartidos pueden ser atendidos por varios proveedores, mientras que los modelos propietarios solo se enrutan a credenciales compatibles. Cada credencial verificada mantiene su propio catálogo de proveedor, y el router prioriza el soporte declarado explícitamente por la credencial sobre deducciones generales. La actualización del catálogo verifica la disponibilidad en tiempo real con el proveedor; las opciones que dejen de estar disponibles seguirán mostrándose en la configuración hasta que se restablezcan o eliminen manualmente.

Cuando un upstream devuelve un error `404` para un modelo físico específico, Polaris registra una ruta no disponible para esa credencial y modelo en lugar de desactivar todo el proveedor. Dicha ruta se omitirá de forma inmediata y permanecerá visible bajo **Rutas de modelos no disponibles** hasta que se limpie o la credencial sea verificada nuevamente. Esto evita que los límites de suscripción o restricciones regionales de una cuenta afecten a otras cuentas saludables del mismo proveedor. Si ninguna credencial habilitada declara o permite deducir el soporte para un modelo solicitado, la pasarela devolverá un error explícito de falta de credenciales compatibles en lugar de enviar la solicitud a un proveedor al azar.

Polaris interpreta prefijos y sufijos de funciones en los nombres de modelos:

- `fake-streaming/{model}` o el prefijo de pseudo-streaming configurado para clientes que requieren obligatoriamente el formato SSE.
- `streaming-anti-truncation/{model}` o el prefijo de anti-truncamiento configurado para la recuperación automática en generaciones extensas en streaming.
- Sufijos de profundidad de razonamiento (como `-high`, `-medium`, `-low`, `-minimal`, `-max`) para modelos compatibles de la familia Gemini.
- Sufijos de búsqueda como `-search` para modelos compatibles con fundamentación en Google Search (grounding).

Los adaptadores de los proveedores normalizan estos identificadores de funciones antes de enviar las solicitudes al upstream.

<a id="usage-and-cost-visibility"></a>

## Transparencia de uso y costes

Cada intento de proveedor, reintento y conmutación se cuenta por separado; las trazas conservan el resultado final de la solicitud lógica. Se registran éxito, credencial, tokens declarados de entrada/salida/caché/razonamiento, ahorro estimado y coste USD. Uso ausente no equivale a cero medido. Los periodos siguen límites fijos de la zona horaria del navegador; el día cubre 00:00–23:00. El catálogo público LiteLLM se actualiza al iniciar y cada 24 horas por defecto; se conserva atómicamente la última copia válida y un fallo no bloquea inferencia. `model_pricing.json` en el directorio de credenciales tiene prioridad; precios por millón de tokens. Agregados en el panel, `/api/virtual-keys` y `/metrics`. La facturación y el tokenizer del proveedor son la referencia.

Las claves virtuales admiten presupuestos diarios/mensuales, ventanas deslizantes RPM/TPM, caducidad y patrones glob de modelos. Se almacenan hashes SHA-256; el secreto se muestra solo al crearlo.

<a id="credential-workflow"></a>

## Flujo de trabajo con credenciales

1. Inicie Polaris.
2. Acceda a `http://IP_DE_SU_SERVIDOR:4283` en un VPS, o a `http://127.0.0.1:4283` en desarrollo local.
3. Complete las comprobaciones y cree la contraseña del propietario. Antes de configurar remotamente, establezca un `SETUP_TOKEN` único de al menos 24 caracteres o `PANEL_PASSWORD`. El token no se genera ni se registra automáticamente.
4. Añada cuentas, claves API o conexiones Ollama desde la página de Proveedores.
5. Verifique la validez de las credenciales y supervise los enfriamientos y errores en el panel. **Credentials** (`/credentials`).
6. Configure sus herramientas de programación para que se conecten a una de las interfaces de API compatibles descritas anteriormente.

Al agregar credenciales de Google Antigravity, Google redirigirá el navegador a `http://localhost:4283/callback` una vez completado el inicio de sesión. En un equipo local, Polaris mostrará directamente la página de éxito de OAuth. En un VPS, dado que ese `localhost` apunta al navegador local del usuario, es posible que la página no cargue; copie la URL completa de la barra de direcciones del navegador, regrese a la página de Proveedores, péguela en el campo `Callback URL` y haga clic en `Guardar credencial`.

Google AI Studio utiliza autenticación mediante API Key en lugar de OAuth. Añada una clave desde la página de Proveedores; Polaris verificará su validez frente al catálogo de modelos de Google, la guardará como credencial de proveedor y enrutará las solicitudes de Gemini o Gemma compatibles a través de ella. El router inteligente puede alternar automáticamente entre AI Studio y Google Antigravity para modelos Gemini compartidos, reservando los modelos propietarios para credenciales compatibles.

La importación masiva de Google AI Studio admite archivos JSON y archivos ZIP que contengan archivos JSON. Los documentos JSON pueden contener una clave única, una lista `api_keys` o una lista de objetos de clave:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

La importación de archivos es sin conexión: Polaris comprueba la estructura JSON/ZIP, guarda las claves nuevas como `unverified` y omite claves duplicadas o existentes sin contactar con Google. Las listas de modelos importadas no se consideran verificadas. Los errores de formato se notifican sin revelar las claves. Después, ejecute la verificación/detección de modelos de la credencial; **Test model** comprueba por separado el acceso a inferencia y puede consumir cuota o generar cargos.

Grok Build admite credenciales OAuth PKCE, mientras que SpaceXAI Console admite claves API. Las claves de SpaceXAI Console se validan frente al catálogo de modelos de la API de SpaceXAI Console antes de guardarse. Para Grok Build OAuth, Polaris genera un enlace de autorización; tras completar la autorización, copie el código mostrado en la página de Grok Build y péguelo en el formulario. Los tokens de acceso se renuevan automáticamente cuando existe un refresh token, y ambos tipos de credenciales solo exponen los modelos declarados en sus catálogos actuales. La página del Credentials permite consultar el uso mensual de créditos de las cuentas Grok Build OAuth y el uso semanal cuando xAI lo proporciona. Esta vista de facturación a nivel de cuenta no está disponible para claves API de SpaceXAI Console.

Codex utiliza el flujo de autorización de dispositivos de OpenAI. Genere un código de dispositivo en la página de Proveedores, abra la URL de verificación mostrada, ingrese el código, complete el inicio de sesión y regrese para comprobar la autorización. Polaris almacena el catálogo de modelos de cuenta devuelto por Codex, renueva los tokens de acceso OAuth cuando es necesario y reenvía las solicitudes compatibles mediante el transporte Codex Responses. OpenAI Platform utiliza autenticación por API Key; las claves se validan frente al catálogo de modelos antes de guardarse en Credentials. Ambos productos admiten importación mediante JSON y ZIP con validación y deduplicación específica por proveedor.

Claude Code utiliza el flujo OAuth PKCE de Anthropic. Genere el enlace de autorización, complete el proceso y pegue el código de autorización recibido en la página de Proveedores. Claude Platform acepta claves API de Anthropic. Ambos productos descubren los modelos admitidos para cada credencial, utilizan el transporte Anthropic Messages, renuevan los tokens de acceso de Claude Code cuando es posible y admiten importaciones validadas mediante JSON o ZIP.

Muse Code usa autorización de dispositivo Meta. En **Providers → Muse Code**, obtenga el enlace, apruebe el código en Meta y vuelva a **Save credential**. La conexión es directa, sin CLI, Linux ni VPS. Los modelos llevan `muse-code/`; se admite un nombre visible opcional. Plan, cuotas de sesión/semana, reinicios y momento de observación solo aparecen si el proveedor los devuelve. Un dato ausente no significa 100 % restante. Actualizar comprueba la suscripción y obtiene la clave de inferencia con la sesión actual; vuelva a iniciar sesión si ya no es válida.

Kiro admite OAuth de navegador Google/GitHub, autorización de dispositivo AWS y clave API. Los campos avanzados dependen del método: región de ejecución, región de token/URL inicial AWS o ARN de perfil para clave API.

Las conexiones Ollama se configuran por endpoint y pueden incluir una Bearer API Key opcional para servidores protegidos o en la nube. Polaris descubre los modelos disponibles a través de `/api/tags` y enruta la inferencia a través de `/api/chat`. Cuando Polaris se ejecuta dentro de Docker, `localhost` apunta al propio contenedor; utilice la dirección de host-gateway o un endpoint de Ollama accesible a través de la red.

La importación completa del Credentials y la importación masiva de Google Antigravity admiten archivos comprimidos de hasta 10 MB, con un máximo de 500 archivos, hasta 2 MB por archivo de credencial individual y un total descomprimido de hasta 25 MB. Las importaciones individuales de Google AI Studio, OpenAI, Anthropic y Ollama aplican límites más estrictos: 2 MB por archivo importado, 200 registros JSON y 5 MB de datos descomprimidos.

**Credentials** (`/credentials`) agrupa cuentas y claves por proveedor. El diálogo muestra identidad, modelos, estado y acciones admitidas. OAuth puede aportar cuotas por ventana o modelo, plan y créditos. Las claves API no proporcionan automáticamente correo, suscripción ni facturación; los datos ausentes quedan como no disponibles.

**Download ZIP** exporta credenciales; **Import ZIP** procesa varios proveedores con validación y deduplicación específicas. Los errores se informan por entrada. Importar o descubrir un catálogo no demuestra acceso a inferencia; **Test model** envía una solicitud real que puede consumir cuota o generar costes. Los archivos contienen secretos. Para respaldar SQLite y configuración completos use el proceso cifrado de **Settings**.

Las credenciales de Google Antigravity se almacenan con el formato `google-antigravity-{account_fingerprint}.json`, donde la huella se deriva del correo electrónico normalizado sin exponer el texto plano. Google AI Studio utiliza `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth utiliza `grok-{account_fingerprint}.json`, SpaceXAI Console utiliza `xai-console-{key_fingerprint}.json`, Codex utiliza `openai-codex-{account_fingerprint}.json`, OpenAI Platform utiliza `openai-platform-{key_fingerprint}.json`, Claude Code utiliza `claude-code-{account_fingerprint}.json`, Claude Platform utiliza `claude-platform-{key_fingerprint}.json` y las conexiones Ollama utilizan `ollama-{connection_fingerprint}.json`. Las credenciales antiguas con formato `provider_*.json` y `xai-grok-*.json` mantienen compatibilidad retrospectiva y se exportan con sus nombres normalizados.

Nombres de modo de credencial:

- `code_assist`: credenciales estándar de Code Assist.
- `provider`: credenciales de backend de proveedores generales.

<a id="storage"></a>

## Almacenamiento de datos

SQLite es el almacenamiento recomendado. Compose conserva `/app/backend/data` en `polaris-data`; con Docker directo monte `/app/backend/data/creds` y `/app/backend/data/logs` en rutas duraderas como `/opt/polaris/creds` y `/opt/polaris/logs`.

PostgreSQL es opcional; MongoDB se mantiene por compatibilidad y funciona directamente sin Redis. Configure solo uno. Un fallo de inicialización detiene el arranque sin volver silenciosamente a SQLite. El almacenamiento externo no permite escalar horizontalmente: un worker y una réplica. El respaldo portátil cifrado solo admite SQLite; no hay migración en vivo entre backends admitida.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[Almacenamiento de datos](../storage.md)

Se admite la importación de credenciales mediante variables de entorno. Puede realizarse desde la consola o estableciendo una de las siguientes variables con un string JSON sin procesar, o utilizando la variante con sufijo `_B64` codificada en Base64:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

El contenido puede ser un objeto de credencial único, una lista de credenciales o una estructura con `{ "credentials": [...] }`.

<a id="development"></a>

## Guía de desarrollo

Esta sección está dirigida a colaboradores del proyecto y depuración local. Los despliegues de producción deben utilizar Docker con volúmenes de host persistentes.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

Las [puertas de calidad](../quality-gates.md) distinguen tarea, fase y lanzamiento. `python tools/quality_gate.py --list-suites` enumera aparte las comprobaciones externas opcionales. El [contrato de compatibilidad](../compatibility.md) protege rutas SDK/gestión, migraciones, esquemas y ejemplos.

Inicie el servicio una vez que se hayan superado todas las comprobaciones:

```bash
python backend/main.py
```

La base estándar para producción es Python 3.12, y las pruebas automáticas en CI cubren Python 3.12 y 3.14. Consulte la [Guía de contribución](../../CONTRIBUTING.md) para conocer el flujo de pull requests y las expectativas de revisión de código.

<a id="deployment-notes"></a>

## Consideraciones de despliegue

- Nunca haga commit de archivos JSON de credenciales ni de archivos `.env`.
- Asigne una `API_KEY` dedicada para las integraciones de clientes y una `PANEL_PASSWORD` independiente para acceder a la consola.
- Restrinja el acceso al volumen de credenciales o base de datos externa y habilite el cifrado en reposo (encryption at rest) en la plataforma; el router debe poder descifrar y leer los tokens de proveedores.
- Ubique siempre Polaris detrás de un proxy inverso con TLS cuando esté expuesto más allá de localhost.
- Configure el proxy inverso para conservar el encabezado `Host` y reenviar `X-Forwarded-Proto`; establezca `PANEL_COOKIE_SECURE=true` cuando la terminación HTTPS esté garantizada.
- Establezca `TRUST_PROXY_HEADERS=true` únicamente si el servicio solo es accesible a través de un proxy de confianza que sobrescriba `X-Forwarded-For` y `X-Forwarded-Proto`.
- Utilice `GET /health` para sondeos de vitalidad (liveness probe) y `GET /ready` para sondeos de disponibilidad con comprobación de almacenamiento (readiness probe).
- Telemetría externa opcional: Prometheus requiere `PROMETHEUS_EXPORT_ENABLED` y un `METRICS_TOKEN` fuerte; OpenTelemetry exporta solo agregados. Nunca se exporta contenido de prompts/respuestas. Consulte [observabilidad](../observability.md).
- La imagen Docker solo opera como root brevemente al inicio para ajustar los permisos del directorio de datos montado, y luego pasa a ejecutarse bajo el usuario sin privilegios `gateway`.
- Defina `CORS_ORIGINS` con los orígenes confiables específicos cuando los clientes web requieran acceso cross-origin.
- Antes de actualizar o mover SQLite, use el [respaldo cifrado y autenticado](../backup-and-restore.md). Guarde archivo y frase secreta fuera de `polaris-data`.
- El flujo de publicación de imágenes Docker utiliza los secretos de repositorio `DOCKERHUB_USERNAME` y `DOCKERHUB_TOKEN` para Docker Hub, y el `GITHUB_TOKEN` integrado para GitHub Packages en `ghcr.io/nguywnben/polaris`. Configure la variable opcional `IMAGE_NAME` solo si publica con un nombre de imagen de Docker Hub personalizado.
- Mantenga `WORKERS=1` y una sola réplica de aplicación para toda la serie 1.x; el almacenamiento externo no sustituye a la coordinación distribuida.
- Utilice las rutas canónicas de administración `/api/credentials`. Las rutas con alias `/api/creds` de la fase beta fueron eliminadas en 1.0.0.
- Consulte la [Guía de actualización a 1.0](../upgrading-to-1.0.md) antes de migrar un despliegue de la versión beta.
- Siga la [Guía de actualización](../updating.md) al actualizar una instancia en ejecución o al revertir a una versión previa.
- Siga la [Lista de verificación de lanzamiento](../release-checklist.md) antes de crear etiquetas o publicar imágenes.
- Establezca políticas adecuadas de retención de registros y rotación de credenciales según sus cuotas de uso.
- Revoque y renueve inmediatamente las credenciales si los analizadores de seguridad del repositorio o de la nube detectan una fuga de secretos.
- El manifiesto de Render Blueprint utiliza servicios de pago con disco persistente. Los servicios gratuitos de Render emplean un sistema de archivos efímero y solo son aptos para pruebas temporales.

<a id="community-and-project-health"></a>

## Comunidad y salud del proyecto

- Lea la [Guía de contribución](../../CONTRIBUTING.md) antes de enviar un pull request.
- Reporte vulnerabilidades de seguridad a través del canal privado indicado en la [Política de seguridad](../../SECURITY.md).
- Revise el [Registro de cambios](../../CHANGELOG.md) para conocer las novedades de cada versión.
- Respete el [Código de conducta](../../CODE_OF_CONDUCT.md) en todos los espacios del proyecto.

<a id="acknowledgements-inspirations"></a>

## Agradecimientos e inspiración

Polaris se apoya en el trabajo de la comunidad de código abierto dedicada a enrutamiento de IA, telemetría y pasarelas. Expresamos nuestro sincero agradecimiento a los creadores y mantenedores de los siguientes proyectos:

| Proyecto | Descripción | Estrellas |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Inspiración arquitectónica en la gestión de claves multiproveedor y agregación de API vía web | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Pionero en la capa de proxy multiprotocolo y conversión de formatos para CLIs de programación con IA | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Referente de la industria en proxy LLM unificado, balanceo de carga y enrutamiento con tolerancia a fallos | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Arquitectura de pasarela de IA ultrarrápida, estrategias de enrutamiento y modos de alta resiliencia | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Plataforma de ingeniería de LLM de código abierto, rastreo de llamadas, observabilidad y métricas | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## Licencia

Polaris se distribuye bajo la [Licencia MIT](../../LICENSE).
