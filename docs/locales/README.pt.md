<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Roteador universal de IA e gateway multiprovedor unificado para ferramentas de código com IA</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">Provedores suportados</a> • <a href="#core-capabilities">Recursos principais</a> • <a href="#deployment">Implantação</a> • <a href="#sdk-surfaces">Interfaces SDK</a> • <a href="#architecture">Arquitetura</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <b>Português</b> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

Este README está disponível em 15 idiomas com o mesmo escopo funcional. Os guias vinculados mantêm o idioma original.

Um roteador de IA universal para ferramentas de código. O Polaris oferece failover automático inteligente (smart auto-fallback), limpeza de contexto com reconhecimento de tokens, visibilidade de uso e tradução contínua de formatos para que agentes locais, assistentes de IDE e scripts de automação possam aproveitar capacidades LLM gratuitas e pagas através de uma única interface estável de API.

> Hospedagem própria para uma pessoa ou equipe confiável, com um worker e uma réplica. Docker Compose, proprietário local, SQLite, roteamento e interfaces SDK documentadas formam o núcleo. PostgreSQL, OIDC, proxy reverso e telemetria externa são opcionais; MongoDB é mantido por compatibilidade. Kubernetes e coordenação entre réplicas não são suportados. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Por que o Polaris

Fluxos de trabalho de desenvolvimento modernos costumam misturar múltiplos clientes e provedores: ferramentas compatíveis com OpenAI, SDKs nativos do Gemini, agentes no estilo Anthropic, credenciais respaldadas pelo Google e rotas de modelos experimentais. O Polaris atua entre esses clientes e os backends dos modelos, permitindo que cada ferramenta continue se comunicando no formato que já compreende, enquanto o gateway gerencia roteamento, novas tentativas (retries), limpeza de solicitações e normalização de respostas.

<a id="core-capabilities"></a>

## Recursos principais

- Failover com reservas por solicitação, rotação justa, pausas e respeito às cotas esgotadas.
- Limpeza do histórico preservando instruções do sistema, ferramentas e turnos recentes.
- Conversão entre OpenAI Chat Completions/Responses, Gemini e Anthropic Messages, incluindo streaming.
- Credenciais OAuth e chaves API com verificação e deduplicação por provedor.
- Catálogo por credencial, respeitando permissões da conta.
- Registro de rotas indisponíveis e recuperação pela página Models.
- SSE, pseudo-streaming e tentativas limitadas para respostas truncadas.
- Roteamento balanceado, prioritário, ponderado, por menor latência ou menor custo.
- Chaves virtuais com orçamento diário/mensal, RPM/TPM, expiração e modelos permitidos.
- Custo estimado em USD por chamada com agregados no painel e Prometheus.
- Proteções opcionais contra injeção, palavras bloqueadas e dados pessoais.
- Cache opcional de respostas determinísticas por correspondência exata.
- Prometheus, exportação opcional Langfuse e acompanhamento de uso.
- Console para credenciais, logs, configuração, uso e versões.

<a id="console-preview"></a>

## Prévia do Console

As capturas usam dados fictícios de uma demonstração offline isolada.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — Painel" width="1600" height="1100" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — Prévia do Console" width="1600" height="1100" />
</picture>

<a id="supported-providers"></a>

## Provedores suportados

O catálogo contém 23 provedores. Modelos e recursos disponíveis dependem das permissões de cada credencial.

| Provedor | Conexão | Serviço / escopo |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | Chave API | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | Chave API | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (código de dispositivo) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | Chave API | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | Chave API | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Endpoint; chave API opcional | Local / hospedagem própria |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | Chave API | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | Token API + ID da conta | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | Chave API | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | Chave API | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | Chave API; ID da organização opcional | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | Chave API / serviço | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | Chave API | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | OAuth no navegador / dispositivo AWS / chave API | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (dispositivo Meta) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | Chave API | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | Chave API | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | Chave API | Inferência hospedada NVIDIA |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | Chave API + plano Zen/Go | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | Chave API | Poolside API |

Os clientes usam as [interfaces SDK](#sdk-surfaces) comuns. Conversão, streaming e failover dependem do modelo; opções incompatíveis são rejeitadas explicitamente. Configure por provedor ou credencial em **Providers**. Muse Code e Meta Model API têm credenciais e namespaces separados.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## Arquitetura

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | Integrações de IDE
        |
        v
Polaris
  autenticação -> tradução de formatos -> limpeza consciente de tokens -> roteamento -> failover -> streaming
        |
        v
provider adapters
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

A API pública permanece estável enquanto os adaptadores específicos de cada provedor evoluem sob o Polaris.

<a id="repository-structure"></a>

## Estrutura do Repositório

```text
backend/       Raiz de composição FastAPI, núcleo de roteamento, tradutores, armazenamento e testes
frontend/      Marcação do console administrativo, estilos, scripts e recursos visuais dos provedores
deploy/        Definições de contêineres, manifestos de plataformas e scripts do sistema operacional
docs/          Notas de arquitetura e documentação de manutenção do projeto
.github/       CI, automação de dependências e modelos de contribuição
```

Consulte [Arquitetura](../architecture.md) para saber mais sobre limites de módulos, fluxo de requisições, controle de estado e restrições da versão atual.

<a id="deployment"></a>

## Implantação

Docker Compose é a opção principal para uma máquina e um worker. Siga a [instalação](../installation.md) e a [matriz de suporte](../installation.md#support-matrix).

O perfil básico dispensa serviços externos e mantém dados em `polaris-data`. O modelo tem como alvo `1.0.0`. Instale apenas tags e imagens publicadas do Polaris da mesma versão; para código ainda não publicado, crie uma imagem local separada conforme a [lista de publicação](../releases/1.0.0-preparation.md). Siga [atualização e reversão](../updating.md); recursos avançados são opcionais via `deploy/compose.advanced.yml`.

Consulte [identificadores](../migrations/polaris.md) e [solução de problemas](../troubleshooting.md). Scripts nativos, `docker run`, Render e Zeabur são caminhos de compatibilidade sem as mesmas verificações. Imagens para `linux/amd64`; publicação `linux/arm64` suspensa.

### Desenvolvimento ou diagnóstico local:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

No Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Abra o console; a configuração inicial é igual à do Docker:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## Configuração

Prioridade: ambiente, configuração salva, padrões. A [referência gerada](../reference/configuration.md) detalha tipos, grupos, responsáveis e aplicação imediata, após reinício ou somente por ambiente. Valores inválidos impedem iniciar; possíveis erros de nome `POLARIS_*` geram avisos.

| Variável | Padrão | Finalidade |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Endereço de escuta (bind address). |
| `PORT` | `4283` | Porta HTTP. |
| `HOST_PORT` | `4283` | Porta do lado do host usada apenas pelo Docker Compose. |
| `WORKERS` | `1` | Somente um worker suportado. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Somente `standalone` suportado. |
| `POLARIS_REPLICA_COUNT` | `1` | Somente uma réplica suportada. |
| `CORS_ORIGINS` | vazio | Lista separada por vírgulas de origens de navegador autorizadas para chamadas de API cross-origin. Deixe vazio para uso no mesmo domínio (same-origin). |
| `CORS_ORIGIN_REGEX` | vazio | Expressão regular opcional para origens dinâmicas gerenciadas no navegador. |
| `API_KEY` | gerado automaticamente | Chave API cliente com prefixo `sk-polaris-`. |
| `PANEL_PASSWORD` | vazio até configurar | Senha para o painel de controle web. |
| `SETUP_TOKEN` | vazio | Token remoto único de ao menos 24 caracteres, não gerado nem registrado. Dispensado no localhost direto. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Duração da sessão do console web em segundos. |
| `PANEL_COOKIE_SECURE` | automático | Defina como `true` para exigir cookies seguros apenas via HTTPS. Deixe vazio para detectar HTTPS via `X-Forwarded-Proto`. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Janela de limitação de taxa de login em segundos. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Tentativas de login falhas permitidas por cliente dentro da janela de taxa. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Limite de endereços de clientes retidos pelo limitador de login em memória. |
| `MAX_REQUEST_BODY_MB` | `64` | Tamanho máximo do corpo da requisição HTTP em MiB. Requisições de SDK que excederem o limite retornam o envelope de erro nativo do protocolo. |
| `TRUST_PROXY_HEADERS` | `false` | Aceitar headers de encaminhamento de cliente/protocolo apenas de um proxy reverso confiável que os sobrescreva. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Diretório de armazenamento de credenciais. No Docker, mantenha `/app/backend/data/creds` persistido com volume host. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Endpoint backend do Code Assist. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Endpoint backend do Google Antigravity. |
| `PROXY` | vazio | Proxy HTTP, HTTPS ou SOCKS opcional. |
| `RETRY_429_ENABLED` | `true` | Ativa tentativas limitadas para limites de taxa e falhas temporárias no upstream. Nome legado mantido por compatibilidade. |
| `RETRY_429_MAX_RETRIES` | `5` | Número máximo de novas tentativas para falhas transitórias no upstream. |
| `RETRY_429_INTERVAL` | `1` | Intervalo base entre tentativas transitórias em segundos. |
| `AUTO_DISABLE` | `false` | Desativa credenciais após falhas graves configuradas. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Lista de códigos de status de falha grave separados por vírgula. |
| `ROUTING_STRATEGY` | `balanced` | Estratégia: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | vazio | Provedor preferido pela estratégia `priority`, como `google_antigravity` ou `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Tempo limite de inferência do provedor, limitado entre 5 e 900 segundos. |
| `RESPONSE_CACHE_ENABLED` | `false` | Cache em memória de respostas determinísticas sem streaming, temperatura 0. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Validade do cache em segundos. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Máximo de respostas em cache. |
| `GUARDRAILS_ENABLED` | `false` | Ativar proteções antes da chamada. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Mascarar emails, cartões e chaves API no texto enviado. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Rejeitar injeção de prompts com HTTP 400. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | vazio | Palavras bloqueadas separadas por vírgulas, sem distinguir maiúsculas. |
| `PRICING_SYNC_ENABLED` | `true` | Atualizar preços LiteLLM em segundo plano; manter última cópia válida offline. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Intervalo de preços: 1–168 horas. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Tentativas máximas de continuação para o streaming anti-truncamento. |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Comprime histórico de conversa excessivo antes de rotear ao provedor. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Limite estimado de tokens de entrada para acionar a compressão. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Meta de tokens de entrada após a compressão. Deve ser menor que o limite. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Número mínimo de turnos recentes do usuário mantidos durante a compressão. |
| `COMPATIBILITY_MODE` | `false` | Converte mensagens de sistema para clientes/modelos que não as suportam. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Retorna campos de raciocínio (reasoning) do modelo quando disponíveis. |
| `MONGODB_URI` | vazio | Armazenamento MongoDB de compatibilidade. |
| `POSTGRESQL_URI` | vazio | Armazenamento PostgreSQL opcional. |
| `CODE_ASSIST_CLIENT_ID` | cliente desktop incluído | Substituição opcional do Client ID OAuth do Code Assist. |
| `CODE_ASSIST_CLIENT_SECRET` | cliente desktop incluído | Substituição opcional do Client Secret OAuth do Code Assist. |
| `ANTIGRAVITY_CLIENT_ID` | cliente desktop incluído | Substituição opcional do Client ID OAuth do Google Antigravity. Gerenciável na página Providers. |
| `ANTIGRAVITY_CLIENT_SECRET` | cliente desktop incluído | Substituição opcional do Client Secret OAuth do Google Antigravity. Configurável via env ou na página Providers. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Substituição opcional do endpoint Generative Language API do Google AI Studio. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Substituição opcional do endpoint SpaceXAI Console API para chaves de API. Gerenciável na página Providers. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Substituição opcional do endpoint de assinatura OAuth do Grok Build. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Substituição opcional do emissor OAuth do Grok Build. Somente hosts HTTPS em `x.ai` são aceitos. |
| `XAI_CLIENT_ID` | cliente público incluído | Substituição opcional do Client ID OAuth PKCE do Grok Build. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Substituição opcional do HTTP User-Agent compartilhado para requisições Grok Build OAuth e SpaceXAI Console API. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Substituição opcional do endpoint de API da OpenAI Platform. Gerenciável na página Providers. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Substituição opcional do endpoint de inferência e catálogo de modelos de conta do Codex. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Substituição opcional do endpoint de limites de taxa de conta do Codex. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Substituição opcional do serviço de autorização de dispositivos do Codex. |
| `CODEX_CLIENT_ID` | cliente público incluído | Substituição opcional do Client ID OAuth de dispositivo do Codex. |
| `CODEX_USER_AGENT` | compatível com Codex CLI | Substituição opcional do User-Agent para requisições do Codex. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Endpoint Messages exclusivo Claude Code. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Substituição opcional do endpoint de autorização PKCE do Claude Code. Apenas hosts Anthropic e Claude são aceitos. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Substituição opcional do endpoint de token do Claude Code. Apenas hosts Anthropic e Claude são aceitos. |
| `CLAUDE_CLIENT_ID` | cliente público incluído | Substituição opcional do Client ID OAuth PKCE do Claude Code. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | User-Agent exclusivo Claude Code. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Endpoint separado Claude Platform em Providers. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | User-Agent independente Claude Platform. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Substituição opcional do User-Agent de protocolo do Google Antigravity. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Substituição opcional do campo userAgent em nível de payload do Google Antigravity. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Ativar `GET /metrics` autenticado. |
| `METRICS_TOKEN` | vazio | Token Bearer de pelo menos 32 bytes UTF-8 para Prometheus. |
| `OTEL_EXPORT_ENABLED` | `false` | Ativar exportação agregada OTLP/HTTP sem conteúdo. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | vazio | Collector HTTPS, sem credenciais na URL. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Intervalo de exportação: 15–300 segundos. |
| `LANGFUSE_PUBLIC_KEY` | vazio | Ativar Langfuse junto com a chave secreta. |
| `LANGFUSE_SECRET_KEY` | vazio | Chave secreta Langfuse para traces. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Endpoint de ingestão Langfuse. |
| `LOG_LEVEL` | `info` | Nível de detalhamento dos logs. |
| `LOG_MAX_MB` | `10` | Tamanho máximo do arquivo de log ativo antes da rotação. |
| `LOG_BACKUP_COUNT` | `3` | Quantidade de arquivos de log rotacionados a serem mantidos. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | Destino do arquivo de log. No Docker, mantenha `/app/backend/data/logs` persistido com volume host. |

### Controle de compressão

A política global AI Quality prevalece. Uma chave pode herdar ou desativar compressão via `PATCH /api/virtual-keys/{key_id}/quality-policy`, com a revisão atual; `inherit` remove a restrição. A solicitação autenticada pode enviar `x-polaris-compression: off`; ausência ou `inherit` aplicam a política global/da chave. Não é possível reativar compressão proibida ou torná-la mais agressiva. Só se remove um prefixo seguro; estrutura ou estimativa incerta mantém a solicitação intacta. Tokens são estimados.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## Interfaces SDK

O Polaris é projetado respeitando o comportamento padrão de URL dos SDKs oficiais em Python. Configure cada cliente exatamente como demonstrado abaixo; o gateway não requer prefixos duplicados ou fora do padrão.

Os exemplos usam o modelo virtual `polaris`. Configure a ordem de prioridade de fallback na página Models previamente ou substitua por um ID de modelo concreto.

### OpenAI Python SDK

Use `/v1` como base URL para OpenAI. O SDK anexa `/chat/completions` automaticamente.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Explique este repositório em um parágrafo."}],
)
```

O mesmo cliente também pode utilizar a OpenAI Responses API:

```python
response = client.responses.create(
    model="polaris",
    instructions="Seja conciso.",
    input="Explique este repositório em um parágrafo.",
)

print(response.output_text)
```

A compatibilidade com Responses oferece suporte a entradas de texto e imagem, ferramentas de função sem streaming e streaming de texto via SSE. Ferramentas internas hospedadas pela OpenAI, histórico persistido de respostas e chamadas de ferramentas em streaming são rejeitadas explicitamente porque o Polaris não executa, persiste ou descarta silenciosamente esses comportamentos proprietários da OpenAI.

### Anthropic Python SDK

Use a origem do gateway como URL base para a Anthropic. O SDK anexa `/v1/messages` automaticamente.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Escreva uma mensagem de commit concisa."}],
)
```

### Google GenAI Python SDK

Use a origem do gateway como URL base para Google GenAI. O SDK anexa a rota padrão do modelo, como `/v1beta/models/{model}:generateContent`.

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
    contents="Escreva uma função simples em Python.",
    config=types.GenerateContentConfig(
        system_instruction="Você é um assistente prestativo.",
    ),
)
```

### Rotas Suportadas

O Polaris expõe rotas compatíveis com SDKs sem a necessidade de prefixos de produtos:

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

Falhas de autenticação, validação de requisições, roteamento, problemas no upstream e erros pré-streaming utilizam o envelope nativo de erros da interface SDK selecionada. Todas as respostas HTTP incluem o cabeçalho `X-Request-ID`; clientes podem enviar um identificador seguro para correlação ponta a ponta. Respostas com limitação de taxa ou indisponibilidade temporária preservam o cabeçalho `Retry-After` quando informado pelo upstream.

<a id="model-features"></a>

## Recursos dos Modelos

A página Models cria o modelo virtual `polaris` a partir dos modelos descobertos em credenciais habilitadas dos provedores. Organize seus membros em ordem de prioridade uma única vez e utilize `polaris` a partir de qualquer SDK suportado. O Polaris realiza balanceamento entre credenciais saudáveis que suportam o modelo principal e avança na ordem configurada quando o modelo estiver indisponível. Identificadores de modelos concretos permanecem disponíveis para clientes que requerem seleção determinística. Salvar uma seleção vazia desativa `polaris` sem impactar as credenciais dos provedores.

A descoberta de modelos é orientada ao provedor: um modelo compartilhado pode ser atendido por múltiplos provedores, enquanto modelos específicos usam apenas credenciais compatíveis. Cada credencial verificada armazena seu próprio catálogo e o roteador prioriza o suporte formalmente declarado da credencial sobre suposições genéricas. Atualizar o catálogo checa a disponibilidade atual do provedor; seleções indisponíveis permanecem na configuração até serem restauradas ou removidas.

Quando um upstream retorna erro `404` para um modelo específico, o Polaris registra uma rota indisponível para essa credencial e modelo em vez de desativar o provedor por inteiro. A rota é evitada temporariamente de imediato e segue listada sob **Unavailable Model Routes** até ser removida ou a credencial revalidada. Isso evita que planos ou restrições regionais de uma conta afetem outras contas no mesmo provedor. Se nenhuma credencial habilitada suportar o modelo solicitado, o gateway retorna um erro claro de ausência de credencial compatível em vez de enviar a requisição a um provedor aleatório.

O Polaris reconhece prefixos e sufixos especiais nos nomes de modelos:

- `fake-streaming/{model}` ou o prefixo de pseudo-streaming configurado para clientes que exigem resposta em SSE.
- `streaming-anti-truncation/{model}` ou o prefixo anti-truncamento configurado para recuperação automática em streaming de respostas longas.
- Sufixos de raciocínio (thinking) como `-high`, `-medium`, `-low`, `-minimal` e `-max` para modelos compatíveis da família Gemini.
- Sufixos de pesquisa como `-search` para modelos com suporte a dados ancorados no Google Search (grounding).

Os adaptadores dos provedores normalizam essas variações antes de encaminhar a requisição ao serviço de origem.

<a id="usage-and-cost-visibility"></a>

## Uso e Transparência de Custos

Cada tentativa, repetição e failover conta separadamente; as traces mantêm o resultado final da solicitação lógica. Registram-se resultado, credencial, tokens informados de entrada/saída/cache/raciocínio, economia estimada e custo USD. Uso ausente não é zero medido. Períodos usam o fuso do navegador; o dia cobre 00:00–23:00. Preços LiteLLM atualizam na inicialização e a cada 24 horas por padrão, preservando atomicamente a última cópia válida; falhas não bloqueiam inferência. `model_pricing.json` no diretório de credenciais tem prioridade; valores por milhão de tokens. Agregados no painel, `/api/virtual-keys` e `/metrics`; cobrança e tokenizer do provedor são a referência.

Chaves virtuais oferecem orçamento diário/mensal, janelas móveis RPM/TPM, expiração e padrões glob. Armazenam-se hashes SHA-256; o segredo aparece só na criação.

<a id="credential-workflow"></a>

## Fluxo de Trabalho com Credenciais

1. Inicie o Polaris.
2. Abra `http://IP_DO_SEU_SERVIDOR:4283` na VPS ou `http://127.0.0.1:4283` no ambiente de desenvolvimento local.
3. Conclua as verificações e crie a senha do proprietário. Antes da configuração remota defina `SETUP_TOKEN` único de pelo menos 24 caracteres ou `PANEL_PASSWORD`. O token não é gerado nem registrado automaticamente.
4. Adicione uma conta, chave de API ou conexão Ollama através da página Providers.
5. Valide as credenciais e acompanhe os estados de cooldown e erros no painel. **Credentials** (`/credentials`).
6. Aponte sua ferramenta de desenvolvimento para uma das interfaces de API descritas acima.

Ao cadastrar credenciais do Google Antigravity, o Google redireciona o navegador para `http://localhost:4283/callback` após o login. Em um computador local, o Polaris exibe a tela de sucesso de autenticação OAuth. Em uma VPS, o endereço `localhost` aponta para o dispositivo do navegador local, o que pode impedir o carregamento da página; copie a URL completa da barra de endereços do navegador, acesse a página Providers, cole em `Callback URL` e clique em `Save credential`.

O Google AI Studio adota autenticação via chave de API em vez de OAuth. Cadastre uma chave na página Providers; o Polaris validará sua conformidade com o catálogo do Google, salvará o registro como credencial e roteará requisições Gemini ou Gemma compatíveis. O roteador inteligente alterna entre AI Studio e Google Antigravity para modelos Gemini compartilhados, mantendo modelos específicos nas credenciais correspondentes.

A importação em lote do Google AI Studio aceita arquivos JSON e arquivos ZIP contendo JSON. O documento JSON pode conter uma única chave, uma lista `api_keys` ou uma lista de objetos de chave:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

A importação de arquivos é offline: o Polaris verifica a estrutura JSON/ZIP, salva novas chaves como `unverified` e ignora chaves duplicadas ou existentes sem contatar o Google. As listas de modelos importadas não são consideradas verificadas. Erros de formato são informados sem expor as chaves. Depois, execute explicitamente a verificação/descoberta de modelos da credencial; **Test model** verifica o acesso à inferência separadamente e pode consumir cota ou gerar cobrança.

O Grok Build suporta autenticação OAuth PKCE, enquanto o SpaceXAI Console aceita chaves de API. Chaves do SpaceXAI Console são validadas contra o catálogo da API SpaceXAI Console antes de serem salvas. Para o Grok Build OAuth, o gateway gera um link de autorização; ao concluir, copie o código exibido na página do Grok Build e cole no formulário do console. Tokens de acesso são renovados automaticamente quando um refresh token estiver disponível, e ambos os tipos de credencial expõem somente os modelos declarados em seus catálogos. A página Credentials permite consultar o consumo mensal e semanal (se fornecido pela xAI) para contas Grok Build OAuth. Esse detalhamento em nível de conta não se aplica a chaves de API do SpaceXAI Console.

O Codex utiliza o fluxo de autorização de dispositivos da OpenAI. Gere o código de dispositivo na página Providers, acesse a URL indicada, insira o código, conclua a autenticação e retorne para checar a autorização. O Polaris persiste o catálogo de modelos retornado pelo Codex, renova tokens OAuth conforme necessário e envia requisições compatíveis via transporte Codex Responses. A OpenAI Platform utiliza autenticação por chave de API; as chaves são validadas no catálogo da conta antes de serem salvas em Credentials. Ambos os produtos suportam importação de arquivos JSON e ZIP com validação e desduplicação específicas por provedor.

O Claude Code emprega o fluxo OAuth PKCE da Anthropic. Gere o link de autorização, conclua a autenticação e insira o código retornado na página Providers. A Claude Platform aceita chaves de API da Anthropic. Ambos identificam os modelos acessíveis para cada credencial, utilizam o transporte Anthropic Messages, renovam tokens do Claude Code quando aplicável e suportam importação validada via JSON ou ZIP.

Muse Code usa autorização de dispositivo Meta. Em **Providers → Muse Code**, obtenha o link, aprove o código na Meta e volte a **Save credential**. Conexão direta, sem CLI, Linux ou VPS; prefixo `muse-code/` e nome de exibição opcional. Plano, cotas de sessão/semana, redefinições e horário da observação aparecem somente quando fornecidos. Informação ausente não significa 100% restante. Atualizar verifica a assinatura e obtém a chave de inferência pela sessão atual; entre novamente se ela não for válida.

Kiro aceita OAuth Google/GitHub no navegador, dispositivo AWS e chave API. Opções avançadas variam: região de execução, região do token/URL inicial AWS ou ARN de perfil da chave API.

Conexões Ollama são configuradas individualmente por endpoint e aceitam chave bearer opcional para servidores protegidos ou em nuvem. O gateway lista modelos via `/api/tags` e roteia inferências via `/api/chat`. Ao executar o Polaris no Docker, `localhost` refere-se ao contêiner; utilize o endereço do host-gateway ou outro endpoint acessível na rede.

As importações do Credentials e do Google Antigravity suportam arquivos compactados de até 10 MB, no máximo 500 arquivos, arquivos individuais de até 2 MB e até 25 MB de dados descompactados. As importações de Google AI Studio, OpenAI, Anthropic e Ollama seguem limites mais restritos: 2 MB por arquivo importado, 200 entradas JSON e 5 MB de dados descompactados.

**Credentials** (`/credentials`) agrupa contas e chaves por provedor. O modal apresenta identidade, modelos, estado e ações disponíveis. OAuth pode fornecer plano, créditos e cotas por janela ou modelo. Chaves API não fornecem automaticamente email, plano ou faturamento; informações ausentes ficam indisponíveis.

**Download ZIP** exporta credenciais; **Import ZIP** valida e deduplica vários provedores, com erros por entrada. Importar ou descobrir catálogo não comprova acesso à inferência: **Test model** faz uma chamada real, podendo consumir cota ou gerar custo. Arquivos contêm segredos. Use o backup criptografado de **Settings** para SQLite e configuração completos.

Credenciais do Google Antigravity utilizam o padrão `google-antigravity-{account_fingerprint}.json`, onde o fingerprint é gerado com base no e-mail normalizado sem expô-lo. O Google AI Studio adota `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth adota `grok-{account_fingerprint}.json`, SpaceXAI Console adota `xai-console-{key_fingerprint}.json`, Codex adota `openai-codex-{account_fingerprint}.json`, OpenAI Platform adota `openai-platform-{key_fingerprint}.json`, Claude Code adota `claude-code-{account_fingerprint}.json`, Claude Platform adota `claude-platform-{key_fingerprint}.json` e conexões Ollama adotam `ollama-{connection_fingerprint}.json`. Credenciais legadas nos formatos `provider_*.json` e `xai-grok-*.json` continuam suportadas e são salvas com a nomenclatura canônica.

Nomes dos modos de credencial (Credential mode names):

- `code_assist`: credenciais padrão do Code Assist.
- `provider`: credenciais de backend de provedores.

<a id="storage"></a>

## Armazenamento

SQLite é recomendado. Compose persiste `/app/backend/data` em `polaris-data`; no Docker direto monte `/app/backend/data/creds` e `/app/backend/data/logs` em diretórios duráveis, como `/opt/polaris/creds` e `/opt/polaris/logs`.

PostgreSQL é opcional; MongoDB permanece por compatibilidade, sem Redis. Configure apenas um. Erros de inicialização interrompem o serviço sem fallback silencioso para SQLite. Continue com um worker e uma réplica: não há escala horizontal. Backup portátil criptografado somente para SQLite; migração ao vivo entre backends não é suportada.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[Armazenamento](../storage.md)

A importação de credenciais via ambiente pode ser acionada pelo console. Atribua o JSON bruto a uma das variáveis abaixo ou utilize o sufixo `_B64` para conteúdo codificado em base64:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

O payload pode conter um único objeto de credencial, uma lista de objetos ou a estrutura `{ "credentials": [...] }`.

<a id="development"></a>

## Desenvolvimento

Esta seção é destinada a contribuidores e testes locais. Ambientes de produção devem priorizar o Docker com volumes persistentes.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

As [verificações de qualidade](../quality-gates.md) separam tarefa, fase e lançamento. `python tools/quality_gate.py --list-suites` lista também testes externos opcionais. O [contrato de compatibilidade](../compatibility.md) protege rotas SDK/gestão, migrações, esquemas e exemplos.

Inicie o serviço após a validação bem-sucedida de todas as etapas:

```bash
python backend/main.py
```

A base oficial de produção é o Python 3.12, com pipelines de CI validando compilações em Python 3.12 e 3.14. Consulte o guia de [Contribuição](../../CONTRIBUTING.md) para detalhes sobre fluxo de pull requests e diretrizes de revisão.

<a id="deployment-notes"></a>

## Notas de Implantação

- Nunca versione arquivos JSON com credenciais ou arquivos `.env`.
- Use uma `API_KEY` dedicada para integrações e uma `PANEL_PASSWORD` distinta para a área administrativa.
- Restrinja o acesso ao volume de credenciais ou banco de dados externo e ative criptografia em repouso (encryption at rest); o gateway precisa ler os tokens em texto puro.
- Posicione o Polaris atrás de um reverse proxy com TLS ativo quando acessível fora do ambiente localhost.
- Configure o proxy para manter o header `Host` e repassar `X-Forwarded-Proto`; ative `PANEL_COOKIE_SECURE=true` ao operar com terminação HTTPS.
- Só habilite `TRUST_PROXY_HEADERS=true` se o serviço estiver estritamente atrás de um proxy confiável que reescreva `X-Forwarded-For` e `X-Forwarded-Proto`.
- Use `GET /health` para checagem de integridade (liveness) e `GET /ready` para checagem de prontidão com armazenamento (readiness).
- Telemetria externa opcional: Prometheus exige `PROMETHEUS_EXPORT_ENABLED` e `METRICS_TOKEN` forte; OpenTelemetry exporta somente agregados, nunca prompts ou respostas. Veja [observabilidade](../observability.md).
- A imagem Docker inicia com privilégios de root apenas para ajustar permissões no volume montado, transferindo a execução ao usuário não privilegiado `gateway`.
- Defina `CORS_ORIGINS` com origens confiáveis caso clientes de navegador precisem de acesso cross-origin.
- Antes de atualizar ou mover SQLite, use o [backup criptografado autenticado](../backup-and-restore.md). Guarde arquivo e senha fora de `polaris-data`.
- O pipeline de publicação de imagens Docker utiliza os secrets `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN` para o Docker Hub, além do `GITHUB_TOKEN` para o GitHub Packages em `ghcr.io/nguywnben/polaris`. Utilize a variável opcional `IMAGE_NAME` apenas para imagens personalizadas no Docker Hub.
- Mantenha `WORKERS=1` e uma única réplica para toda a série 1.x; armazenamento externo não substitui mecanismos de coordenação distribuída.
- Utilize as rotas canônicas de gerenciamento `/api/credentials`. Os aliases beta `/api/creds` foram removidos na versão 1.0.0.
- Consulte o guia [Migrando para a versão 1.0](../upgrading-to-1.0.md) antes de atualizar instâncias beta.
- Siga as instruções de [Atualização](../updating.md) para atualizar uma instância em produção ou reverter versões.
- Siga o [checklist de lançamento](../release-checklist.md) mantido antes de gerar tags ou publicar imagens.
- Alinhe o período de retenção de logs e rotação de credenciais com as cotas contratadas junto aos provedores.
- Revogue e atualize credenciais caso detectores automáticos de segurança apontem vazamento de segredos.
- O Blueprint da Render exige um serviço pago com disco persistente. Serviços gratuitos utilizam armazenamento temporário e destinam-se apenas a testes breves.

<a id="community-and-project-health"></a>

## Comunidade e Saúde do Projeto

- Consulte o guia de [Contribuição](../../CONTRIBUTING.md) antes de submeter um pull request.
- Comunique vulnerabilidades de segurança de maneira privada pelo processo da [Política de Segurança](../../SECURITY.md).
- Acompanhe o [Histórico de Alterações](../../CHANGELOG.md) para detalhes de mudanças em cada versão.
- Respeite o [Código de Conduta](../../CODE_OF_CONDUCT.md) em todos os canais oficiais do projeto.

<a id="acknowledgements-inspirations"></a>

## Agradecimentos e Inspirações

O Polaris baseia-se nas inovações da comunidade open-source de roteamento de IA, telemetria e gateways. Agradecemos profundamente aos idealizadores e mantenedores dos projetos:

| Projeto | Descrição | Estrelas |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Referência em agregação web de APIs e gestão centralizada de chaves multiprovedor | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Pioneiro na camada de tradução e roteamento de protocolos entre múltiplos formatos para ferramentas CLI de IA | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Grande referência em proxy LLM unificado, balanceamento de carga e estratégias de failover | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Arquitetura ultra veloz para gateways de IA com suporte a estratégias flexíveis de roteamento | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Plataforma open-source completa para engenharia de LLMs, rastreabilidade e observabilidade | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## Licença

O Polaris é distribuído sob a licença [MIT](../../LICENSE).
