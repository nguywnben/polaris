<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Router IA universale e gateway multi-provider unificato per strumenti di sviluppo IA</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">Provider supportati</a> • <a href="#core-capabilities">Funzionalità principali</a> • <a href="#deployment">Distribuzione</a> • <a href="#sdk-surfaces">Guida rapida: Integrazione SDK</a> • <a href="#architecture">Architettura</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <b>Italiano</b> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

Questo README è disponibile in 15 lingue con lo stesso ambito funzionale. Le guide collegate mantengono la lingua originale.

Un router IA universale per strumenti di programmazione. Polaris offre failover automatico intelligente (smart auto-fallback), pulizia del contesto sensibile ai token, visibilità sull'utilizzo e conversione fluida dei formati, consentendo ad agenti locali, assistenti IDE e script di automazione di sfruttare la capacità di LLM gratuiti e a pagamento tramite un'unica interfaccia API stabile.

> Polaris supporta l'hosting autonomo per una persona o un gruppo fidato: un worker e una replica. Docker Compose, proprietario locale, SQLite, routing e interfacce SDK documentate costituiscono il nucleo. PostgreSQL, OIDC, proxy inverso e telemetria esterna sono opzionali; MongoDB è mantenuto per compatibilità. Kubernetes e coordinamento multi-replica non sono supportati. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Perché scegliere Polaris

I moderni flussi di lavoro di sviluppo combinano spesso molteplici client e provider: strumenti compatibili con OpenAI, SDK nativi Gemini, agenti in stile Anthropic, credenziali basate su Google e route di modelli sperimentali. Polaris si posiziona tra tali client e i backend dei modelli, consentendo a ciascuno strumento di comunicare nel formato nativo mentre il gateway gestisce routing, tentativi di ripetizione (retry), pulizia delle richieste e normalizzazione delle risposte.

<a id="core-capabilities"></a>

## Funzionalità principali

- Failover con prenotazioni per richiesta, rotazione equa, pause e rispetto delle quote esaurite.
- Riduzione della cronologia preservando istruzioni di sistema, strumenti e turni recenti.
- Conversione tra OpenAI Chat Completions/Responses, Gemini e Anthropic Messages, anche in streaming.
- Credenziali OAuth e chiavi API con verifica e deduplicazione per provider.
- Catalogo modelli per credenziale, coerente con i permessi dell'account.
- Rilevamento delle route non disponibili e ripristino dalla pagina Models.
- SSE, pseudo-streaming e tentativi limitati per risposte troncate.
- Routing bilanciato, prioritario, ponderato, a latenza minima o costo minimo.
- Chiavi virtuali con budget giornalieri/mensili, RPM/TPM, scadenza e modelli consentiti.
- Costi stimati in USD per chiamata, aggregati nella dashboard e in Prometheus.
- Protezione opzionale contro prompt injection, parole vietate e dati personali.
- Cache opzionale per risposte deterministiche con corrispondenza esatta.
- Metriche Prometheus, esportazione Langfuse opzionale e monitoraggio dell'utilizzo.
- Console per credenziali, log, configurazione, utilizzo e versioni.

<a id="console-preview"></a>

## Anteprima della console

Le schermate mostrano dati fittizi di una demo offline isolata.

### Dashboard

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — Dashboard" />
</picture>

### Credenziali

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — Anteprima della console" />
</picture>

<a id="supported-providers"></a>

## Provider supportati

Il catalogo include 23 provider. Modelli e funzionalità disponibili dipendono dai permessi di ciascuna credenziale.

| Provider | Connessione | Servizio / ambito |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | Chiave API | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | Chiave API | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (codice dispositivo) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | Chiave API | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | Chiave API | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Endpoint; chiave API opzionale | Locale / hosting autonomo |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | Chiave API | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | Token API + ID account | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | Chiave API | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | Chiave API | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | Chiave API; ID organizzazione opzionale | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | Chiave API / servizio | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | Chiave API | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | OAuth nel browser / dispositivo AWS / chiave API | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (dispositivo Meta) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | Chiave API | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | Chiave API | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | Chiave API | Inferenza ospitata NVIDIA |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | Chiave API + piano Zen/Go | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | Chiave API | Poolside API |

I client utilizzano le [interfacce SDK](#sdk-surfaces) comuni. Conversione, streaming e failover dipendono dal modello; opzioni incompatibili vengono rifiutate esplicitamente. Configurare le connessioni per provider o credenziale in **Providers**. Muse Code e Meta Model API hanno credenziali e namespace separati.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## Architettura

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | Integrazioni IDE
        |
        v
Polaris
  autenticazione -> conversione formato -> pulizia token -> routing -> failover -> streaming
        |
        v
provider adapters
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

L'API pubblica mantiene la sua stabilità mentre gli adapter specifici per provider evolvono continuamente all'interno di Polaris.

<a id="repository-structure"></a>

## Struttura del repository

```text
backend/       Radice di composizione FastAPI, core di routing, adapter, persistenza e test
frontend/      Interfaccia console web, stili, script e asset grafici dei provider
deploy/        Definizioni container, manifest di piattaforma e script del sistema operativo
docs/          Note di architettura e documentazione di manutenzione del progetto
.github/       Flussi CI, automazione delle dipendenze e modelli per i contributi
```

Consultare [Architettura](../architecture.md) per i confini dei moduli, il flusso delle richieste, la gestione dello stato e i vincoli attuali di rilascio.

<a id="deployment"></a>

## Distribuzione

Docker Compose è il percorso principale su una macchina con un worker. Seguire [installazione](../installation.md) e [matrice di supporto](../installation.md#support-matrix).

Il profilo base non richiede servizi esterni e conserva i dati in `polaris-data`. Il modello è destinato a `1.0.0`. Installare solo tag e immagini Polaris pubblicati della stessa versione; per codice non ancora pubblicato, creare un’immagine locale separata seguendo la [checklist di rilascio](../releases/1.0.0-preparation.md). Consultare [aggiornamento e rollback](../updating.md); le opzioni avanzate si attivano tramite `deploy/compose.advanced.yml`.

Consultare [identificatori](../migrations/polaris.md) e [risoluzione dei problemi](../troubleshooting.md). Script nativi, `docker run`, Render e Zeabur sono percorsi di compatibilità senza le stesse garanzie di verifica. Immagini pubblicate per `linux/amd64`; `linux/arm64` è sospeso.

### Sviluppo o diagnosi locale:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

Su Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Aprire la console; la configurazione iniziale è la stessa di Docker:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## Configurazione

Priorità: ambiente, configurazione salvata, valori predefiniti. La [referenza generata](../reference/configuration.md) descrive tipi, gruppi, responsabili e applicazione immediata, al riavvio o solo tramite ambiente. Valori errati bloccano l'avvio; possibili refusi `POLARIS_*` producono avvisi.

| Variabile d'ambiente | Valore predefinito | Descrizione |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Indirizzo di ascolto (bind address). |
| `PORT` | `4283` | Porta HTTP. |
| `HOST_PORT` | `4283` | Porta host utilizzata esclusivamente da Docker Compose. |
| `WORKERS` | `1` | Supportato un solo worker. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Supportato solo `standalone`. |
| `POLARIS_REPLICA_COUNT` | `1` | Supportata una sola replica. |
| `CORS_ORIGINS` | vuoto | Elenco separato da virgole di origini browser autorizzate a chiamate API cross-origin. Lasciare vuoto per l'uso della console sulla stessa origine. |
| `CORS_ORIGIN_REGEX` | vuoto | Espressione regolare opzionale per origini browser dinamiche. |
| `API_KEY` | generato automaticamente | Chiave API client con prefisso `sk-polaris-`. |
| `PANEL_PASSWORD` | vuoto fino alla configurazione | Password per l'accesso al pannello di controllo web. |
| `SETUP_TOKEN` | vuoto | Token di configurazione remota univoco di almeno 24 caratteri; mai generato o registrato. Non richiesto su localhost diretto. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Durata della sessione della console web in secondi. |
| `PANEL_COOKIE_SECURE` | automatico | Impostare su `true` per forzare cookie solo su HTTPS. Lasciare vuoto per rilevamento automatico tramite `X-Forwarded-Proto`. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Finestra del limitatore di frequenza di login in secondi. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Tentativi massimi di login falliti consentiti per client nella finestra di limitazione. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Numero massimo di indirizzi client tracciati in memoria dal limitatore di login. |
| `MAX_REQUEST_BODY_MB` | `64` | Dimensione massima del corpo della richiesta HTTP in MiB. Le richieste che superano il limite restituiranno strutture di errore conformi al rispettivo protocollo. |
| `TRUST_PROXY_HEADERS` | `false` | Accetta gli header di inoltro client/protocollo solo da un reverse proxy affidabile che li sovrascrive. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Directory di archiviazione delle credenziali. In Docker, rendere persistente `/app/backend/data/creds` tramite volumi host. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Endpoint backend di Code Assist. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Endpoint backend di Google Antigravity. |
| `PROXY` | vuoto | Proxy HTTP, HTTPS o SOCKS opzionale. |
| `RETRY_429_ENABLED` | `true` | Abilita tentativi limitati per rate limit ed errori temporanei upstream. Nome storico mantenuto per compatibilità. |
| `RETRY_429_MAX_RETRIES` | `5` | Numero massimo di tentativi per errori temporanei dell'upstream. |
| `RETRY_429_INTERVAL` | `1` | Ritardo base tra i tentativi temporanei in secondi. |
| `AUTO_DISABLE` | `false` | Disabilita automaticamente le credenziali dopo errori gravi configurati. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Elenco separato da virgole dei codici di stato di errore grave. |
| `ROUTING_STRATEGY` | `balanced` | Strategia: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | vuoto | Provider preferito per la strategia `priority`, ad esempio `google_antigravity` o `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Timeout per la risposta di inferenza del provider (da 5 a 900 secondi). |
| `RESPONSE_CACHE_ENABLED` | `false` | Cache in memoria per risposte deterministiche senza streaming, temperatura 0. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Durata cache in secondi. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Numero massimo di risposte in cache. |
| `GUARDRAILS_ENABLED` | `false` | Attivare protezioni prima della chiamata. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Mascherare email, carte e chiavi API nel testo in uscita. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Rifiutare prompt injection con HTTP 400. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | vuoto | Parole vietate separate da virgole, senza distinzione maiuscole/minuscole. |
| `PRICING_SYNC_ENABLED` | `true` | Aggiornare prezzi LiteLLM in background; conservare l'ultima copia valida offline. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Intervallo prezzi: 1–168 ore. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Tentativi massimi di continuazione per la funzione di streaming anti-troncamento. |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Comprime la cronologia di conversazioni troppo ampie prima dell'inoltro al provider. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Soglia stimata di token in input per attivare la compressione del contesto. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Obiettivo stimato di token in input dopo la compressione. Deve essere inferiore alla soglia di attivazione. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Numero minimo di turni recenti dell'utente da preservare durante la compressione. |
| `COMPATIBILITY_MODE` | `false` | Converte i messaggi di sistema per client/modelli che non li supportano nativamente. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Restituisce il processo di ragionamento del modello (reasoning) quando disponibile. |
| `MONGODB_URI` | vuoto | Storage MongoDB di compatibilità. |
| `POSTGRESQL_URI` | vuoto | Storage PostgreSQL opzionale. |
| `CODE_ASSIST_CLIENT_ID` | client desktop incluso | Override opzionale per il Client ID OAuth di Code Assist. |
| `CODE_ASSIST_CLIENT_SECRET` | client desktop incluso | Override opzionale per il Client Secret OAuth di Code Assist. |
| `ANTIGRAVITY_CLIENT_ID` | client desktop incluso | Override opzionale per il Client ID OAuth di Google Antigravity. Gestibile anche dalla pagina Provider. |
| `ANTIGRAVITY_CLIENT_SECRET` | client desktop incluso | Override opzionale per il Client Secret OAuth di Google Antigravity. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Override opzionale per l'endpoint Generative Language API di Google AI Studio. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Override opzionale per l'endpoint API SpaceXAI Console per credenziali API key. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Override opzionale per l'endpoint di abbonamento Grok Build OAuth. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Override opzionale per l'emittente OAuth di Grok Build. La console accetta solo host HTTPS del dominio `x.ai`. |
| `XAI_CLIENT_ID` | client pubblico incluso | Override opzionale per il Client ID OAuth PKCE di Grok Build. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Override opzionale per l'User-Agent HTTP condiviso per richieste Grok Build OAuth e API SpaceXAI Console. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Override opzionale per l'endpoint API OpenAI Platform. Gestibile anche dalla pagina Provider. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Override opzionale per l'endpoint di inferenza e catalogo modelli account di Codex. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Override opzionale per l'endpoint di verifica limiti account Codex. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Override opzionale per il servizio di autorizzazione dispositivi di Codex. |
| `CODEX_CLIENT_ID` | client pubblico incluso | Override opzionale per il Client ID OAuth dispositivi di Codex. |
| `CODEX_USER_AGENT` | compatibile con Codex CLI | Override opzionale per l'User-Agent delle richieste Codex. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Endpoint Messages esclusivo di Claude Code. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Override opzionale per l'endpoint di autorizzazione PKCE di Claude Code. Solo host Anthropic e Claude. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Override opzionale per l'endpoint token di Claude Code. Solo host Anthropic e Claude. |
| `CLAUDE_CLIENT_ID` | client pubblico incluso | Override opzionale per il Client ID OAuth PKCE di Claude Code. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | User-Agent esclusivo di Claude Code. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Endpoint separato Claude Platform in Providers. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | User-Agent indipendente di Claude Platform. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Override opzionale per l'User-Agent a livello di protocollo Google Antigravity. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Override opzionale per il campo userAgent a livello di payload Google Antigravity. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Attivare `GET /metrics` autenticato. |
| `METRICS_TOKEN` | vuoto | Token Bearer di almeno 32 byte UTF-8 richiesto per Prometheus. |
| `OTEL_EXPORT_ENABLED` | `false` | Attivare esportazione aggregata OTLP/HTTP senza contenuto. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | vuoto | Collector HTTPS, senza credenziali nell'URL. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Intervallo di esportazione: 15–300 secondi. |
| `LANGFUSE_PUBLIC_KEY` | vuoto | Abilitare Langfuse insieme alla chiave segreta. |
| `LANGFUSE_SECRET_KEY` | vuoto | Chiave segreta Langfuse per le tracce. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Endpoint di ricezione Langfuse. |
| `LOG_LEVEL` | `info` | Livello di dettaglio dei log (log level). |
| `LOG_MAX_MB` | `10` | Dimensione massima in MB del file di log attivo prima della rotazione. |
| `LOG_BACKUP_COUNT` | `3` | Numero di file di log archiviati dopo la rotazione da conservare. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | Percorso del file di log. In Docker, rendere persistente `/app/backend/data/logs` tramite volumi host. |

### Controllo della compressione

La politica globale AI Quality prevale. Una chiave può ereditarla o disabilitare la compressione tramite `PATCH /api/virtual-keys/{key_id}/quality-policy`, indicando la revisione corrente; `inherit` rimuove il vincolo. Una richiesta autenticata può inviare `x-polaris-compression: off`; assenza o `inherit` applicano la politica globale/della chiave. Non è possibile riattivare o rendere più aggressiva una compressione vietata. Viene eliminato solo un prefisso sicuro: se struttura o stima sono incerte, la richiesta resta invariata. I token sono stimati.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## Guida rapida: Integrazione SDK

Polaris è progettato seguendo il comportamento standard degli URL degli SDK ufficiali Python. Configurare ciascun client esattamente come indicato di seguito; il gateway non richiede prefissi di percorso ridondanti o non standard.

I seguenti esempi utilizzano il modello virtuale `polaris`. Configurare preventivamente l'ordine di priorità di fallback modello-provider nella pagina Modelli, oppure sostituirlo con l'ID di un modello specifico.

### OpenAI Python SDK

Utilizzare `/v1` come Base URL per OpenAI. L'SDK aggiungerà automaticamente `/chat/completions`.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Spiega questo repository di codice in un singolo paragrafo."}],
)
```

Lo stesso client può invocare direttamente l'API OpenAI Responses:

```python
response = client.responses.create(
    model="polaris",
    instructions="Rispondi in modo conciso e chiaro.",
    input="Spiega questo repository di codice in un singolo paragrafo.",
)

print(response.output_text)
```

La compatibilità con Responses supporta testo, input di immagini, Function Tools non-streaming e streaming di testo via SSE. Gli strumenti integrati ospitati da OpenAI, la cronologia persistente delle risposte e le chiamate di funzione in streaming saranno rifiutati esplicitamente, poiché Polaris non esegue, memorizza né ignora silenziosamente tali funzionalità proprietarie di OpenAI.

### Anthropic Python SDK

Utilizzare l'origine del gateway come Base URL per Anthropic. L'SDK aggiungerà automaticamente `/v1/messages`.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Scrivi un messaggio di commit breve."}],
)
```

### Google GenAI Python SDK

Utilizzare l'origine del gateway come Base URL per Google GenAI. L'SDK aggiungerà automaticamente il percorso predefinito del modello, come `/v1beta/models/{model}:generateContent`.

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
    contents="Scrivi una breve funzione in Python.",
    config=types.GenerateContentConfig(
        system_instruction="Sei un assistente utile e competente.",
    ),
)
```

### Endpoint supportati

Polaris fornisce percorsi compatibili con gli SDK standard senza la necessità di prefissi di namespace dedicati:

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

Errori di autenticazione, convalida delle richieste, routing, fallimenti upstream ed errori precedenti all'avvio dello streaming utilizzano le strutture di errore native di ciascuna interfaccia SDK. Tutte le risposte HTTP includono l'header `X-Request-ID`; i client possono inviare un identificatore per tracciare il flusso delle richieste. Le risposte soggette a rate limit o temporaneamente non disponibili conservano l'header `Retry-After` fornito dall'upstream.

<a id="model-features"></a>

## Gestione avanzata dei modelli

La pagina Modelli costruisce il modello virtuale `polaris` aggregando i modelli rilevati dalle credenziali dei provider attivi. È sufficiente ordinare le priorità dei modelli una sola volta e richiamare `polaris` da qualsiasi SDK supportato. Polaris bilancerà il carico tra le credenziali integre che supportano il modello primario e passerà automaticamente al modello successivo qualora il primo risulti non disponibile. Gli ID specifici dei modelli fisici rimangono accessibili per i client che necessitano di selezioni deterministiche. Il salvataggio di un elenco vuoto disattiva `polaris` senza intaccare le credenziali dei provider.

Il rilevamento dei modelli è specifico per ciascun provider: i modelli condivisi possono essere serviti da più provider, mentre i modelli proprietari vengono instradati solo verso credenziali compatibili. Ogni credenziale verificata mantiene il proprio catalogo di provider e il router privilegia il supporto dichiarato esplicitamente dalla credenziale rispetto a deduzioni generiche. L'aggiornamento del catalogo verifica la disponibilità effettiva presso il provider; le opzioni non più disponibili rimangono visibili nella configurazione fino al loro ripristino o alla rimozione manuale.

Quando un upstream restituisce un errore `404` per uno specifico modello fisico, Polaris registra un percorso non disponibile per tale credenziale e modello, anziché disattivare l'intero provider. Quel percorso viene escluso immediatamente ed è visibile sotto **Percorsi modello non disponibili** fino alla cancellazione o alla nuova verifica della credenziale. In questo modo si evita che i limiti di abbonamento o le restrizioni geografiche di un account influiscano sugli altri account dello stesso provider. Se nessuna credenziale abilitata dichiara o deduce il supporto per il modello richiesto, il gateway restituirà un errore esplicito di assenza di credenziali compatibili anziché inviare la richiesta a un provider casuale.

Polaris riconosce prefissi e suffissi di funzionalità nei nomi dei modelli:

- `fake-streaming/{model}` o il prefisso di pseudo-streaming configurato per i client che richiedono obbligatoriamente il formato SSE.
- `streaming-anti-truncation/{model}` o il prefisso di anti-troncamento configurato per il ripristino automatico dello streaming in testi lunghi.
- Suffissi di profondità di ragionamento (come `-high`, `-medium`, `-low`, `-minimal`, `-max`) per i modelli compatibili della famiglia Gemini.
- Suffissi di ricerca come `-search` per i modelli che supportano il grounding con Google Search.

Gli adapter dei provider normalizzano tali identificatori di funzionalità prima di inoltrare la richiesta all'upstream.

<a id="usage-and-cost-visibility"></a>

## Trasparenza su utilizzo e costi

Ogni tentativo, ripetizione e failover conta separatamente; le tracce mantengono il risultato finale della richiesta logica. Si registrano esito, credenziale, token dichiarati di input/output/cache/ragionamento, risparmio stimato e costo USD. Utilizzo assente non significa zero misurato. I periodi seguono il fuso del browser; il giorno copre 00:00–23:00. I prezzi LiteLLM si aggiornano all'avvio e ogni 24 ore per impostazione predefinita: l'ultima copia valida viene conservata atomicamente e un errore non blocca l'inferenza. `model_pricing.json` nella directory credenziali ha priorità; prezzi per milione di token. Aggregati in dashboard, `/api/virtual-keys` e `/metrics`. Fatturazione e tokenizer del provider restano autorevoli.

Le chiavi virtuali supportano budget giornalieri/mensili, finestre mobili RPM/TPM, scadenza e modelli glob. Si memorizzano hash SHA-256; il segreto appare solo alla creazione.

<a id="credential-workflow"></a>

## Flusso di lavoro per le credenziali

1. Avviare Polaris.
2. Accedere a `http://IP_DEL_VOSTRO_SERVER:4283` su VPS, oppure `http://127.0.0.1:4283` in locale.
3. Completare i controlli e creare la password del proprietario. Prima della configurazione remota impostare `SETUP_TOKEN` univoco di almeno 24 caratteri oppure `PANEL_PASSWORD`. Il token non viene generato né scritto nei log.
4. Aggiungere account, chiavi API o connessioni Ollama dalla pagina Provider.
5. Verificare la validità delle credenziali e monitorare cooldown ed errori nel pannello. **Credentials** (`/credentials`).
6. Indirizzare i propri strumenti di sviluppo verso una delle interfacce API sopra descritte.

Quando si aggiungono credenziali Google Antigravity, Google reindirizzerà il browser a `http://localhost:4283/callback` dopo l'autenticazione. In locale, Polaris mostrerà direttamente la pagina di conferma OAuth. Su un VPS, poiché `localhost` fa riferimento alla macchina locale dell'utente, la pagina potrebbe non caricarsi; copiare l'intero URL dalla barra degli indirizzi del browser, tornare alla pagina Provider, incollarlo nel campo `Callback URL` e premere `Salva credenziale`.

Google AI Studio utilizza l'autenticazione tramite chiave API anziché OAuth. Aggiungere una chiave dalla pagina Provider; Polaris ne verificherà la validità rispetto al catalogo modelli di Google, la salverà come credenziale del provider e vi instraderà le richieste compatibili di Gemini o Gemma. Il router intelligente effettua il failover automatico tra AI Studio e Google Antigravity per i modelli Gemini condivisi, mantenendo i modelli proprietari sulle rispettive credenziali.

L'importazione massiva di Google AI Studio accetta file JSON e archivi ZIP contenenti file JSON. I documenti JSON possono contenere una singola chiave, un array `api_keys` o una lista di oggetti chiave:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

L’importazione dei file avviene offline: Polaris controlla la struttura JSON/ZIP, salva le nuove chiavi come `unverified` e ignora quelle duplicate o già presenti senza contattare Google. Gli elenchi di modelli importati non sono considerati verificati. Gli errori di formato vengono segnalati senza esporre le chiavi. Eseguire poi la verifica/rilevazione dei modelli della credenziale; **Test model** verifica separatamente l’accesso all’inferenza e può consumare quota o comportare addebiti.

Grok Build supporta credenziali OAuth PKCE, mentre SpaceXAI Console supporta chiavi API. Le chiavi SpaceXAI Console vengono convalidate rispetto al catalogo modelli dell’API SpaceXAI Console prima di essere memorizzate. Per Grok Build OAuth, Polaris genera un link di autorizzazione; completata l'autorizzazione, copiare il codice mostrato nella pagina di Grok Build e incollarlo nel form. I token di accesso vengono rinnovati automaticamente in presenza di un refresh token, ed entrambi i tipi di credenziali espongono solo i modelli dichiarati nei rispettivi cataloghi correnti. La pagina Credentials consente di consultare l'utilizzo mensile dei crediti e l'utilizzo settimanale (quando fornito da xAI) per gli account Grok Build OAuth. Questa visualizzazione di fatturazione a livello di account non è disponibile per le API key di SpaceXAI Console.

Codex adotta il flusso di autorizzazione dispositivi di OpenAI. Generare un codice dispositivo dalla pagina Provider, aprire l'URL di verifica mostrato, digitare il codice, completare il login e tornare per verificare l'autorizzazione. Polaris memorizza il catalogo modelli associato all'account restituito da Codex, rinnova i token di accesso OAuth quando necessario e inoltra le richieste compatibili tramite il trasporto Codex Responses. OpenAI Platform utilizza l'autenticazione tramite API Key; le chiavi sono convalidate tramite il catalogo modelli dell'account prima di essere salvate in Credentials. Entrambi i prodotti supportano importazioni JSON e ZIP con convalida e deduplicazione specifiche per provider.

Claude Code adotta il flusso OAuth PKCE di Anthropic. Generare il link di autorizzazione, completare il flusso e incollare il codice di autorizzazione ottenuto nella pagina Provider. Claude Platform accetta chiavi API Anthropic. Entrambi i prodotti rilevano i modelli supportati per ciascuna credenziale, utilizzano il trasporto Anthropic Messages, rinnovano i token di accesso di Claude Code quando possibile e supportano importazioni convalidate da file JSON o ZIP.

Muse Code usa l'autorizzazione dispositivo Meta. In **Providers → Muse Code**, ottenere il collegamento, approvare il codice su Meta e tornare a **Save credential**. Connessione diretta, senza CLI, Linux o VPS; namespace `muse-code/` e nome visualizzato opzionale. Piano, quote di sessione/settimana, ripristini e data di osservazione appaiono solo se forniti. Dati mancanti non significano 100% residuo. L'aggiornamento verifica l'abbonamento e ottiene la chiave d'inferenza usando la sessione corrente; se non è valida, accedere nuovamente.

Kiro supporta OAuth Google/GitHub nel browser, dispositivo AWS e chiave API. Impostazioni avanzate specifiche del metodo: regione runtime, regione token/URL iniziale AWS o ARN del profilo API.

Le connessioni Ollama sono configurate per singolo endpoint e possono includere una Bearer API Key facoltativa per istanze protette o cloud. Polaris rileva i modelli disponibili tramite `/api/tags` e instrada l'inferenza tramite `/api/chat`. Quando Polaris è in esecuzione all'interno di Docker, `localhost` fa riferimento al container stesso; utilizzare l'indirizzo host-gateway o un endpoint Ollama accessibile via rete.

L'importazione completa del Credentials e l'importazione massiva di Google Antigravity accettano archivi fino a 10 MB, per un massimo di 500 file, fino a 2 MB per singolo file di credenziale e fino a 25 MB totali non compressi. Le importazioni dedicate per Google AI Studio, OpenAI, Anthropic e Ollama adottano limiti più restrittivi: 2 MB per file importato, 200 voci JSON e 5 MB di dati non compressi.

**Credentials** (`/credentials`) raggruppa account e chiavi per provider. Il dialogo mostra identità, modelli, stato e azioni disponibili. OAuth può restituire piano, crediti e quote per finestra o modello. Le chiavi API non forniscono automaticamente email, piano o fatturazione; le informazioni mancanti restano non disponibili.

**Download ZIP** esporta le credenziali; **Import ZIP** convalida e deduplica più provider, segnalando errori per voce. Catalogo o importazione non provano l'accesso all'inferenza: **Test model** invia richieste reali che possono consumare quota o denaro. Gli archivi contengono segreti. Per SQLite e configurazione completi usare il backup cifrato di **Settings**.

Le credenziali Google Antigravity utilizzano il formato `google-antigravity-{account_fingerprint}.json`, dove il fingerprint è derivato dall'email dell'account normalizzata senza esporre l'email in chiaro. Google AI Studio utilizza `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth utilizza `grok-{account_fingerprint}.json`, SpaceXAI Console utilizza `xai-console-{key_fingerprint}.json`, Codex utilizza `openai-codex-{account_fingerprint}.json`, OpenAI Platform utilizza `openai-platform-{key_fingerprint}.json`, Claude Code utilizza `claude-code-{account_fingerprint}.json`, Claude Platform utilizza `claude-platform-{key_fingerprint}.json` e le connessioni Ollama utilizzano `ollama-{connection_fingerprint}.json`. Le vecchie credenziali conformi a `provider_*.json` e `xai-grok-*.json` rimangono retrocompatibili e vengono esportate con i nomi normalizzati.

Nomi delle modalità credenziali (Credential mode names):

- `code_assist`: credenziali Code Assist standard.
- `provider`: credenziali backend per provider generici.

<a id="storage"></a>

## Archiviazione dei dati

SQLite è consigliato. Compose conserva `/app/backend/data` nel volume `polaris-data`; con Docker diretto montare `/app/backend/data/creds` e `/app/backend/data/logs` in directory persistenti come `/opt/polaris/creds` e `/opt/polaris/logs`.

PostgreSQL è opzionale; MongoDB è mantenuto per compatibilità e funziona senza Redis. Configurarne uno solo. Errori di inizializzazione interrompono l'avvio senza ripiego silenzioso su SQLite. Restano necessari un worker e una replica: nessuno scaling orizzontale. Backup portabile cifrato solo per SQLite; nessuna migrazione live fra backend supportata.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[Archiviazione dei dati](../storage.md)

È supportata l'importazione di credenziali tramite variabili d'ambiente direttamente dalla console. Impostare una delle seguenti variabili con una stringa JSON non elaborata o utilizzare la variante con suffisso `_B64` codificata in Base64:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

Il payload può essere un singolo oggetto credenziale, un array o `{ "credentials": [...] }`.

<a id="development"></a>

## Guida allo sviluppo

Questa sezione è destinata a contributori e al debug locale. Le installazioni di produzione devono utilizzare Docker con volumi host persistenti.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

Le [verifiche di qualità](../quality-gates.md) distinguono attività, fase e release. `python tools/quality_gate.py --list-suites` elenca anche le prove esterne opzionali. Il [contratto di compatibilità](../compatibility.md) protegge route SDK/gestione, migrazioni, schemi ed esempi.

Avviare il servizio una volta superati tutti i controlli:

```bash
python backend/main.py
```

La piattaforma di riferimento per la produzione è Python 3.12, e la CI convalida sia Python 3.12 sia 3.14. Consultare [Contribuire](../../CONTRIBUTING.md) per le linee guida sulle pull request e le aspettative di revisione del codice.

<a id="deployment-notes"></a>

## Note di distribuzione

- Non committare mai file JSON contenenti credenziali né file `.env`.
- Utilizzare una `API_KEY` dedicata per le integrazioni client e una `PANEL_PASSWORD` distinta per l'accesso alla console.
- Limitare i permessi di accesso al volume persistente delle credenziali o al database esterno e attivare la cifratura a riposo (encryption at rest) sulla piattaforma; il router deve poter decifrare e leggere i token dei provider.
- Posizionare Polaris dietro un reverse proxy con TLS attivo quando esposto al di fuori di localhost.
- Configurare il reverse proxy in modo da preservare l'header `Host` e inoltrare `X-Forwarded-Proto`; impostare `PANEL_COOKIE_SECURE=true` una volta garantita la terminazione HTTPS.
- Impostare `TRUST_PROXY_HEADERS=true` unicamente se il servizio è accessibile esclusivamente tramite un proxy fidato che sovrascrive `X-Forwarded-For` e `X-Forwarded-Proto`.
- Utilizzare `GET /health` per i controlli di attività (liveness probe) e `GET /ready` per i controlli di disponibilità con verifica dello storage (readiness probe).
- Telemetria esterna opzionale: Prometheus richiede `PROMETHEUS_EXPORT_ENABLED` e un `METRICS_TOKEN` robusto. OpenTelemetry esporta solo aggregati, mai prompt o risposte. Vedere [osservabilità](../observability.md).
- L'immagine Docker opera come root solo temporaneamente all'avvio per correggere i permessi della cartella dati montata, passando poi all'utente non privilegiato `gateway`.
- Configurare `CORS_ORIGINS` con le origini attendibili esplicite qualora i client web necessitino di accesso cross-origin.
- Prima di aggiornare o spostare SQLite usare il [backup cifrato autenticato](../backup-and-restore.md); conservare archivio e passphrase fuori da `polaris-data`.
- Il flusso di pubblicazione delle immagini Docker utilizza i secret di repository `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN` per Docker Hub, e il `GITHUB_TOKEN` integrato per GitHub Packages su `ghcr.io/nguywnben/polaris`. Impostare la variabile opzionale `IMAGE_NAME` solo se si pubblica con un nome immagine Docker Hub personalizzato.
- Mantenere `WORKERS=1` e una singola replica dell'applicazione per l'intera serie 1.x; lo storage esterno non sostituisce il coordinamento distribuito.
- Utilizzare i percorsi canonici di gestione `/api/credentials`. Le route con alias `/api/creds` della fase beta sono state rimosse a partire dalla 1.0.0.
- Consultare la guida [Aggiornamento a 1.0](../upgrading-to-1.0.md) prima di migrare una distribuzione beta.
- Seguire la [guida all'aggiornamento](../updating.md) durante l'aggiornamento di un'istanza attiva o il ripristino di una versione precedente.
- Seguire la [checklist di rilascio](../release-checklist.md) prima di applicare tag o pubblicare immagini.
- Definire politiche di conservazione dei log e di rotazione delle credenziali adeguate alle proprie quote di utilizzo.
- Revocare e rinnovare immediatamente le credenziali qualora scanner di sicurezza o piattaforme cloud rilevino token esposti.
- Il template Render Blueprint impiega un servizio a pagamento con disco persistente. I piani gratuiti di Render utilizzano file system effimeri e sono idonei solo a test temporanei.

<a id="community-and-project-health"></a>

## Community e stato del progetto

- Consultare [Contribuire](../../CONTRIBUTING.md) prima di aprire una pull request.
- Segnalare vulnerabilità di sicurezza tramite il canale privato descritto nell'[Informativa sulla sicurezza](../../SECURITY.md).
- Consultare il [Registro delle modifiche](../../CHANGELOG.md) per l'elenco delle novità di ciascuna versione.
- Rispettare il [Codice di condotta](../../CODE_OF_CONDUCT.md) in tutti gli spazi del progetto.

<a id="acknowledgements-inspirations"></a>

## Ringraziamenti e ispirazione

Polaris poggia sul lavoro della comunità open source nell'ambito di AI routing, telemetria e gateway. Esprimiamo la nostra più profonda gratitudine ai creatori e manutentori dei seguenti progetti:

| Progetto | Descrizione | Stelle |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Ispirazione per la gestione chiavi multi-provider e l'aggregazione API via console web | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Pioniere nel livello di proxy multi-protocollo e conversione di formati per CLI di coding con IA | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Punto di riferimento nei proxy LLM unificati, bilanciamento del carico e routing con tolleranza d'errore | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Architettura AI gateway ad altissime prestazioni, strategie di routing e modalità di failover avanzate | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Piattaforma open source di LLM engineering, tracciamento delle chiamate, osservabilità e metriche | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## Licenza

Polaris è distribuito sotto [Licenza MIT](../../LICENSE).
