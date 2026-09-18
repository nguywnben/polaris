<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Routeur d'IA universel et passerelle multi-fournisseurs unifiée pour outils de développement IA</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">Fournisseurs pris en charge</a> • <a href="#core-capabilities">Fonctionnalités principales</a> • <a href="#deployment">Déploiement</a> • <a href="#sdk-surfaces">Surfaces SDK</a> • <a href="#architecture">Architecture</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <b>Français</b> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

Ce README est disponible en 15 langues avec le même périmètre fonctionnel. Les guides détaillés liés conservent leur langue d’origine.

Un routeur d'IA universel pour les outils de développement. Polaris fournit un basculement automatique intelligent (smart auto-fallback), un nettoyage de contexte sensible aux tokens, une visibilité d'utilisation et une traduction fluide de formats afin que les agents locaux, assistants d'IDE et scripts d'automatisation puissent exploiter la capacité des LLM gratuits et payants via une interface d'API stable unique.

> Polaris prend en charge l’auto-hébergement par une personne ou une équipe de confiance avec un worker et une réplique. Docker Compose, accès propriétaire local, SQLite, routage et interfaces SDK documentées constituent le socle. PostgreSQL, OIDC, proxy inverse et télémétrie externe sont optionnels ; MongoDB relève de la compatibilité. Le fonctionnement coordonné à plusieurs répliques et Kubernetes sont hors périmètre. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Pourquoi Polaris

Les flux de travail de développement modernes associent fréquemment plusieurs clients et fournisseurs : outils compatibles OpenAI, SDK natifs Gemini, agents au style Anthropic, identifiants adossés à Google et routes de modèles expérimentales. Polaris s'intercale entre ces clients et les backends de modèles afin que chaque outil puisse continuer à utiliser son format natif tandis que la passerelle gère le routage, les nouvelles tentatives (retries), le nettoyage des requêtes et la normalisation des réponses.

<a id="core-capabilities"></a>

## Fonctionnalités principales

- Repli automatique avec réservation par requête, rotation équitable, délais de récupération et prise en compte des quotas.
- Nettoyage des historiques trop longs préservant instructions système, outils et échanges récents.
- Conversion entre OpenAI Chat Completions/Responses, Gemini et Anthropic Messages, y compris en streaming.
- Gestion des comptes OAuth et clés API : validation, état et déduplication par fournisseur.
- Catalogue de modèles propre à chaque identifiant pour respecter les droits du compte.
- Mémorisation des routes indisponibles par identifiant et restauration depuis Models.
- SSE, pseudo-streaming et reprises limitées des réponses tronquées.
- Routage équilibré, prioritaire, pondéré, à latence minimale ou au coût minimal.
- Clés API virtuelles avec budgets quotidiens/mensuels, RPM/TPM, expiration et modèles autorisés.
- Coût estimé en USD par appel, agrégé dans le tableau de bord et Prometheus.
- Protections optionnelles contre les injections, mots interdits et données personnelles.
- Cache optionnel des réponses déterministes correspondant exactement à la requête.
- Prometheus, export Langfuse optionnel et suivi intégré de l’utilisation.
- Console de gestion des identifiants, journaux, configuration, utilisation et versions.

<a id="console-preview"></a>

## Aperçu de la console

![Polaris — Aperçu de la console](../assets/screenshots/credential-pool.png)

<a id="supported-providers"></a>

## Fournisseurs pris en charge

Le catalogue comprend 23 fournisseurs. Les modèles et fonctions disponibles dépendent des droits de chaque identifiant.

| Fournisseur | Connexion | Service / périmètre |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | Clé API | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | Clé API | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (code appareil) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | Clé API | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | Clé API | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Endpoint ; clé API facultative | Local / auto-hébergé |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | Clé API | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | Jeton API + ID du compte | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | Clé API | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | Clé API | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | Clé API ; ID d’organisation facultatif | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | Clé API / service | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | Clé API | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | OAuth navigateur / connexion appareil AWS / clé API | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (code appareil Meta) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | Clé API | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | Clé API | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | Clé API | Inférence hébergée NVIDIA |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | Clé API + offre Zen/Go | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | Clé API | Poolside API |

Les clients utilisent les [interfaces SDK](#sdk-surfaces) communes. Conversion, streaming et repli dépendent des capacités du modèle ; les options non prises en charge sont rejetées explicitement. Les paramètres de connexion appartiennent au fournisseur ou à l’identifiant dans **Providers**. Muse Code et Meta Model API ont des identifiants et espaces de modèles distincts.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## Architecture

```text
outils clients
  SDKs OpenAI | SDKs Google GenAI | SDKs Anthropic | Intégrations IDE
        |
        v
Polaris
  authentification -> traduction de format -> nettoyage de tokens -> routage -> basculement -> streaming
        |
        v
adaptateurs fournisseurs
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

L'API publique demeure stable pendant que les adaptateurs spécifiques aux fournisseurs évoluent sous Polaris.

<a id="repository-structure"></a>

## Structure du dépôt

```text
backend/       Racine de composition FastAPI, cœur de routage, traducteurs, stockage et tests
frontend/      Interface de console d'administration, styles, scripts et ressources graphiques
deploy/        Définitions de conteneurs, manifestes de plateforme et scripts système
docs/          Notes d'architecture et documentation de maintenance du projet
.github/       CI, automatisation des dépendances et modèles de contribution
```

Consultez [Architecture](../architecture.md) pour en savoir plus sur les limites de modules, flux de requêtes, gestion d'état et contraintes de version actuelles.

<a id="deployment"></a>

## Déploiement

Docker Compose est la voie de référence sur une machine avec un worker. Suivez le [guide d’installation](../installation.md) et sa [matrice de prise en charge](../installation.md#support-matrix) jusqu’au tableau de bord authentifié ; aucune prise en charge ARM64 supplémentaire n’est implicite.

Le profil standard fonctionne sans service externe et conserve les données dans `polaris-data`. Le modèle prépare `1.0.0`, qui n’est pas encore publiée. Résolvez les conflits avec les anciens tags/images avant l’installation selon la [liste de publication](../releases/1.0.0-preparation.md). Suivez le [guide de mise à jour et retour arrière](../updating.md) ; les options avancées s’activent via `deploy/compose.advanced.yml`.

Consultez le [contrat de nommage](../migrations/polaris.md) et le [dépannage](../troubleshooting.md). Les scripts natifs, `docker run`, Render et Zeabur sont des voies de compatibilité sans les mêmes preuves d’installation/restauration. L’image de production cible `linux/amd64` ; la publication `linux/arm64` reste suspendue.

### Pour développer ou diagnostiquer localement :

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

Sous Windows PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Ouvrez la console ; l’assistant initial est le même que sous Docker :

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## Configuration

Priorité : environnement, configuration enregistrée, valeurs par défaut. La [référence générée](../reference/configuration.md) précise types, catégories, responsables et application immédiate, après redémarrage ou uniquement par environnement. Une valeur invalide bloque le démarrage en indiquant la variable ; les noms `POLARIS_*` suspects sont signalés.

| Variable | Valeur par défaut | Description |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Adresse d'écoute (bind address). |
| `PORT` | `4283` | Port HTTP. |
| `HOST_PORT` | `4283` | Port côté hôte utilisé uniquement par Docker Compose. |
| `WORKERS` | `1` | Un seul worker est pris en charge. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Seul `standalone` est pris en charge. |
| `POLARIS_REPLICA_COUNT` | `1` | Une seule réplique applicative est prise en charge. |
| `CORS_ORIGINS` | vide | Liste séparée par des virgules des origines de navigateur autorisées pour les appels API cross-origin. Laisser vide pour un usage console same-origin. |
| `CORS_ORIGIN_REGEX` | vide | Expression régulière optionnelle pour les origines de navigateur dynamiques gérées. |
| `API_KEY` | générée automatiquement | Clé des clients API avec préfixe `sk-polaris-`. |
| `PANEL_PASSWORD` | vide jusqu’à la configuration | Mot de passe pour le panneau de contrôle web. |
| `SETUP_TOKEN` | vide | Configuration distante initiale : valeur unique d’au moins 24 caractères, jamais générée ni journalisée. Inutile en localhost direct. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Durée de vie de la session de console web en secondes. |
| `PANEL_COOKIE_SECURE` | automatique | Définir à `true` pour forcer les cookies de console uniquement via HTTPS. Laisser vide pour une détection automatique via `X-Forwarded-Proto`. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Fenêtre de limitation de débit de connexion en secondes. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Tentatives de connexion infructueuses autorisées par client pendant la fenêtre de limitation. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Nombre maximal d'adresses clients conservées en mémoire par le limiteur de connexion. |
| `MAX_REQUEST_BODY_MB` | `64` | Taille maximale du corps de requête HTTP en MiB. Les requêtes SDK trop volumineuses renvoient la structure d'erreur native du protocole. |
| `TRUST_PROXY_HEADERS` | `false` | N'accepter les en-têtes de transfert client/protocole que depuis un reverse proxy de confiance qui les écrase. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Répertoire de stockage des identifiants. Dans Docker, persister `/app/backend/data/creds` avec un volume hôte. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Point de terminaison backend de Code Assist. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Point de terminaison backend de Google Antigravity. |
| `PROXY` | vide | Proxy HTTP, HTTPS ou SOCKS optionnel. |
| `RETRY_429_ENABLED` | `true` | Active les nouvelles tentatives limitées pour les limites de débit et pannes temporaires d'upstream. Le nom historique est conservé pour compatibilité. |
| `RETRY_429_MAX_RETRIES` | `5` | Nombre maximal de tentatives pour les pannes temporaires d'upstream. |
| `RETRY_429_INTERVAL` | `1` | Délai de base entre les nouvelles tentatives temporaires en secondes. |
| `AUTO_DISABLE` | `false` | Désactive automatiquement les identifiants après des erreurs critiques configurées. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Liste séparée par des virgules des codes d'état d'erreur critique. |
| `ROUTING_STRATEGY` | `balanced` | Stratégie : `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | vide | Fournisseur préféré pour la stratégie `priority`, tel que `google_antigravity` ou `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Délai d'expiration d'inférence du fournisseur, compris entre 5 et 900 secondes. |
| `RESPONSE_CACHE_ENABLED` | `false` | Cache mémoire des réponses déterministes sans streaming, température 0. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Durée de vie du cache en secondes. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Nombre maximal de réponses en cache. |
| `GUARDRAILS_ENABLED` | `false` | Activer les protections avant l’appel fournisseur. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Masquer e-mails, numéros de carte et clés API dans le texte sortant. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Rejeter les injections de prompt avec HTTP 400. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | vide | Mots interdits séparés par des virgules, sans distinction de casse. |
| `PRICING_SYNC_ENABLED` | `true` | Actualiser les prix LiteLLM en arrière-plan ; conserver le dernier état valide hors ligne. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Intervalle des prix : 1–168 heures. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Nombre maximal de tentatives de continuation pour le streaming anti-troncature (anti-truncation). |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Compresse l'historique de conversation volumineux avant le routage vers le fournisseur. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Seuil estimé de tokens d'entrée déclenchant la compression de contexte. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Cible estimée de tokens d'entrée après compression. Doit être inférieur au seuil. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Nombre minimal de tours récents de l'utilisateur conservés lors de la compression. |
| `COMPATIBILITY_MODE` | `false` | Convertit les messages système pour les clients/modèles qui ne les prennent pas en charge nativement. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Inclut les champs de raisonnement du modèle (reasoning) lorsqu'ils sont disponibles. |
| `MONGODB_URI` | vide | Stockage MongoDB de compatibilité. |
| `POSTGRESQL_URI` | vide | Stockage PostgreSQL optionnel. |
| `CODE_ASSIST_CLIENT_ID` | client bureau intégré | Remplacement optionnel pour le Client ID OAuth de Code Assist. |
| `CODE_ASSIST_CLIENT_SECRET` | client bureau intégré | Remplacement optionnel pour le Client Secret OAuth de Code Assist. |
| `ANTIGRAVITY_CLIENT_ID` | client bureau intégré | Remplacement optionnel pour le Client ID OAuth de Google Antigravity. Peut également être géré depuis la page Providers. |
| `ANTIGRAVITY_CLIENT_SECRET` | client bureau intégré | Remplacement optionnel pour le Client Secret OAuth de Google Antigravity. À configurer via env ou l'interface Providers lors d'un changement upstream. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Remplacement optionnel du point de terminaison Generative Language API de Google AI Studio. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Remplacement optionnel du point de terminaison d'API SpaceXAI Console pour les identifiants par clé API. Gérable depuis la page Providers. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Remplacement optionnel du point de terminaison d'abonnement Grok Build OAuth. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Remplacement optionnel de l'émetteur Grok Build OAuth. Seuls les hôtes HTTPS sous `x.ai` sont acceptés par la console. |
| `XAI_CLIENT_ID` | client public intégré | Remplacement optionnel pour le Client ID OAuth PKCE de Grok Build. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Remplacement optionnel du User-Agent HTTP partagé pour les requêtes Grok Build OAuth et API SpaceXAI Console. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Remplacement optionnel du point de terminaison d'API OpenAI Platform. Gérable depuis la page Providers. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Remplacement optionnel du point de terminaison d'inférence et de catalogue de modèles de compte Codex. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Remplacement optionnel du point de terminaison de vérification des limites de compte Codex. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Remplacement optionnel du service d'autorisation d'appareils Codex. |
| `CODEX_CLIENT_ID` | client public intégré | Remplacement optionnel pour le Client ID OAuth d'appareils de Codex. |
| `CODEX_USER_AGENT` | compatible CLI Codex | Remplacement optionnel de User-Agent pour les requêtes Codex. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Endpoint Messages propre à Claude Code. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Remplacement optionnel du point de terminaison d'autorisation PKCE de Claude Code. Seuls les hôtes Anthropic et Claude sont acceptés. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Remplacement optionnel du point de terminaison d'échange de token de Claude Code. Seuls les hôtes Anthropic et Claude sont acceptés. |
| `CLAUDE_CLIENT_ID` | client public intégré | Remplacement optionnel pour le Client ID OAuth PKCE de Claude Code. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | User-Agent propre à Claude Code. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Endpoint Claude Platform distinct dans Providers. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | User-Agent Claude Platform indépendant. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Remplacement optionnel de User-Agent au niveau protocolaire de Google Antigravity. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Remplacement optionnel du champ userAgent au niveau de la charge utile de Google Antigravity. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Activer l’export authentifié `GET /metrics`. |
| `METRICS_TOKEN` | vide | Jeton Bearer d’au moins 32 octets UTF-8 requis pour Prometheus. |
| `OTEL_EXPORT_ENABLED` | `false` | Activer l’export agrégé OTLP/HTTP sans contenu. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | vide | Endpoint HTTPS du collecteur ; identifiants dans l’URL interdits. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Intervalle d’export : 15–300 secondes. |
| `LANGFUSE_PUBLIC_KEY` | vide | Activer Langfuse avec la clé secrète. |
| `LANGFUSE_SECRET_KEY` | vide | Clé secrète Langfuse pour les traces. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Endpoint de réception Langfuse. |
| `LOG_LEVEL` | `info` | Niveau de détail des journaux (log level). |
| `LOG_MAX_MB` | `10` | Taille maximale du fichier de journal actif avant rotation. |
| `LOG_BACKUP_COUNT` | `3` | Nombre de fichiers journaux archivés conservés lors des rotations. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | Emplacement du fichier journal. Dans Docker, persister `/app/backend/data/logs` avec un volume hôte. |

### Contrôle de la compression

La politique globale AI Quality fait autorité. Une clé ne peut que l’hériter ou désactiver la compression via `PATCH /api/virtual-keys/{key_id}/quality-policy` avec sa révision actuelle. `inherit` retire cette restriction. Une requête authentifiée peut envoyer `x-polaris-compression: off` ; sans cet en-tête ou avec `inherit`, la politique globale/de clé s’applique. Impossible de réactiver une compression globalement désactivée ou de la renforcer. Seul un préfixe sûr de l’historique est retiré ; si l’estimation ou la structure est incertaine, la requête reste intacte. Les comptes de tokens sont estimatifs.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## Surfaces SDK

Polaris est conçu autour du comportement d'URL standard des SDK Python officiels. Configurez chaque client exactement comme illustré ci-dessous ; la passerelle n'exige aucun préfixe de chemin dupliqué non standard.

Ces exemples utilisent le modèle virtuel `polaris`. Configurez son ordre de priorité de basculement fournisseur-modèle sur la page Models au préalable, ou remplacez-le par un ID de modèle concret.

### OpenAI Python SDK

Utilisez `/v1` comme base_url pour OpenAI. Le SDK ajoute automatiquement `/chat/completions`.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Explique ce dépôt en un seul paragraphe."}],
)
```

Le même client peut utiliser l'API OpenAI Responses :

```python
response = client.responses.create(
    model="polaris",
    instructions="Réponds de façon concise.",
    input="Explique ce dépôt en un seul paragraphe.",
)

print(response.output_text)
```

La compatibilité Responses prend en charge le texte, les entrées d'images, les outils de fonction sans streaming et le streaming de texte par SSE. Les outils intégrés hébergés par OpenAI, l'historique persistant de réponses et les appels de fonctions en streaming sont explicitement rejetés car Polaris n'exécute, ne persiste ni ne supprime silencieusement ces comportements spécifiques à OpenAI.

### Anthropic Python SDK

Utilisez l'origine de la passerelle comme base_url pour Anthropic. Le SDK ajoute automatiquement `/v1/messages`.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Rédige un message de commit court."}],
)
```

### Google GenAI Python SDK

Utilisez l'origine de la passerelle comme base_url pour Google GenAI. Le SDK ajoute automatiquement sa route de modèle par défaut, telle que `/v1beta/models/{model}:generateContent`.

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
    contents="Écris une petite fonction Python.",
    config=types.GenerateContentConfig(
        system_instruction="Tu es un assistant serviable.",
    ),
)
```

### Routes prises en charge

Polaris expose des routes compatibles SDK sans espace de noms dédié aux produits :

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

Les erreurs d'authentification, de validation de requête, de routage, d'upstream et préalables au streaming utilisent la structure d'erreur native du SDK correspondant. Chaque réponse HTTP inclut l'en-tête `X-Request-ID` ; les clients peuvent fournir un identifiant sécurisé dans cet en-tête pour corréler les requêtes de bout en bout. Les réponses limitées en débit ou temporairement indisponibles conservent l'en-tête `Retry-After` lorsqu'il est fourni par l'upstream.

<a id="model-features"></a>

## Fonctionnalités des modèles

La page Models assemble le modèle virtuel `polaris` à partir des modèles découverts sur les identifiants de fournisseurs activés. Définissez une fois l'ordre de priorité de ses membres, puis utilisez `polaris` depuis n'importe quel SDK pris en charge. Polaris équilibre la charge entre les identifiants sains prenant en charge le premier modèle et continue à travers l'ordre configuré lorsque ce modèle est indisponible. Les ID de modèles spécifiques des fournisseurs restent accessibles pour les clients nécessitant une sélection déterministe. Enregistrer une sélection vide désactive `polaris` sans impacter les identifiants des fournisseurs.

La découverte de modèles tient compte du fournisseur : un modèle partagé peut être alimenté par plusieurs fournisseurs, tandis que les modèles propres à un fournisseur n'utilisent que des identifiants compatibles. Chaque identifiant vérifié conserve son propre catalogue de fournisseur, et le routeur accorde la priorité au support explicitement déclaré par l'identifiant plutôt qu'aux déductions génériques. Actualiser le catalogue revérifie la disponibilité actuelle du fournisseur ; les sélections indisponibles restent visibles dans la configuration jusqu'à leur rétablissement ou suppression.

Lorsqu'un upstream renvoie une erreur `404` pour un modèle concret, Polaris enregistre une route indisponible pour cet identifiant et ce modèle au lieu de désactiver l'ensemble du fournisseur. Cette route est immédiatement et temporairement évitée, et demeure visible dans **Routes de modèles indisponibles** jusqu'à ce qu'elle soit supprimée ou que l'identifiant soit revalidé. Cela évite que les restrictions d'abonnement ou régionales d'un compte n'affectent les autres comptes sains du même fournisseur. Si aucun identifiant activé ne déclare ou ne permet de déduire la prise en charge d'un modèle demandé, la passerelle renvoie une erreur explicite d'absence d'identifiant compatible au lieu d'envoyer la requête à un fournisseur aléatoire.

Polaris interprète les préfixes et suffixes de fonctionnalités dans les noms de modèles :

- `fake-streaming/{model}` ou le préfixe de pseudo-streaming configuré pour les clients exigeant obligatoirement une sortie SSE.
- `streaming-anti-truncation/{model}` ou le préfixe anti-troncature configuré pour la récupération automatique lors de longs flux.
- Suffixes de réflexion (thinking) comme `-high`, `-medium`, `-low`, `-minimal` et `-max` pour les modèles compatibles de la famille Gemini.
- Suffixes de recherche comme `-search` pour les modèles prenant en charge l'ancrage Google Search (grounding).

Les adaptateurs de fournisseurs normalisent ces noms de fonctionnalités avant de transmettre les requêtes vers l'upstream.

<a id="usage-and-cost-visibility"></a>

## Visibilité de l'utilisation et des coûts

Chaque tentative fournisseur, nouvelle tentative ou repli est compté séparément ; les traces conservent le résultat final de la requête logique. Le tableau de bord indique réussite, identifiant, tokens d’entrée/sortie/cache/raisonnement déclarés, économies de compression estimées et coût USD. Une utilisation absente n’est pas un zéro mesuré. Les périodes suivent les limites fixes du fuseau du navigateur ; la journée couvre 00:00–23:00. Le catalogue public de prix LiteLLM est actualisé au démarrage puis toutes les 24 heures par défaut ; le dernier état validé est conservé atomiquement et un échec ne bloque pas l’inférence. `model_pricing.json` dans le répertoire des identifiants est prioritaire, en USD par million de tokens. Les agrégats sont disponibles dans le tableau de bord, `/api/virtual-keys` et `/metrics`. La facturation et le tokenizer du fournisseur font autorité.

Les clés virtuelles acceptent budgets quotidiens/mensuels, fenêtres glissantes RPM/TPM, expiration et listes de modèles avec motifs glob. Seuls leurs hachages SHA-256 sont stockés ; le secret n’est affiché qu’à la création.

<a id="credential-workflow"></a>

## Flux de travail des identifiants

1. Démarrez Polaris.
2. Ouvrez `http://IP_DE_VOTRE_SERVEUR:4283` sur VPS, ou `http://127.0.0.1:4283` en développement local.
3. Terminez les vérifications et créez le mot de passe propriétaire. Avant une configuration distante, définissez un `SETUP_TOKEN` unique d’au moins 24 caractères ou préconfigurez `PANEL_PASSWORD`. Le jeton n’est ni généré ni écrit dans les journaux.
4. Ajoutez un compte, une clé API ou une connexion Ollama depuis la page Providers.
5. Vérifiez les identifiants et observez l'état des cooldowns/erreurs dans la console. **Credentials** (`/credentials`).
6. Pointez votre outil de programmation vers l'une des interfaces API décrites ci-dessus.

Lors de l'ajout d'un identifiant Google Antigravity, Google redirige le navigateur vers `http://localhost:4283/callback` après connexion. Sur une machine locale, Polaris affiche une page de succès OAuth. Sur un VPS, cette adresse `localhost` correspondant à la machine du navigateur de l'utilisateur, la page peut ne pas charger ; copiez l'URL complète depuis la barre d'adresse du navigateur, revenez sur la page Providers, collez-la dans `Callback URL` et cliquez sur `Save credential`.

Google AI Studio utilise une authentification par clé API au lieu d'OAuth. Ajoutez une clé depuis la page Providers ; Polaris la valide par rapport au catalogue de modèles de Google, la stocke comme identifiant de fournisseur et route les requêtes Gemini ou Gemma compatibles à travers elle. Le routeur intelligent peut basculer entre AI Studio et Google Antigravity pour les modèles Gemini partagés tout en maintenant les modèles propriétaires sur des identifiants compatibles.

L'importation par lot de Google AI Studio accepte les fichiers JSON et les archives ZIP contenant des fichiers JSON. Un document JSON peut contenir une clé unique, un tableau `api_keys` ou un tableau d'objets de clé :

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

L’import de fichiers est hors ligne : Polaris contrôle la structure JSON/ZIP, enregistre les nouvelles clés comme `unverified` et ignore les doublons ou clés existantes sans contacter Google. Les listes de modèles importées ne sont pas considérées comme vérifiées. Les erreurs de format sont signalées sans exposer les clés. Lancez ensuite la vérification/découverte des modèles de l’identifiant ; **Test model** vérifie séparément l’accès à l’inférence et peut consommer du quota ou entraîner des frais.

Grok Build prend en charge les identifiants OAuth PKCE, tandis que SpaceXAI Console prend en charge les clés API. Les clés SpaceXAI Console sont validées par rapport au catalogue de modèles de l’API SpaceXAI Console avant enregistrement. Pour Grok Build OAuth, Polaris génère un lien d'autorisation ; après autorisation, copiez le code affiché sur la page Grok Build et collez-le dans le formulaire Grok Build OAuth. Les tokens d'accès sont renouvelés automatiquement lorsqu'un refresh token est disponible, et les deux types d'identifiants n'exposent que les modèles déclarés par leur catalogue actuel. La page Credentials permet de récupérer l'utilisation mensuelle des crédits et, lorsque xAI la fournit, l'utilisation hebdomadaire des comptes Grok Build OAuth. Cette vue de facturation au niveau du compte n'est pas disponible pour les clés API SpaceXAI Console.

Codex utilise le flux d'autorisation d'appareils d'OpenAI. Générez un code d'appareil depuis la page Providers, ouvrez l'URL de vérification affichée, saisissez le code, terminez la connexion et revenez vérifier l'autorisation. Polaris stocke le catalogue de modèles de compte renvoyé par Codex, rafraîchit les tokens d'accès OAuth si nécessaire et achemine les requêtes compatibles via le transport Codex Responses. OpenAI Platform utilise une authentification par clé API ; les clés sont validées via le catalogue de modèles de compte avant d’être enregistrées dans Credentials. Les deux produits prennent en charge l'importation JSON et ZIP avec validation et déduplication propres à chaque fournisseur.

Claude Code utilise le flux OAuth PKCE d'Anthropic. Générez un lien d'autorisation, complétez l'autorisation, puis collez le code d'autorisation obtenu dans la page Providers. Claude Platform accepte les clés API Anthropic. Les deux produits découvrent les modèles exposés pour chaque identifiant, utilisent le transport Anthropic Messages, rafraîchissent les tokens d'accès Claude Code lorsque possible et prennent en charge l'importation validée en JSON ou ZIP.

Muse Code utilise l’autorisation appareil de Meta. Dans **Providers → Muse Code**, obtenez le lien, approuvez le code chez Meta puis choisissez **Save credential**. La connexion est directe, sans CLI, Linux ni VPS. Les modèles commencent par `muse-code/` ; un nom d’affichage facultatif est disponible. Offre, quotas de session/semaine, réinitialisations et date d’observation proviennent exclusivement du fournisseur. Une donnée absente ne signifie pas 100 % disponible. L’actualisation vérifie l’abonnement et obtient une clé d’inférence avec la session existante ; reconnectez-vous si elle n’est plus valide.

Kiro propose OAuth navigateur Google/GitHub, autorisation appareil AWS et clé API. Les champs avancés dépendent du mode : région d’exécution, région de jeton/URL de départ AWS ou ARN de profil pour clé API.

Les connexions Ollama sont configurées par point de terminaison et peuvent inclure une clé API Bearer optionnelle pour les serveurs protégés ou dans le cloud. Polaris découvre les modèles via `/api/tags` et achemine l'inférence via `/api/chat`. Quand Polaris s'exécute dans Docker, `localhost` fait référence au conteneur lui-même ; utilisez une adresse host-gateway ou un point de terminaison Ollama accessible sur le réseau.

Les imports de données d’authentification et les imports par lot de Google Antigravity acceptent des archives jusqu'à 10 Mo, au maximum 500 fichiers, 2 Mo par fichier d'identifiant individuel et 25 Mo de données décompressées au total. Les imports de fournisseurs Google AI Studio, OpenAI, Anthropic et Ollama appliquent des limites plus strictes de 2 Mo par fichier importé, 200 entrées JSON et 5 Mo de données décompressées.

**Credentials** (`/credentials`) regroupe comptes et clés par fournisseur. La fenêtre de gestion présente identité, modèles, état et actions prises en charge. OAuth peut fournir quotas temporels/par modèle, offre et crédits. Une clé API ne donne pas automatiquement accès à l’e-mail, l’abonnement ou la facturation ; les données absentes restent indisponibles.

**Download ZIP** exporte les identifiants ; **Import ZIP** traite les archives multifournisseurs avec validation et déduplication adaptées. Les erreurs sont signalées par entrée. Importer ou découvrir un catalogue ne prouve pas l’accès à l’inférence ; **Test model** effectue un appel réel pouvant consommer un quota ou être facturé. Les archives contiennent des secrets. Pour une sauvegarde SQLite complète avec configuration, utilisez le processus chiffré de **Settings**.

Les identifiants Google Antigravity utilisent `google-antigravity-{account_fingerprint}.json`, où l'empreinte est dérivée de l'e-mail normalisé sans l'exposer. Les identifiants Google AI Studio utilisent `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth utilise `grok-{account_fingerprint}.json`, SpaceXAI Console utilise `xai-console-{key_fingerprint}.json`, Codex utilise `openai-codex-{account_fingerprint}.json`, OpenAI Platform utilise `openai-platform-{key_fingerprint}.json`, Claude Code utilise `claude-code-{account_fingerprint}.json`, Claude Platform utilise `claude-platform-{key_fingerprint}.json` et les connexions Ollama utilisent `ollama-{connection_fingerprint}.json`. Les identifiants historiques `provider_*.json` et `xai-grok-*.json` demeurent compatibles et sont exportés avec des noms canoniques.

Noms des modes d'identifiants :

- `code_assist` : identifiants standard Code Assist.
- `provider` : identifiants de backend de fournisseur.

<a id="storage"></a>

## Stockage

SQLite est le stockage recommandé. Compose conserve `/app/backend/data` dans `polaris-data` ; avec Docker direct, montez durablement `/app/backend/data/creds` et `/app/backend/data/logs`, par exemple sous `/opt/polaris/creds` et `/opt/polaris/logs`.

PostgreSQL est optionnel ; MongoDB est conservé pour compatibilité, avec accès direct sans Redis. Configurez un seul backend externe. Son échec d’initialisation arrête le démarrage sans repli silencieux vers SQLite. Un worker et une réplique restent requis. La sauvegarde portable chiffrée ne couvre que SQLite ; aucune migration à chaud entre backends n’est fournie.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[Stockage](../storage.md)

L'importation d'identifiants depuis les variables d'environnement est disponible depuis la console. Définissez l'une des variables suivantes avec une chaîne JSON brute ou utilisez la variante `_B64` correspondante pour une chaîne JSON encodée en base64 :

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

La charge utile peut être un objet d'identifiant unique, un tableau ou `{ "credentials": [...] }`.

<a id="development"></a>

## Développement

Cette section s'adresse aux contributeurs et au débogage local. Les déploiements en production doivent utiliser Docker avec des volumes hôtes persistants.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

Les [contrôles qualité](../quality-gates.md) couvrent tâche, phase et publication. `python tools/quality_gate.py --list-suites` liste séparément les vérifications externes optionnelles. Le [contrat de compatibilité](../compatibility.md) protège routes SDK/gestion, migrations de configuration, schémas et exemples.

Démarrez le service une fois l'ensemble des vérifications réussies :

```bash
python backend/main.py
```

Le standard de production est Python 3.12, et l'intégration continue vérifie actuellement Python 3.12 et 3.14. Consultez [Contribution](../../CONTRIBUTING.md) pour le cycle de vie des pull requests et les critères de revue de code.

<a id="deployment-notes"></a>

## Notes de déploiement

- Ne committez jamais de fichiers JSON d'identifiants ni de fichiers `.env`.
- Utilisez une `API_KEY` dédiée pour les intégrations clientes et un `PANEL_PASSWORD` distinct pour l'accès à la console.
- Restreignez l'accès au volume d'identifiants ou à la base de données externe et activez le chiffrement au repos (encryption at rest) ; les tokens des fournisseurs doivent pouvoir être relus par le routeur.
- Placez Polaris derrière un reverse proxy avec TLS lorsqu'il est accessible au-delà de localhost.
- Configurez le reverse proxy pour préserver `Host` et transmettre `X-Forwarded-Proto` ; définissez `PANEL_COOKIE_SECURE=true` lorsque la terminaison HTTPS est garantie.
- Ne définissez `TRUST_PROXY_HEADERS=true` que si le service n'est accessible qu'à travers un proxy de confiance qui écrase `X-Forwarded-For` et `X-Forwarded-Proto`.
- Utilisez `GET /health` pour les sondes de vivacité (liveness probe) et `GET /ready` pour les vérifications de disponibilité avec état du stockage (readiness probe).
- La télémétrie externe est optionnelle : `PROMETHEUS_EXPORT_ENABLED` et un `METRICS_TOKEN` fort sont requis pour Prometheus. OpenTelemetry n’exporte que des agrégats, jamais le contenu des prompts/réponses. Voir [observabilité](../observability.md).
- L'image Docker ne s'exécute en root que le temps nécessaire pour ajuster les permissions du répertoire de données monté, puis bascule sur l'utilisateur non privilégié `gateway`.
- Définissez `CORS_ORIGINS` avec des origines de confiance explicites lorsque les clients navigateurs requièrent un accès cross-origin.
- Avant une mise à jour ou un transfert, utilisez la [sauvegarde SQLite chiffrée et authentifiée](../backup-and-restore.md). Conservez archive et phrase secrète hors de `polaris-data`.
- La publication d'images Docker utilise les secrets de dépôt `DOCKERHUB_USERNAME` et `DOCKERHUB_TOKEN` pour Docker Hub, et le `GITHUB_TOKEN` intégré pour GitHub Packages sous `ghcr.io/nguywnben/polaris`. Ne définissez la variable optionnelle `IMAGE_NAME` que lors de la publication vers un nom d'image Docker Hub personnalisé.
- Conservez `WORKERS=1` et une seule réplique d'application pour toute la série 1.x ; le stockage externe ne remplace pas la coordination distribuée.
- Utilisez les routes de gestion canoniques `/api/credentials`. Les alias `/api/creds` de la phase bêta ont été supprimés en 1.0.0.
- Suivez le guide [Mise à niveau vers 1.0](../upgrading-to-1.0.md) avant de migrer un déploiement bêta.
- Suivez le [guide de mise à jour](../updating.md) lors de la mise à niveau d'une instance déployée ou d'un retour arrière (rollback).
- Suivez la [checklist de release](../release-checklist.md) maintenue avant d'apposer un tag ou de publier une image.
- Alignez les politiques de rétention des journaux et de rotation des identifiants avec vos limites d'utilisation.
- Révoquez et renouvelez immédiatement les identifiants si un analyseur de sécurité détecte une fuite de secrets.
- Le Render Blueprint utilise un service payant doté d'un disque persistant. Les services gratuits de Render utilisent un système de fichiers éphémère et ne conviennent qu'aux évaluations temporaires.

<a id="community-and-project-health"></a>

## Communauté et santé du projet

- Lisez le guide de [Contribution](../../CONTRIBUTING.md) avant d'ouvrir une pull request.
- Signalez toute vulnérabilité de sécurité via la procédure privée décrite dans la [Politique de sécurité](../../SECURITY.md).
- Consultez le [Journal des modifications](../../CHANGELOG.md) pour le détail des changements par version.
- Respectez le [Code de conduite](../../CODE_OF_CONDUCT.md) dans tous les espaces du projet.

<a id="acknowledgements-inspirations"></a>

## Remerciements et inspirations

Polaris s'appuie sur le travail de la communauté open source dans les domaines du routage d'IA, de la télémétrie et des passerelles. Nous exprimons notre profonde gratitude aux créateurs et mainteneurs des projets suivants :

| Projet | Description | Étoiles |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Source d'inspiration pour la gestion multi-fournisseurs de clés et l'agrégation d'API basée sur le web | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Pionnier de la couche de proxy multi-format et de la traduction de protocoles pour CLI de codage IA | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Référence pour le proxy LLM unifié, l'équilibrage de charge et le routage de basculement | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Architecture de passerelle IA ultra-rapide, stratégies de routage et modèles de basculement résilients | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Plateforme d'ingénierie LLM open source, traçage, observabilité et ingestion de métriques | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## Licence

Polaris est publié sous la [Licence MIT](../../LICENSE).
