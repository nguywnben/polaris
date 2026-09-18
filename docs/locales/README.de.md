<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Universeller KI-Router & einheitliches Multi-Provider-Gateway für KI-Coding-Tools</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">Unterstützte Anbieter</a> • <a href="#core-capabilities">Kernfunktionen</a> • <a href="#deployment">Bereitstellung</a> • <a href="#sdk-surfaces">SDK-Schnittstellen</a> • <a href="#architecture">Architektur</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <b>Deutsch</b> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

Dieses README ist in 15 Sprachen verfügbar und beschreibt denselben Funktionsumfang von Polaris. Verlinkte Detailanleitungen bleiben in ihrer jeweiligen Originalsprache.

Ein universeller KI-Router für Coding-Tools. Polaris bietet intelligentes Auto-Fallback, tokenbewusste Kontextbereinigung, Nutzungstransparenz und nahtlose Formatübersetzung, sodass lokale Agenten, IDE-Assistenten und Automatisierungsskripte kostenlose und kostenpflichtige LLM-Kapazitäten über eine einzige stabile API-Schnittstelle nutzen können.

> Für den selbstverwalteten Produktivbetrieb durch eine Person oder ein vertrauenswürdiges Team werden ein Worker und eine Replik unterstützt. Docker Compose, lokaler Eigentümerzugang, SQLite, Routing und die dokumentierten SDK-Schnittstellen bilden den Kern. PostgreSQL, OIDC, Reverse Proxy und externe Telemetrie sind optionale Erweiterungen; MongoDB ist eine Kompatibilitätsoption. Koordinierter Mehrreplikabetrieb und Kubernetes gehören nicht zum unterstützten Umfang. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Warum Polaris

Moderne Entwicklungs-Workflows kombinieren oft mehrere Clients und Anbieter: OpenAI-kompatible Tools, native Gemini-SDKs, Agenten im Anthropic-Stil, Google-gestützte Anmeldedaten und experimentelle Modellrouten. Polaris positioniert sich zwischen diesen Clients und den Modell-Backends, sodass jedes Tool das Format beibehalten kann, das es bereits versteht, während das Gateway Routing, Wiederholungsversuche, Anfragebereinigung und Antwortnormalisierung übernimmt.

<a id="core-capabilities"></a>

## Kernfunktionen

- Intelligentes Fallback mit Reservierungen je Anfrage, fairer Rotation, Cooldowns und Berücksichtigung erschöpfter Kontingente.
- Tokenbewusste Bereinigung überlanger Historien unter Erhalt von Systemanweisungen, Werkzeugdefinitionen und jüngsten Dialogen.
- Übersetzung zwischen OpenAI Chat Completions/Responses, Gemini und Anthropic Messages, einschließlich Streaming.
- Verwaltung von OAuth-Konten und API-Schlüsseln mit Prüfung, Status und anbieterspezifischer Deduplizierung.
- Eigene Modellkataloge je Anmeldedatensatz, damit Kontoberechtigungen korrekt bleiben.
- Speicherung nicht verfügbarer Modellrouten je Anmeldedatensatz mit Wiederherstellung über Models.
- SSE, Pseudo-Streaming und begrenzte Wiederholungen bei abgeschnittenen Antworten.
- Auswahl nach Balance, Anbieterpriorität, Gewichtung, geringster Latenz oder niedrigsten Kosten.
- Virtuelle API-Schlüssel mit Tages-/Monatsbudgets, RPM/TPM, Ablaufzeit und Modellfreigaben.
- Geschätzte USD-Kosten je Aufruf mit Dashboard- und Prometheus-Aggregaten.
- Optionale Schutzregeln gegen Prompt Injection, Schlüsselwörter und personenbezogene Daten.
- Optionaler Cache für exakt übereinstimmende deterministische Antworten.
- Prometheus und optionaler Langfuse-Export sowie integrierte Nutzungsübersicht.
- Webkonsole für Anmeldedaten, Protokolle, Konfiguration, Nutzung und Versionen.

<a id="console-preview"></a>

## Konsolen-Vorschau

Die Screenshots zeigen fiktive Daten aus einer isolierten Offline-Demo.

### Dashboard

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — Dashboard" />
</picture>

### Zugangsdaten

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — Konsolen-Vorschau" />
</picture>

<a id="supported-providers"></a>

## Unterstützte Anbieter

Der Katalog umfasst 23 Anbieter. Verfügbare Modelle und Funktionen hängen vom jeweiligen Konto und seinen Berechtigungen ab.

| Anbieter | Verbindung | Dienst / Umfang |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API-Schlüssel | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API-Schlüssel | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (Gerätecode) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API-Schlüssel | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | API-Schlüssel | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Endpunkt; optionaler API-Schlüssel | Lokal / selbstverwaltet |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | API-Schlüssel | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | API-Token + Konto-ID | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | API-Schlüssel | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | API-Schlüssel | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | API-Schlüssel; optionale Organisations-ID | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | API-/Dienstschlüssel | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | API-Schlüssel | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | Browser-OAuth / AWS-Geräteanmeldung / API-Schlüssel | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (Meta-Gerätecode) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | API-Schlüssel | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | API-Schlüssel | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | API-Schlüssel | Gehostete NVIDIA-Inferenz |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | API-Schlüssel + Zen/Go-Tarif | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | API-Schlüssel | Poolside API |

Clients verwenden die gemeinsamen [SDK-Schnittstellen](#sdk-surfaces). Protokollübersetzung, Streaming und Fallback richten sich nach den Fähigkeiten des Modells; nicht unterstützte Optionen werden ausdrücklich abgelehnt. Verbindungseinstellungen gehören zum Anbieter oder Anmeldedatensatz unter **Providers**, nicht zu den Systemeinstellungen. Muse Code und Meta Model API verwenden getrennte Anmeldedaten und Modellnamensräume.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## Architektur

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | IDE-Integrationen
        |
        v
Polaris
  Authentifizierung -> Formatübersetzung -> tokenbewusste Bereinigung -> Routing -> Fallback -> Streaming
        |
        v
provider adapters
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

Die öffentliche API bleibt stabil, während sich die anbieterspezifischen Adapter unter Polaris kontinuierlich weiterentwickeln.

<a id="repository-structure"></a>

## Repository-Struktur

```text
backend/       FastAPI-Kompositions-Root, Routing-Kern, Übersetzer, Speicher und Tests
frontend/      Verwaltungskonsolen-Markup, Styles, Skripte und Anbieter-Grafiken
deploy/        Container-Definitionen, Plattform-Manifeste und Betriebssystem-Skripte
docs/          Architekturhinweise und gepflegte Projektdokumentation
.github/       CI, Abhängigkeitsautomatisierung und Vorlagen für Beiträge
```

Siehe [Architektur](../architecture.md) für Modulgrenzen, Anfragefluss, Zustandsverwaltung und aktuelle Release-Vorgaben.

<a id="deployment"></a>

## Bereitstellung

Docker Compose ist der Standard für eine Maschine mit einem Worker. Folgen Sie der [Installationsanleitung](../installation.md) und ihrer [Supportmatrix](../installation.md#support-matrix) bis zum authentifizierten Dashboard; daraus ergibt sich keine zusätzliche ARM64-Unterstützung.

Das Standardprofil benötigt keine externen Dienste und speichert Daten im Volume `polaris-data`. Die Vorlage zielt auf `1.0.0`. Installieren Sie nur mit veröffentlichten Polaris-Tags und Images derselben Version; erstellen Sie bei unveröffentlichtem Quellcode ein separates lokales Image gemäß der [Freigabe-Checkliste](../releases/1.0.0-preparation.md). Nutzen Sie den [Update- und Rollback-Ablauf](../updating.md); erweiterte Optionen werden über `deploy/compose.advanced.yml` aktiviert.

Beachten Sie den [Bezeichnervertrag](../migrations/polaris.md) und die [Fehlerbehebung](../troubleshooting.md). Native Skripte, direktes `docker run`, Render und Zeabur sind Kompatibilitätswege ohne dieselben Installations-/Wiederherstellungsnachweise. Das Produktionsimage wird für `linux/amd64` veröffentlicht; `linux/arm64` bleibt ausgesetzt.

### Für lokale Entwicklung oder Fehlersuche:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

Unter Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Konsole öffnen; dieselbe Ersteinrichtung gilt wie bei Docker:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## Konfiguration

Priorität: Umgebungsvariablen, gespeicherte Konfiguration, Standardwerte. Die [generierte Referenz](../reference/configuration.md) nennt Typ, Gruppe, Zuständigkeit sowie Live-/Neustart-/Umgebungsverhalten. Ungültige Werte verhindern den Start mit Angabe der Variable; verdächtige `POLARIS_*`-Namen erzeugen Warnungen.

| Umgebungsvariable | Standardwert | Zweck |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind-Adresse. |
| `PORT` | `4283` | HTTP-Port. |
| `HOST_PORT` | `4283` | Host-seitiger Port, der nur von Docker Compose verwendet wird. |
| `WORKERS` | `1` | Nur ein Worker wird unterstützt. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Nur `standalone` wird unterstützt. |
| `POLARIS_REPLICA_COUNT` | `1` | Nur eine Anwendungsreplik wird unterstützt. |
| `CORS_ORIGINS` | leer | Kommagetrennte Browser-Origins für zulässige Cross-Origin-API-Aufrufe. Leer lassen für Same-Origin-Konsolennutzung. |
| `CORS_ORIGIN_REGEX` | leer | Optionaler regulärer Ausdruck für dynamisch verwaltete Browser-Origins. |
| `API_KEY` | automatisch erzeugt | Client-API-Schlüssel mit Präfix `sk-polaris-`. |
| `PANEL_PASSWORD` | leer bis zur Einrichtung | Passwort für das Web-Control-Panel. |
| `SETUP_TOKEN` | leer | Vor Remote-Ersteinrichtung erforderlich: eigener Wert mit mindestens 24 Zeichen. Wird weder erzeugt noch protokolliert; direktes localhost benötigt ihn nicht. |
| `SETUP_ALLOW_INSECURE_HTTP` | `false` | Remote-Einrichtung über HTTP nur bei akzeptiertem Risiko unverschlüsselter Zugangsdaten und Sitzungen erlauben. HTTPS wird empfohlen; ein starkes Einrichtungstoken bleibt erforderlich. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Lebensdauer von Webkonsolen-Sitzungen in Sekunden. |
| `PANEL_COOKIE_SECURE` | automatisch | Auf `true` setzen, um reine HTTPS-Panel-Cookies zu erzwingen. Leer lassen, um HTTPS über `X-Forwarded-Proto` zu erkennen. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Zeitfenster für Login-Ratenbegrenzung in Sekunden. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Maximal zulässige fehlgeschlagene Login-Versuche pro Client innerhalb des Zeitfensters. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Maximale Anzahl an Client-Adressen, die im In-Memory-Login-Limiter gespeichert werden. |
| `MAX_REQUEST_BODY_MB` | `64` | Maximale HTTP-Request-Body-Größe in MiB. Zu große SDK-Anfragen geben die native Protokoll-Fehlerstruktur zurück. |
| `TRUST_PROXY_HEADERS` | `false` | Client-/Protokoll-Forwarding-Header nur von einem vertrauenswürdigen Reverse-Proxy akzeptieren, der diese überschreibt. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Verzeichnis für Anmeldedaten. In Docker `/app/backend/data/creds` als Host-Volume mounten. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Backend-Endpunkt für Code Assist. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Backend-Endpunkt für Google Antigravity. |
| `PROXY` | leer | Optionaler HTTP-, HTTPS- oder SOCKS-Proxy. |
| `RETRY_429_ENABLED` | `true` | Aktiviert begrenzte Wiederholungsversuche bei Ratenbegrenzungen und vorübergehenden Upstream-Fehlern. Legacy-Name aus Kompatibilitätsgründen beibehalten. |
| `RETRY_429_MAX_RETRIES` | `5` | Maximale Anzahl an Wiederholungsversuchen bei vorübergehenden Upstream-Fehlern. |
| `RETRY_429_INTERVAL` | `1` | Basisverzögerung zwischen vorübergehenden Wiederholungsversuchen in Sekunden. |
| `AUTO_DISABLE` | `false` | Deaktiviert Anmeldedaten nach konfigurierten schwerwiegenden Fehlern. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Kommagetrennte Statuscodes für schwerwiegende Fehler. |
| `ROUTING_STRATEGY` | `balanced` | Auswahlstrategie: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | leer | Bevorzugter Anbieter bei `priority`-Strategie, z. B. `google_antigravity` oder `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Timeout für Anbieter-Inferenz, begrenzt zwischen 5 und 900 Sekunden. |
| `RESPONSE_CACHE_ENABLED` | `false` | Deterministische Antworten ohne Streaming bei Temperatur 0 im Speicher puffern. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Gültigkeitsdauer eines Cache-Eintrags in Sekunden. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Maximale Anzahl gepufferter Antworten. |
| `GUARDRAILS_ENABLED` | `false` | Schutzregeln vor dem Anbieteraufruf aktivieren. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | E-Mails, Kartennummern und API-Schlüssel im ausgehenden Text maskieren. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Prompt-Injection-Versuche mit HTTP 400 ablehnen. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | leer | Kommagetrennte Sperrwörter ohne Beachtung der Großschreibung. |
| `PRICING_SYNC_ENABLED` | `true` | LiteLLM-Preiskatalog im Hintergrund aktualisieren; letzter gültiger Stand bleibt offline nutzbar. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Preisaktualisierung alle 1–168 Stunden. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Maximale Fortsetzungsversuche für Anti-Truncation-Streaming. |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Komprimiert überlange Konversationshistorien vor dem Routing an den Anbieter. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Geschätzter Eingabe-Token-Schwellenwert zur Aktivierung der Komprimierung. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Geschätztes Eingabe-Token-Ziel nach der Komprimierung. Muss niedriger als der Schwellenwert sein. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Mindestanzahl jüngster Benutzer-Interaktionen, die bei der Komprimierung erhalten bleiben. |
| `COMPATIBILITY_MODE` | `false` | Wandelt Systemnachrichten für Clients/Modelle um, die diese nicht unterstützen. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Gibt Modell-Denkprozesse (Reasoning) zurück, wenn verfügbar. |
| `MONGODB_URI` | leer | MongoDB-Speicherung als Kompatibilitätsoption. |
| `POSTGRESQL_URI` | leer | Optionale PostgreSQL-Speicherung. |
| `CODE_ASSIST_CLIENT_ID` | integrierter Desktop-Client | Optionales Überschreiben der Code Assist OAuth Client-ID. |
| `CODE_ASSIST_CLIENT_SECRET` | integrierter Desktop-Client | Optionales Überschreiben des Code Assist OAuth Client-Secrets. |
| `ANTIGRAVITY_CLIENT_ID` | integrierter Desktop-Client | Optionales Überschreiben der Google Antigravity OAuth Client-ID. Auch über die Providers-Seite verwaltbar. |
| `ANTIGRAVITY_CLIENT_SECRET` | integrierter Desktop-Client | Optionales Überschreiben des Google Antigravity OAuth Client-Secrets. Über Env oder Providers-Seite konfigurierbar. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Optionales Überschreiben des Generative Language API-Endpunkts von Google AI Studio. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Optionales Überschreiben des SpaceXAI Console API-Endpunkts für API-Schlüssel. Über die Providers-Seite verwaltbar. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Optionales Überschreiben des Grok Build OAuth-Abonnement-Endpunkts. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Optionales Überschreiben des Grok Build OAuth-Ausstellers. Nur HTTPS-Hosts unter `x.ai` werden akzeptiert. |
| `XAI_CLIENT_ID` | integrierter öffentlicher Client | Optionales Überschreiben der Grok Build PKCE OAuth Client-ID. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Optionales gemeinsames HTTP-User-Agent-Überschreiben für Grok Build OAuth- und SpaceXAI Console API-Anfragen. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Optionales Überschreiben des OpenAI Platform API-Endpunkts. Auch über die Providers-Seite verwaltbar. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Optionales Überschreiben des Codex Inferenz- und Kontomodell-Endpunkts. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Optionales Überschreiben des Codex Konto-Ratenbegrenzungs-Endpunkts. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Optionales Überschreiben des Codex Geräteautorisierungsdienstes. |
| `CODEX_CLIENT_ID` | integrierter öffentlicher Client | Optionales Überschreiben der Codex Geräte-OAuth-Client-ID. |
| `CODEX_USER_AGENT` | Codex-CLI-kompatibel | Optionales User-Agent-Überschreiben für Codex-Anfragen. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Messages-Endpunkt speziell für Claude Code überschreiben. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Optionales Überschreiben des Claude Code PKCE-Autorisierungsendpunkts. Nur Anthropic- und Claude-Hosts erlaubt. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Optionales Überschreiben des Claude Code Token-Endpunkts. Nur Anthropic- und Claude-Hosts erlaubt. |
| `CLAUDE_CLIENT_ID` | integrierter öffentlicher Client | Optionales Überschreiben der Claude Code PKCE OAuth Client-ID. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | User-Agent speziell für Claude Code überschreiben. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Separater Claude-Platform-Endpunkt unter Providers. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | Separater User-Agent für Claude Platform. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Optionales User-Agent-Überschreiben für das Google Antigravity Protokoll. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Optionales User-Agent-Überschreiben auf Payload-Ebene für Google Antigravity. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Authentifizierten Export über `GET /metrics` aktivieren. |
| `METRICS_TOKEN` | leer | Bearer-Token mit mindestens 32 UTF-8-Bytes für aktivierten Prometheus-Export. |
| `OTEL_EXPORT_ENABLED` | `false` | Inhaltsfreien aggregierten OTLP/HTTP-Export aktivieren. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | leer | HTTPS-Collector-Endpunkt; Zugangsdaten in URLs sind unzulässig. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Exportintervall: 15–300 Sekunden. |
| `LANGFUSE_PUBLIC_KEY` | leer | Langfuse-Export zusammen mit dem geheimen Schlüssel aktivieren. |
| `LANGFUSE_SECRET_KEY` | leer | Geheimer Langfuse-Schlüssel für den Trace-Export. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse-Empfangsendpunkt. |
| `LOG_LEVEL` | `info` | Protokollierungsgrad (Log-Level). |
| `LOG_MAX_MB` | `10` | Maximale Dateigröße des aktiven Logs vor der Rotation. |
| `LOG_BACKUP_COUNT` | `3` | Anzahl der aufbewahrten rotierten Protokolldateien. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | Pfad zur Protokolldatei. In Docker `/app/backend/data/logs` als Host-Volume mounten. |

### Kompressionssteuerung

Die globale AI-Quality-Richtlinie ist maßgeblich. Ein virtueller Schlüssel darf sie nur erben oder die Kompression über `PATCH /api/virtual-keys/{key_id}/quality-policy` mit aktueller Revision deaktivieren. `inherit` hebt diese Einschränkung auf. Eine authentifizierte Anfrage kann `x-polaris-compression: off` senden; ohne Header oder mit `inherit` gilt die globale/Schlüssel-Richtlinie. Schlüssel und Anfragen können global deaktivierte Kompression weder aktivieren noch verstärken. Es wird nur ein sicherer Historienanfang entfernt; bei unsicherer Schätzung oder Struktur bleibt die Anfrage unverändert. Tokenzahlen sind Schätzungen.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## SDK-Schnittstellen

Polaris orientiert sich am standardmäßigen URL-Verhalten der offiziellen Python-SDKs. Konfigurieren Sie jeden Client genau wie unten dargestellt; das Gateway erfordert keine unüblichen doppelten Pfadpräfixe.

Die folgenden Beispiele verwenden das virtuelle Modell `polaris`. Konfigurieren Sie dessen geordnete Fallback-Reihenfolge zuerst auf der Models-Seite oder ersetzen Sie es durch eine konkrete Modell-ID.

### OpenAI Python SDK

Verwenden Sie `/v1` als Basis-URL für OpenAI. Das SDK hängt automatisch `/chat/completions` an.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Erkläre dieses Repository in einem Absatz."}],
)
```

Derselbe Client kann auch die OpenAI Responses API verwenden:

```python
response = client.responses.create(
    model="polaris",
    instructions="Fasse dich kurz.",
    input="Erkläre dieses Repository in einem Absatz.",
)

print(response.output_text)
```

Die Responses-Kompatibilität unterstützt Text, Bildeingaben, nicht-streamende Function-Tools und SSE-Text-Streaming. Von OpenAI gehostete integrierte Tools, gespeicherte Antworthistorien und streamende Funktionsaufrufe werden explizit abgelehnt, da Polaris diese OpenAI-spezifischen Verhaltensweisen weder ausführt, speichert noch stillschweigend verwirft.

### Anthropic Python SDK

Verwenden Sie den Gateway-Origin als Basis-URL für Anthropic. Das SDK hängt automatisch `/v1/messages` an.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Entwirf eine prägnante Commit-Nachricht."}],
)
```

### Google GenAI Python SDK

Verwenden Sie den Gateway-Origin als Basis-URL für Google GenAI. Das SDK hängt automatisch die Standard-Modellroute an, z. B. `/v1beta/models/{model}:generateContent`.

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
    contents="Schreibe eine kleine Python-Funktion.",
    config=types.GenerateContentConfig(
        system_instruction="Du bist ein hilfreicher Assistent.",
    ),
)
```

### Unterstützte Routen

Polaris stellt SDK-kompatible Routen ohne produktbezogene Namespaces bereit:

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

Fehler bei Authentifizierung, Anfragevalidierung, Routing, Upstream-Aufrufen sowie Fehler vor dem Stream-Start verwenden die native Fehlerstruktur der jeweiligen SDK-Schnittstelle. Jede HTTP-Antwort enthält den Header `X-Request-ID`; Clients können eine sichere Kennung übergeben, um Anfragen durchgängig zu verfolgen. Ratenbegrenzte oder temporär nicht verfügbare Antworten behalten den Header `Retry-After` bei, wenn der Upstream-Anbieter ihn bereitstellt.

<a id="model-features"></a>

## Modellfunktionen

Die Seite Models erstellt das virtuelle Modell `polaris` aus den Modellen, die über aktivierte Anmeldedaten ermittelt wurden. Ordnen Sie die Modellmitglieder einmalig nach Priorität und verwenden Sie anschließend `polaris` in jedem unterstützten SDK. Polaris verteilt die Last auf gesunde Anmeldedaten, die das erste Modell unterstützen, und probiert bei Nichtverfügbarkeit die konfigurierte Reihenfolge durch. Konkrete Modell-IDs der Anbieter bleiben für deterministische Modellauswahlen verfügbar. Das Speichern einer leeren Liste deaktiviert `polaris`, ohne die Anmeldedaten der Anbieter zu beeinträchtigen.

Die Modellerkennung erfolgt anbietersensitiv: Ein geteiltes Modell kann von mehreren Anbietern unterstützt werden, während anbieterspezifische Modelle nur kompatible Anmeldedaten nutzen. Jeder verifizierte Anmeldedatensatz speichert seinen eigenen Anbieterkatalog, und der Router bevorzugt explizit deklarierte Unterstützung vor allgemeinen Anbieterannahmen. Das Aktualisieren des Katalogs prüft die aktuelle Anbieterverfügbarkeit erneut; nicht verfügbare Auswahlen bleiben in der Konfiguration sichtbar, bis sie wiederhergestellt oder gelöscht werden.

Gibt ein Upstream einen `404`-Fehler für ein konkretes Modell zurück, registriert Polaris eine nicht verfügbare Route für diesen Anmeldedatensatz und dieses Modell, anstatt den gesamten Anbieter zu deaktivieren. Diese Route wird sofort temporär umgangen und bleibt unter **Unavailable Model Routes** sichtbar, bis sie gelöscht oder der Anmeldedatensatz neu validiert wird. Dadurch wird verhindert, dass konto- oder regionsspezifische Einschränkungen andere Konten desselben Anbieters beeinträchtigen. Falls kein aktivierter Anmeldedatensatz das angeforderte Modell unterstützt, gibt das Gateway einen klaren Fehler zurück, anstatt die Anfrage an einen beliebigen Anbieter zu leiten.

Polaris erkennt Funktionspräfixe und -suffixe in Modellnamen:

- `fake-streaming/{model}` oder das konfigurierte Pseudo-Streaming-Präfix für Clients, die zwingend SSE-Ausgaben benötigen.
- `streaming-anti-truncation/{model}` oder das konfigurierte Anti-Truncation-Präfix zur automatischen Wiederherstellung bei langen Streaming-Generierungen.
- Thinking-Suffixe wie `-high`, `-medium`, `-low`, `-minimal` und `-max` für unterstützte Modelle der Gemini-Familie.
- Such-Suffixe wie `-search` für Modelle mit Google Search Grounding-Unterstützung.

Anbieter-Adapter normalisieren diese Funktionsnamen vor dem Weiterleiten an Upstream-Dienste.

<a id="usage-and-cost-visibility"></a>

## Nutzung und Kostentransparenz

Polaris zählt jeden Anbieteraufruf einschließlich Wiederholung und Fallback separat; Traces bewahren das Endergebnis der logischen Anfrage. Angezeigt werden Erfolgsquote, Anmeldedatensatz, gemeldete Eingabe-/Ausgabe-/Cache-/Reasoning-Token, geschätzte Kompressionseinsparungen und USD-Kosten. Fehlende Nutzungsangaben sind kein gemessener Nullwert. Dashboard-Zeiträume folgen festen Grenzen der Browser-Zeitzone; ein Tag umfasst 00:00–23:00. Der öffentliche LiteLLM-Preiskatalog wird beim Start und standardmäßig alle 24 Stunden geprüft und atomar zwischengespeichert; Ausfälle blockieren keine Inferenz. `model_pricing.json` im Anmeldedatenverzeichnis hat Vorrang; Preise gelten je Million Token. Aggregate stehen im Dashboard, unter `/api/virtual-keys` und über `/metrics` bereit. Abrechnung und Tokenizer des Anbieters bleiben maßgeblich.

Virtuelle API-Schlüssel können Tages-/Monatsbudgets, gleitende RPM-/TPM-Grenzen, Ablaufdatum und Modell-Globlisten erhalten. Gespeichert werden SHA-256-Hashes; das Klartextgeheimnis erscheint nur bei der Erstellung.

<a id="credential-workflow"></a>

## Workflow für Anmeldedaten

1. Starten Sie Polaris.
2. Öffnen Sie `http://IHRE_SERVER_IP:4283` auf einem VPS oder `http://127.0.0.1:4283` bei lokaler Entwicklung.
3. Ersteinrichtung abschließen und Eigentümerpasswort anlegen. Vor einer Remote-Einrichtung `SETUP_TOKEN` mit mindestens 24 Zeichen setzen oder `PANEL_PASSWORD` vorkonfigurieren. Das Einrichtungstoken wird weder automatisch erzeugt noch protokolliert.
4. Fügen Sie Konten, API-Schlüssel oder Ollama-Verbindungen auf der Seite Providers hinzu.
5. Verifizieren Sie Anmeldedaten und überwachen Sie Cooldown- und Fehlerzustände in der Konsole. **Credentials** (`/credentials`).
6. Richten Sie Ihr Entwicklungs-Tool auf eine der oben genannten API-Schnittstellen aus.

Beim Hinzufügen von Google Antigravity-Anmeldedaten leitet Google den Browser nach dem Login zu `http://localhost:4283/callback` weiter. Auf einem lokalen Rechner zeigt Polaris eine OAuth-Erfolgsseite an. Auf einem VPS gehört diese `localhost`-Adresse zum Browser-Rechner des Nutzers, sodass die Seite eventuell nicht lädt; kopieren Sie die vollständige URL aus der Adressleiste des Browsers, kehren Sie zur Seite Providers zurück, fügen Sie sie in `Callback URL` ein und klicken Sie auf `Save credential`.

Google AI Studio nutzt API-Schlüssel-Authentifizierung anstelle von OAuth. Fügen Sie einen Schlüssel über die Seite Providers hinzu; Polaris validiert ihn anhand des Modellkatalogs von Google, speichert ihn als Anbieter-Anmeldedatensatz und leitet kompatible Gemini- oder Gemma-Anfragen darüber weiter. Der intelligente Router kann bei gemeinsamen Gemini-Modellen zwischen AI Studio und Google Antigravity wechseln, während modellspezifische Anfragen auf kompatiblen Zugängen verbleiben.

Der Google AI Studio-Batch-Import akzeptiert JSON-Dateien und ZIP-Archive, die JSON-Dateien enthalten. Ein JSON-Dokument kann einen einzelnen Schlüssel, ein `api_keys`-Array oder ein Array von Schlüsselobjekten enthalten:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

Der Dateiimport erfolgt offline: Polaris prüft die JSON/ZIP-Struktur, speichert neue Schlüssel als `unverified` und überspringt doppelte oder bereits vorhandene Schlüssel, ohne Google zu kontaktieren. Importierte Modelllisten gelten nicht als bestätigt. Formatfehler werden ohne Offenlegung der Schlüssel gemeldet. Führen Sie danach die explizite Prüfung/Modellerkennung des Zugangsdaten-Eintrags aus; **Test model** prüft den Inferenzzugriff separat und kann Kontingent verbrauchen oder Kosten verursachen.

Grok Build unterstützt PKCE-OAuth-Anmeldedaten, während SpaceXAI Console API-Schlüssel unterstützt. Schlüssel der SpaceXAI Console werden vor dem Speichern anhand des SpaceXAI Console API-Modellkatalogs validiert. Für Grok Build OAuth generiert Polaris einen Autorisierungslink; kopieren Sie nach der Autorisierung den auf der Seite angezeigten Code und fügen Sie ihn in das Grok Build-Formular ein. Zugriffstokens werden automatisch aktualisiert, wenn ein Refresh-Token vorhanden ist, und beide Anmeldedatentypen zeigen nur die Modelle an, die in ihrem aktuellen Katalog deklariert sind. Die Credentials-Seite kann monatliche Guthabennutzung und wöchentliche Nutzung (sofern von xAI bereitgestellt) für Grok Build OAuth-Konten abrufen. Diese Abrechnungsansicht auf Kontoebene ist für SpaceXAI Console API-Schlüssel nicht verfügbar.

Codex verwendet den Geräteautorisierungs-Flow von OpenAI. Generieren Sie einen Gerätecode auf der Seite Providers, öffnen Sie die angezeigte Verifizierungs-URL, geben Sie den Code ein, schließen Sie die Anmeldung ab und prüfen Sie die Autorisierung. Polaris speichert den von Codex zurückgegebenen kontospezifischen Modellkatalog, aktualisiert OAuth-Tokens bei Bedarf und sendet kompatible Anfragen über den Codex Responses-Transport. OpenAI Platform nutzt API-Schlüssel-Authentifizierung; Schlüssel werden vor der Aufnahme in Credentials über den Kontomodellkatalog validiert. Beide Produkte unterstützen JSON- und ZIP-Importe mit anbieterspezifischer Validierung und Deduplizierung.

Claude Code verwendet den PKCE-OAuth-Flow von Anthropic. Generieren Sie einen Autorisierungslink, schließen Sie die Autorisierung ab und fügen Sie den erhaltenen Code auf der Seite Providers ein. Claude Platform akzeptiert Anthropic-API-Schlüssel. Beide Produkte erkennen die für die Anmeldedaten verfügbaren Modelle, nutzen den Anthropic Messages-Transport, aktualisieren Tokens von Claude Code, wenn möglich, und unterstützen validierte JSON- oder ZIP-Importe.

Muse Code verwendet die Geräteautorisierung von Meta. Unter **Providers → Muse Code** den Anmeldelink anfordern, den Gerätecode bei Meta bestätigen und anschließend **Save credential** wählen. Polaris verbindet sich direkt ohne CLI, Linux oder VPS. Modelle tragen `muse-code/`; als erweiterte Einstellung ist ein Anzeigename möglich. Tarif, Sitzungs-/Wochenkontingente, Rücksetz- und Beobachtungszeit werden nur angezeigt, wenn der Anbieter sie liefert. Fehlende Werte bedeuten nicht 100 % Restkapazität. Aktualisieren prüft die Berechtigung erneut und bezieht einen Inferenzschlüssel über die vorhandene Sitzung; ist diese ungültig, erneut anmelden.

Kiro unterstützt Browser-OAuth über Google/GitHub, AWS-Geräteanmeldung und API-Schlüssel. Erweiterte Felder richten sich nach der Methode: Laufzeitregion, AWS-Tokenregion/Start-URL oder Profil-ARN für API-Schlüssel.

Ollama-Verbindungen werden pro Endpunkt konfiguriert und können einen optionalen Bearer-API-Schlüssel für geschützte oder Cloud-Server enthalten. Polaris erkennt Modelle über `/api/tags` und leitet Inferenzen über `/api/chat`. Wenn Polaris in Docker läuft, bezieht sich `localhost` auf den Container selbst; verwenden Sie eine Host-Gateway-Adresse oder einen netzwerkweit erreichbaren Ollama-Endpunkt.

Credentials-Importe und Google Antigravity-Batch-Importe akzeptieren Archive bis zu 10 MB, maximal 500 Dateien, einzelne Anmeldedateien bis zu 2 MB und maximal 25 MB unkomprimierte Daten. Für Google AI Studio, OpenAI, Anthropic und Ollama gelten strengere Limits: 2 MB pro Datei, 200 JSON-Einträge und 5 MB unkomprimierte Daten.

**Credentials** (`/credentials`) gruppiert Konten und API-Schlüssel nach Anbieter. Das Verwaltungsdialogfeld zeigt Identität, Modelle, Status und unterstützte Aktionen. OAuth-Kontingente können pro Zeitfenster oder Modell gelten und Tarif-/Guthabendaten enthalten. API-Schlüssel liefern nicht automatisch E-Mail-, Tarif- oder Abrechnungsinformationen. Fehlende Daten bleiben als nicht verfügbar markiert.

**Download ZIP** exportiert Anmeldedaten; **Import ZIP** verarbeitet gemischte Anbieterarchive mit anbieterspezifischer Prüfung und Deduplizierung. Fehlerhafte Einträge werden einzeln gemeldet. Erfolgreicher Import oder Modellkatalog beweist keinen Inferenzzugang; **Test model** sendet eine echte, möglicherweise kostenpflichtige Anfrage. Archive enthalten Geheimnisse. Für eine vollständige unterstützte SQLite-Sicherung einschließlich Konfiguration den verschlüsselten Ablauf unter **Settings** verwenden.

Google Antigravity-Anmeldedaten verwenden das Format `google-antigravity-{account_fingerprint}.json`, wobei der Fingerprint aus der normalisierten E-Mail-Adresse abgeleitet wird, ohne diese preiszugeben. Google AI Studio verwendet `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth `grok-{account_fingerprint}.json`, SpaceXAI Console `xai-console-{key_fingerprint}.json`, Codex `openai-codex-{account_fingerprint}.json`, OpenAI Platform `openai-platform-{key_fingerprint}.json`, Claude Code `claude-code-{account_fingerprint}.json`, Claude Platform `claude-platform-{key_fingerprint}.json` und Ollama `ollama-{connection_fingerprint}.json`. Legacy-Dateien wie `provider_*.json` und `xai-grok-*.json` bleiben kompatibel und werden mit kanonischen Namen exportiert.

Bezeichnungen der Anmeldemodi (Credential mode names):

- `code_assist`: Standard-Anmeldedatenpool für Code Assist.
- `provider`: Anmeldedatenpool für Anbieter-Backends.

<a id="storage"></a>

## Speicherung

SQLite ist die empfohlene Standardspeicherung. Compose sichert `/app/backend/data` im Volume `polaris-data`; bei direktem Docker-Betrieb `/app/backend/data/creds` und `/app/backend/data/logs` dauerhaft etwa unter `/opt/polaris/creds` und `/opt/polaris/logs` einbinden.

PostgreSQL ist eine optionale Erweiterung; MongoDB wird für bestehende Installationen direkt unterstützt und benötigt kein Redis. Nur eines der beiden externen Backends konfigurieren. Ein Initialisierungsfehler stoppt den Start statt still auf SQLite zurückzufallen. Externe Speicherung erlaubt keine horizontale Skalierung: ein Worker und eine Replik bleiben vorgeschrieben. Die portable verschlüsselte Sicherung unterstützt nur SQLite; ein unterstützter Live-Wechsel zwischen Backends ist nicht enthalten.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[Speicherung](../storage.md)

Der Import von Anmeldedaten über Umgebungsvariablen ist über die Konsole verfügbar. Setzen Sie eine der folgenden Variablen auf einen rohen JSON-String oder nutzen Sie die entsprechende `_B64`-Variante für base64-codiertes JSON:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

Die Payload kann ein einzelnes Anmeldeobjekt, ein Array oder `{ "credentials": [...] }` sein.

<a id="development"></a>

## Entwicklung

Dieser Abschnitt richtet sich an Mitwirkende und die lokale Fehlersuche. Produktionsbereitstellungen sollten Docker mit persistenten Host-Volumes nutzen.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

Die [Qualitätsprüfungen](../quality-gates.md) unterscheiden Aufgaben-, Phasen- und Release-Prüfungen. Optionale Live-Prüfungen sind unter `python tools/quality_gate.py --list-suites` separat aufgeführt. Der versionierte [Kompatibilitätsvertrag](../compatibility.md) schützt SDK-/Verwaltungsrouten, Konfigurationsmigrationen, Datenschemata und Clientbeispiele.

Starten Sie den Dienst, nachdem alle Prüfungen erfolgreich bestanden wurden:

```bash
python backend/main.py
```

Die Produktions-Baseline ist Python 3.12, und CI verifiziert derzeit Python 3.12 und 3.14. Siehe [Beitragende Richtlinien](../../CONTRIBUTING.md) für den Pull-Request-Workflow und Review-Erwartungen.

<a id="deployment-notes"></a>

## Hinweise zur Bereitstellung

- Committen Sie niemals JSON-Dateien mit Anmeldedaten oder `.env`-Dateien.
- Verwenden Sie einen dedizierten `API_KEY` für Client-Integrationen und ein separates `PANEL_PASSWORD` für den Konsolenzugriff.
- Beschränken Sie den Zugriff auf persistente Anmelde-Volumes oder externe Datenbanken und aktivieren Sie Verschlüsselung im Ruhezustand (Encryption at rest); das Gateway muss Tokens der Anbieter im Klartext lesen können.
- Platzieren Sie Polaris hinter einem Reverse-Proxy mit TLS, wenn es außerhalb von localhost erreichbar ist.
- Konfigurieren Sie den Reverse-Proxy so, dass er `Host` beibehält und `X-Forwarded-Proto` weiterleitet; setzen Sie `PANEL_COOKIE_SECURE=true`, wenn HTTPS-Terminierung gewährleistet ist.
- Setzen Sie `TRUST_PROXY_HEADERS=true` nur, wenn der Dienst ausschließlich über einen vertrauenswürdigen Proxy erreichbar ist, der `X-Forwarded-For` und `X-Forwarded-Proto` überschreibt.
- Verwenden Sie `GET /health` für Liveness- und `GET /ready` für speicherbezogene Readiness-Prüfungen.
- Externe Telemetrie ist optional. Prometheus benötigt `PROMETHEUS_EXPORT_ENABLED` und ein starkes `METRICS_TOKEN`; OpenTelemetry exportiert nur Aggregate. Prompt- und Antwortinhalte werden nicht exportiert. Siehe [Betriebsbeobachtung](../observability.md).
- Das Docker-Image startet nur kurzzeitig mit Root-Rechten, um Dateiberechtigungen im gemounteten Verzeichnis zu korrigieren, und führt den Dienst dann als unprivilegierter Benutzer `gateway` aus.
- Setzen Sie `CORS_ORIGINS` auf explizite vertrauenswürdige Origins, wenn Browser-Clients Cross-Origin-Zugriff benötigen.
- Vor Updates oder Umzügen den authentifizierten [verschlüsselten Sicherungsablauf](../backup-and-restore.md) für SQLite nutzen. Archiv und Passphrase außerhalb von `polaris-data` aufbewahren.
- Die Docker-Image-Veröffentlichung nutzt die Repository-Secrets `DOCKERHUB_USERNAME` und `DOCKERHUB_TOKEN` für Docker Hub sowie das integrierte `GITHUB_TOKEN` für GitHub Packages unter `ghcr.io/nguywnben/polaris`. Setzen Sie die optionale Variable `IMAGE_NAME` nur bei Veröffentlichung unter einem benutzerdefinierten Image-Namen.
- Behalten Sie `WORKERS=1` und ein einzelnes Anwendungsreplikat für die 1.x-Serie bei; externer Speicher ersetzt keine verteilte Koordination.
- Verwenden Sie die kanonischen Verwaltungsrouten `/api/credentials`. Die Beta-Aliase `/api/creds` wurden in Version 1.0.0 entfernt.
- Befolgen Sie die Anleitung [Upgrade auf 1.0](../upgrading-to-1.0.md), bevor Sie eine Beta-Bereitstellung migrieren.
- Befolgen Sie den [Update-Leitfaden](../updating.md), wenn Sie eine Instanz aktualisieren oder auf eine frühere Version zurücksetzen.
- Arbeiten Sie die gepflegte [Release-Checkliste](../release-checklist.md) ab, bevor Sie ein Image taggen oder freigeben.
- Stimmen Sie Log-Aufbewahrung und Anmelderotation auf Ihre Nutzungslimits ab.
- Tauschen Sie Anmeldedaten unverzüglich aus, falls ein Secret-Scanner einen geleakten Schlüssel meldet.
- Das Render-Blueprint nutzt einen kostenpflichtigen Dienst mit persistenter Festplatte. Kostenlose Render-Dienste nutzen flüchtige Dateisysteme und eignen sich nur für kurzzeitige Tests.

<a id="community-and-project-health"></a>

## Community und Projektzustand

- Lesen Sie [Beitragen](../../CONTRIBUTING.md), bevor Sie einen Pull Request öffnen.
- Melden Sie Sicherheitslücken über das vertrauliche Verfahren in der [Sicherheitsrichtlinie](../../SECURITY.md).
- Konsultieren Sie das [Änderungsprotokoll](../../CHANGELOG.md) für versionsspezifische Änderungen.
- Befolgen Sie den [Verhaltenskodex](../../CODE_OF_CONDUCT.md) in allen Projektbereichen.

<a id="acknowledgements-inspirations"></a>

## Danksagungen & Inspirationen

Polaris baut auf der Arbeit der Open-Source-Community für KI-Routing, Telemetrie und Gateways auf. Wir bedanken uns herzlich bei den Entwicklern und Betreuern folgender Projekte:

| Projekt | Beschreibung | Sterne |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Inspiration für Multi-Provider-Schlüsselverwaltung und webbasierte API-Aggregation | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Wegweisende Multi-Format-Proxy- und Protokollübersetzungsschicht für KI-Coding-CLIs | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Maßstabsetzender LLM-Proxy mit Lastverteilung und Fallback-Routing | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Ultraschnelle KI-Gateway-Architektur, Routing-Strategien und ausfallsichere Fallback-Muster | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Open-Source-LLM-Engineering-Plattform, Tracing, Observability und Metrikerfassung | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## Lizenz

Polaris ist unter der [MIT-Lizenz](../../LICENSE) lizenziert.
