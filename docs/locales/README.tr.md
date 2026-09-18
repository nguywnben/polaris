<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Yapay Zeka Kodlama Araçları İçin Evrensel AI Yönlendirici ve Birleşik Çok Sağlayıcılı Ağ Geçidi</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">Desteklenen Sağlayıcılar</a> • <a href="#core-capabilities">Temel Yetenekler</a> • <a href="#deployment">Dağıtım</a> • <a href="#sdk-surfaces">SDK Yüzeyleri</a> • <a href="#architecture">Mimari</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <a href="README.th.md">ภาษาไทย</a> • <b>Türkçe</b></p>
</div>

---

Bu README aynı işlev kapsamıyla 15 dilde sunulur. Bağlantılı teknik kılavuzlar özgün dillerini korur.

Kodlama araçları için evrensel bir yapay zeka yönlendiricisi. Polaris; akıllı otomatik yük devretme (auto-fallback), belirteç (token) duyarlı istek temizleme, kullanım görünürlüğü ve kusursuz format dönüşümü sağlayarak yerel ajanların, IDE asistanlarının ve otomasyon betiklerinin tek bir kararlı API yüzeyi üzerinden ücretsiz ve premium LLM kapasitesini kullanmasına olanak tanır.

> Polaris, bir kişi veya güvenilir ekip için tek worker ve tek replikalı kendi sunucusunda barındırmayı destekler. Docker Compose, yerel sahip girişi, SQLite, yönlendirme ve belgelenmiş SDK arayüzleri çekirdeği oluşturur. PostgreSQL, OIDC, ters proxy ve dış telemetri isteğe bağlıdır; MongoDB uyumluluk içindir. Çoklu replika koordinasyonu ve Kubernetes desteklenmez. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Neden Polaris

Modern kodlama iş akışları genellikle istemcileri ve sağlayıcıları bir arada kullanır: OpenAI uyumlu araçlar, Gemini yerel SDK'ları, Anthropic tarzı ajanlar, Google destekli kimlik bilgileri ve deneysel model rotaları. Polaris, bu istemciler ile model arka uçları arasında yer alır; böylece her araç zaten anladığı formatta konuşmaya devam ederken ağ geçidi yönlendirme, yeniden denemeler, istek temizleme ve yanıt normalleştirmesini üstlenir.

<a id="core-capabilities"></a>

## Temel Yetenekler

- İstek başına rezervasyon, adil döndürme, bekleme süreleri ve tükenen kotaları dikkate alan otomatik yedek yönlendirme.
- Sistem yönergeleri, araçlar ve son konuşmaları koruyan geçmiş temizliği.
- OpenAI Chat Completions/Responses, Gemini ve Anthropic Messages arasında akış destekli dönüşüm.
- Sağlayıcıya özgü doğrulama ve yinelenen kayıt temizliğiyle OAuth hesapları ve API anahtarları.
- Hesap izinlerine uygun, kimlik bilgisi başına model kataloğu.
- Kullanılamayan model yollarının kaydı ve Models sayfasından kurtarma.
- SSE, sözde akış ve kesilmiş yanıtlar için sınırlı yeniden deneme.
- Dengeli, öncelikli, ağırlıklı, en düşük gecikmeli veya en düşük maliyetli yönlendirme.
- Günlük/aylık bütçe, RPM/TPM, son kullanma ve izinli modeller içeren sanal anahtarlar.
- Çağrı başına tahmini USD maliyeti, panel ve Prometheus toplamları.
- İsteğe bağlı istem enjeksiyonu, engellenen sözcük ve kişisel veri koruması.
- Deterministik yanıtlar için isteğe bağlı tam eşleşmeli önbellek.
- Prometheus, isteğe bağlı Langfuse dışa aktarımı ve kullanım takibi.
- Kimlik bilgileri, günlükler, yapılandırma, kullanım ve sürüm konsolu.

<a id="console-preview"></a>

## Konsol Önizlemesi

![Polaris — Konsol Önizlemesi](../assets/screenshots/credential-pool.png)

<a id="supported-providers"></a>

## Desteklenen Sağlayıcılar

Katalogda 23 sağlayıcı bulunur. Kullanılabilir modeller ve özellikler her kimlik bilgisinin izinlerine bağlıdır.

| Sağlayıcı | Bağlantı | Hizmet / kapsam |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API anahtarı | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API anahtarı | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (cihaz kodu) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API anahtarı | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | API anahtarı | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Uç nokta; API anahtarı isteğe bağlı | Yerel / kendi sunucusunda |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | API anahtarı | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | API belirteci + hesap kimliği | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | API anahtarı | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | API anahtarı | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | API anahtarı; kuruluş kimliği isteğe bağlı | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | API / hizmet anahtarı | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | API anahtarı | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | Tarayıcı OAuth / AWS cihaz girişi / API anahtarı | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (Meta cihaz kodu) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | API anahtarı | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | API anahtarı | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | API anahtarı | NVIDIA barındırılan çıkarım |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | API anahtarı + Zen/Go planı | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | API anahtarı | Poolside API |

İstemciler ortak [SDK arayüzlerini](#sdk-surfaces) kullanır. Dönüşüm, akış ve yedek yönlendirme model yeteneklerine bağlıdır; uyumsuz seçenekler açıkça reddedilir. **Providers** üzerinde sağlayıcı veya kimlik bilgisi bazında yapılandırın. Muse Code ile Meta Model API kimlik bilgileri ve model ad alanları ayrıdır.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## Mimari

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | IDE entegrasyonları
        |
        v
Polaris
  kimlik doğrulama -> format dönüştürme -> belirteç duyarlı temizleme -> yönlendirme -> yük devretme -> akış
        |
        v
provider adapters
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

Genel API kararlı kalırken sağlayıcıya özel adaptörler Polaris arkasında gelişmeye devam eder.

<a id="repository-structure"></a>

## Depo Yapısı

```text
backend/       FastAPI bileşim kökü, yönlendirme çekirdeği, dönüştürücüler, depolama ve testler
frontend/      Yönetim konsolu işaretlemesi, stilleri, betikleri ve sağlayıcı varlıkları
deploy/        Konteyner tanımları, platform bildirimleri ve işletim sistemi betikleri
docs/          Mimari notları ve bakımı yapılan proje belgeleri
.github/       CI, bağımlılık otomasyonu ve katkı şablonları
```

Modül sınırları, istek akışı, durum sahipliği ve mevcut sürüm kısıtlamaları için [Mimari](../architecture.md) belgesine bakın.

<a id="deployment"></a>

## Dağıtım

Tek makine ve tek worker için ana yol Docker Compose'dur. [Kurulum](../installation.md) ve [destek tablosunu](../installation.md#support-matrix) izleyin.

Temel profil dış hizmet gerektirmez; veriler `polaris-data` içinde saklanır. Şablon `1.0.0` sürümünü hedefler. Yalnızca aynı sürümün yayımlanmış Polaris etiket ve imajlarıyla kurulum yapın; yayımlanmamış kaynak kod için [yayın kontrol listesine](../releases/1.0.0-preparation.md) göre ayrı bir yerel imaj oluşturun. [Güncelleme ve geri dönüş](../updating.md) sürecini izleyin; gelişmiş özellikler `deploy/compose.advanced.yml` ile isteğe bağlıdır.

[Adlandırma sözleşmesi](../migrations/polaris.md) ve [sorun giderme](../troubleshooting.md) kılavuzlarına bakın. Yerel betikler, `docker run`, Render ve Zeabur eşdeğer kurulum/kurtarma doğrulamasına sahip olmayan uyumluluk yollarıdır. İmajlar `linux/amd64` için yayımlanır; `linux/arm64` yayını duraklatılmıştır.

### Yerel geliştirme veya tanılama:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

Windows PowerShell üzerinde:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Konsolu açın; ilk kurulum Docker ile aynıdır:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## Yapılandırma

Öncelik: ortam değişkenleri, kayıtlı ayarlar, varsayılanlar. [Üretilen yapılandırma başvurusu](../reference/configuration.md) türleri, grupları, sorumlu modülleri ve anında/yeniden başlatmada/yalnız ortamdan uygulamayı açıklar. Geçersiz değer başlatmayı engeller ve değişkeni belirtir; olası `POLARIS_*` yazım hataları uyarılır.

| Değişken | Varsayılan | Amaç |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bağlanma adresi (bind address). |
| `PORT` | `4283` | HTTP bağlantı noktası. |
| `HOST_PORT` | `4283` | Yalnızca Docker Compose tarafından kullanılan ana makine tarafı bağlantı noktası. |
| `WORKERS` | `1` | Yalnız tek worker desteklenir. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Yalnız `standalone` desteklenir. |
| `POLARIS_REPLICA_COUNT` | `1` | Yalnız tek replika desteklenir. |
| `CORS_ORIGINS` | boş | API'yi kaynaklar arası (cross-origin) çağırmasına izin verilen virgülle ayrılmış tarayıcı kaynakları. Aynı kaynak konsol kullanımı için boş bırakın. |
| `CORS_ORIGIN_REGEX` | boş | Yönetilen dinamik tarayıcı kaynakları için isteğe bağlı regex. |
| `API_KEY` | otomatik üretilir | `sk-polaris-` önekli istemci API anahtarı. |
| `PANEL_PASSWORD` | kuruluma kadar boş | Web kontrol paneli şifresi. |
| `SETUP_TOKEN` | boş | Uzak kurulum için en az 24 karakterli benzersiz belirteç; üretilmez veya kaydedilmez. Doğrudan localhost için gerekmez. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Saniye cinsinden web konsolu oturum ömrü. |
| `PANEL_COOKIE_SECURE` | otomatik | Yalnızca HTTPS panel çerezleri gerektirmek için `true` yapın. HTTPS'yi `X-Forwarded-Proto` üzerinden algılamak için boş bırakın. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Saniye cinsinden giriş hız sınırlama penceresi. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Hız sınırlama penceresi içinde istemci başına izin verilen maksimum başarısız giriş denemesi. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Bellek içi giriş sınırlayıcısı tarafından tutulan maksimum istemci adresi. |
| `MAX_REQUEST_BODY_MB` | `64` | MiB cinsinden maksimum HTTP istek gövdesi boyutu. Aşırı büyük SDK istekleri yerel protokol hata zarfını döndürür. |
| `TRUST_PROXY_HEADERS` | `false` | İstemci/protokol yönlendirme başlıklarını yalnızca bunların üzerine yazan güvenilir bir ters proxy'den kabul edin. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Kimlik bilgisi depolama dizini. Docker'da `/app/backend/data/creds` dizinini bir ana makine birimiyle kalıcı hale getirin. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Code Assist arka uç uç noktası. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Google Antigravity arka uç uç noktası. |
| `PROXY` | boş | İsteğe bağlı HTTP, HTTPS veya SOCKS proxy. |
| `RETRY_429_ENABLED` | `true` | Hız sınırları ve geçici yukarı akış (upstream) hataları için sınırlı yeniden denemeleri etkinleştirin. Eski ad yapılandırma uyumluluğu için korunmuştur. |
| `RETRY_429_MAX_RETRIES` | `5` | Geçici yukarı akış hataları için maksimum yeniden deneme sayısı. |
| `RETRY_429_INTERVAL` | `1` | Saniye cinsinden geçici yeniden denemeler arasındaki temel gecikme. |
| `AUTO_DISABLE` | `false` | Yapılandırılmış kritik hatalardan (hard failures) sonra kimlik bilgilerini devre dışı bırakın. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Virgülle ayrılmış kritik hata durum kodları. |
| `ROUTING_STRATEGY` | `balanced` | Strateji: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | boş | `priority` stratejisi tarafından tercih edilen sağlayıcı, örneğin `google_antigravity` veya `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Sağlayıcı çıkarım zaman aşımı, 5 ile 900 saniye arasında sınırlandırılmıştır. |
| `RESPONSE_CACHE_ENABLED` | `false` | Sıcaklık 0, akışsız deterministik yanıtlar için bellek önbelleği. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Önbellek süresi, saniye. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | En fazla önbellek yanıtı. |
| `GUARDRAILS_ENABLED` | `false` | Çağrı öncesi korumaları etkinleştir. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Giden metindeki e-posta, kart ve API anahtarlarını maskele. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | İstem enjeksiyonunu HTTP 400 ile reddet. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | boş | Virgülle ayrılmış yasak sözcükler; büyük/küçük harf duyarsız. |
| `PRICING_SYNC_ENABLED` | `true` | LiteLLM fiyatlarını arka planda yenile; çevrimdışıyken son geçerli kopyayı koru. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Fiyat yenileme aralığı: 1–168 saat. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Kesilmeyi önleyici akış için maksimum devam denemesi. |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Sağlayıcı yönlendirmesinden önce aşırı büyük konuşma geçmişini sıkıştırın. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Sıkıştırmayı etkinleştiren tahmini giriş belirteci eşiği. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Sıkıştırma sonrası tahmini hedef giriş belirteci sayısı. Eşikten düşük olmalıdır. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Sıkıştırma sırasında korunan minimum son kullanıcı konuşma turu sayısı. |
| `COMPATIBILITY_MODE` | `false` | Sistem mesajlarını reddeden istemciler/modeller için dönüştürür. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Mevcut olduğunda model akıl yürütme (reasoning) alanlarını dahil edin. |
| `MONGODB_URI` | boş | Uyumluluk MongoDB depolaması. |
| `POSTGRESQL_URI` | boş | İsteğe bağlı PostgreSQL depolaması. |
| `CODE_ASSIST_CLIENT_ID` | dahili masaüstü istemcisi | Code Assist OAuth Client ID için isteğe bağlı geçersiz kılma. |
| `CODE_ASSIST_CLIENT_SECRET` | dahili masaüstü istemcisi | Code Assist OAuth Client Secret için isteğe bağlı geçersiz kılma. |
| `ANTIGRAVITY_CLIENT_ID` | dahili masaüstü istemcisi | Google Antigravity OAuth Client ID için isteğe bağlı geçersiz kılma. Providers sayfasından da yönetilebilir. |
| `ANTIGRAVITY_CLIENT_SECRET` | dahili masaüstü istemcisi | Google Antigravity OAuth Client Secret için isteğe bağlı geçersiz kılma. Yukarı akış istemcisi değiştiğinde ortam değişkeni veya Providers sayfası üzerinden yapılandırın. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Google AI Studio Generative Language API uç noktası için isteğe bağlı geçersiz kılma. |
| `XAI_API_URL` | `https://api.x.ai/v1` | API anahtarı kimlik bilgileri için SpaceXAI Console API uç noktası geçersiz kılması. Providers sayfasından da yönetilebilir. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Grok Build OAuth abonelik uç noktası için isteğe bağlı geçersiz kılma. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Grok Build OAuth sağlayıcısı (issuer) için isteğe bağlı geçersiz kılma. Konsol tarafından yalnızca `x.ai` altındaki HTTPS ana makineleri kabul edilir. |
| `XAI_CLIENT_ID` | dahili genel istemci | Grok Build PKCE OAuth Client ID için isteğe bağlı geçersiz kılma. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Grok Build OAuth ve SpaceXAI Console API istekleri için paylaşılan ortak HTTP User-Agent geçersiz kılması. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | OpenAI Platform API uç noktası için isteğe bağlı geçersiz kılma. Providers sayfasından da yönetilebilir. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Codex çıkarım ve hesap-model uç noktası için isteğe bağlı geçersiz kılma. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Codex hesap hız sınırı uç noktası için isteğe bağlı geçersiz kılma. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Codex cihaz yetkilendirme hizmeti için isteğe bağlı geçersiz kılma. |
| `CODEX_CLIENT_ID` | dahili genel istemci | Codex cihazı OAuth Client ID için isteğe bağlı geçersiz kılma. |
| `CODEX_USER_AGENT` | Codex CLI uyumlu değer | Codex istekleri için isteğe bağlı User-Agent geçersiz kılması. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Claude Code'a özel Messages uç noktası. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Claude Code PKCE yetkilendirme uç noktası için isteğe bağlı geçersiz kılma. Konsol tarafından yalnızca Anthropic ve Claude ana makineleri kabul edilir. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Claude Code belirteç uç noktası için isteğe bağlı geçersiz kılma. Konsol tarafından yalnızca Anthropic ve Claude ana makineleri kabul edilir. |
| `CLAUDE_CLIENT_ID` | dahili genel istemci | Claude Code PKCE OAuth Client ID için isteğe bağlı geçersiz kılma. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | Claude Code'a özel User-Agent. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Providers içinde ayrı Claude Platform uç noktası. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | Bağımsız Claude Platform User-Agent. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Google Antigravity protokolü User-Agent geçersiz kılması. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Google Antigravity yük düzeyi userAgent geçersiz kılması. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Kimlik doğrulamalı `GET /metrics` etkinleştir. |
| `METRICS_TOKEN` | boş | Prometheus için en az 32 UTF-8 baytlık Bearer belirteci. |
| `OTEL_EXPORT_ENABLED` | `false` | İçeriksiz OTLP/HTTP toplu dışa aktarımını etkinleştir. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | boş | HTTPS toplayıcı; URL içinde kimlik bilgisi yasak. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Aktarım aralığı: 15–300 saniye. |
| `LANGFUSE_PUBLIC_KEY` | boş | Gizli anahtarla birlikte Langfuse'u etkinleştir. |
| `LANGFUSE_SECRET_KEY` | boş | İzler için Langfuse gizli anahtarı. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse alım uç noktası. |
| `LOG_LEVEL` | `info` | Çalışma zamanı günlük seviyesi. |
| `LOG_MAX_MB` | `10` | Döndürmeden (rotation) önceki maksimum aktif günlük dosyası boyutu. |
| `LOG_BACKUP_COUNT` | `3` | Saklanan döndürülmüş günlük dosyası sayısı. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | Dosya günlüğü hedefi. Docker'da `/app/backend/data/logs` dizinini bir ana makine birimiyle kalıcı hale getirin. |

### Sıkıştırma denetimi

Küresel AI Quality politikası üst sınırdır. Sanal anahtar yalnızca devralabilir veya sıkıştırmayı kapatabilir: geçerli revizyon ile `PATCH /api/virtual-keys/{key_id}/quality-policy` kullanın; `inherit` anahtar kısıtını kaldırır. Kimliği doğrulanmış istek `x-polaris-compression: off` gönderebilir; başlık yoksa veya `inherit` ise küresel/anahtar politikası uygulanır. Yasaklanmış sıkıştırma yeniden açılamaz veya güçlendirilemez. Yalnızca güvenli geçmiş öneki çıkarılır; yapı ya da tahmin belirsizse istek değiştirilmez. Token sayıları tahminidir.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## SDK Yüzeyleri

Polaris, resmi Python SDK'larının standart URL davranışı etrafında tasarlanmıştır. Her istemciyi tam olarak aşağıda gösterildiği gibi yapılandırın; ağ geçidi standart olmayan yinelenen yol önekleri gerektirmez.

Örnekler sanal model `polaris` kullanır. Önce Models sayfasında sıralı sağlayıcı-model yük devretmesini yapılandırın veya somut bir model kimliğiyle değiştirin.

### OpenAI Python SDK

OpenAI temel URL'si olarak `/v1` kullanın. SDK sonuna `/chat/completions` ekler.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Bu depoyu bir paragrafta açıklayın."}],
)
```

Aynı istemci OpenAI Responses API'sini de kullanabilir:

```python
response = client.responses.create(
    model="polaris",
    instructions="Kısa ve öz olun.",
    input="Bu depoyu bir paragrafta açıklayın.",
)

print(response.output_text)
```

Responses uyumluluğu; metin, görüntü girişleri, akışsız fonksiyon araçları (non-streaming function tools) ve SSE metin akışını destekler. OpenAI tarafından barındırılan yerleşik araçlar, saklanan yanıt geçmişi ve akışlı fonksiyon çağrıları açıkça reddedilir; çünkü Polaris bu OpenAI'ye özgü davranışları yürütmez, kalıcı kılmaz veya sessizce göz ardı etmez.

### Anthropic Python SDK

Anthropic temel URL'si olarak ağ geçidi kaynağını (origin) kullanın. SDK sonuna `/v1/messages` ekler.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Kısa bir commit mesajı taslağı hazırlayın."}],
)
```

### Google GenAI Python SDK

Google GenAI temel URL'si olarak ağ geçidi kaynağını kullanın. SDK varsayılan model rotasını ekler, örneğin `/v1beta/models/{model}:generateContent`.

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
    contents="Küçük bir Python fonksiyonu yazın.",
    config=types.GenerateContentConfig(
        system_instruction="Yardımsever bir asistansınız.",
    ),
)
```

### Desteklenen Rotalar

Polaris, ürün ad alanı olmadan SDK uyumlu rotalar sunar:

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

Kimlik doğrulama, istek doğrulama, yönlendirme, yukarı akış ve akış öncesi hatalar, seçilen SDK yüzeyi için yerel hata zarfını kullanır. Her HTTP yanıtı `X-Request-ID` içerir; istemciler uçtan uca ilişkilendirme için bu başlıkta güvenli bir tanımlayıcı sağlayabilir. Hız sınırlı ve geçici olarak kullanılamayan yanıtlar, yukarı akış sağladığında `Retry-After` başlığını korur.

<a id="model-features"></a>

## Model Özellikleri

Models sayfası, etkin sağlayıcı kimlik bilgileri genelinde keşfedilen modellerden sanal `polaris` modelini oluşturur. Üyelerini bir kez öncelik sırasına göre düzenleyin, ardından desteklenen herhangi bir SDK'dan `polaris` kullanın. Polaris, ilk modeli destekleyen sağlıklı kimlik bilgilerini dengeler ve bu model kullanılamadığında yapılandırılmış model sırası üzerinden devam eder. Belirli sağlayıcı model kimlikleri, deterministik model seçimine ihtiyaç duyan istemciler için kullanılabilir olmaya devam eder. Boş bir seçimi kaydetmek, sağlayıcı kimlik bilgilerini etkilemeden `polaris` modelini devre dışı bırakır.

Model keşfi sağlayıcıya duyarlıdır: paylaşılan bir model birden fazla sağlayıcı tarafından desteklenebilirken, sağlayıcıya özgü modeller yalnızca uyumlu kimlik bilgilerini kullanır. Doğrulanan her kimlik bilgisi kendi sağlayıcı kataloğunu saklar ve yönlendirici, bildirilen kimlik bilgisi desteğine genel sağlayıcı çıkarımına göre öncelik verir. Kataloğu yenilemek, mevcut sağlayıcı kullanılabilirliğini yeniden kontrol eder; kullanılamayan seçimler geri yüklenene veya kaldırılana kadar yapılandırmada görünür kalır.

Bir yukarı akış somut bir model için `404` döndürdüğünde Polaris, tüm sağlayıcıyı devre dışı bırakmak yerine söz konusu kimlik bilgisi ve model için kullanılamayan bir rota kaydeder. Rota hemen geçici olarak atlatılır ve kaldırılana veya kimlik bilgisi yeniden doğrulanana kadar **Unavailable Model Routes** altında görünür kalır. Bu, bir hesabın aboneliğinin veya bölgesel yetkisinin aynı sağlayıcıdaki diğer hesapları etkilemesini önler. Etkinleştirilmiş hiçbir kimlik bilgisi istenen somut model için destek bildirmez veya çıkaramazsa ağ geçidi, isteği rastgele bir sağlayıcıya göndermek yerine net bir uyumlu kimlik bilgisi yok hatası döndürür.

Polaris, model adlarındaki özellik öneklerini ve soneklerini tanır:

- SSE çıktısı gerektiren istemciler için `fake-streaming/{model}` veya yapılandırılmış sözde akış öneki.
- Uzun biçimli akış kurtarma için `streaming-anti-truncation/{model}` veya yapılandırılmış kesilmeyi önleme öneki.
- Desteklenen Gemini ailesi modelleri için `-high`, `-medium`, `-low`, `-minimal` ve `-max` gibi düşünme (thinking) sonekleri.
- Google Search doğrulaması (grounding) destekleyen modeller için `-search` gibi arama sonekleri.

Sağlayıcı adaptörleri, yukarı akış isteklerini göndermeden önce bu özellik adlarını normalleştirir.

<a id="usage-and-cost-visibility"></a>

## Kullanım ve Maliyet Görünürlüğü

Her sağlayıcı denemesi, tekrar ve yedek yönlendirme ayrı sayılır; izler mantıksal isteğin son sonucunu korur. Sonuç, kimlik bilgisi, bildirilen giriş/çıkış/önbellek/akıl yürütme tokenları, tahmini tasarruf ve USD maliyeti kaydedilir. Eksik kullanım ölçülmüş sıfır değildir. Dönemler tarayıcının saat diliminde sabit sınırlar kullanır; günlük görünüm 00:00–23:00 aralığındadır. LiteLLM fiyatları varsayılan olarak başlangıçta ve her 24 saatte yenilenir; son geçerli kopya atomik olarak korunur ve hata çıkarımı engellemez. Kimlik bilgisi dizinindeki `model_pricing.json` önceliklidir; fiyatlar milyon token başınadır. Panel, `/api/virtual-keys` ve `/metrics` toplamları sunar. Sağlayıcının faturası ve tokenizer'ı esastır.

Sanal anahtarlar günlük/aylık bütçe, kayan RPM/TPM pencereleri, süre sonu ve glob model kurallarını destekler. SHA-256 özetleri saklanır; gizli değer yalnızca oluşturulurken gösterilir.

<a id="credential-workflow"></a>

## Kimlik Bilgisi İş Akışı

1. Polaris'i başlatın.
2. VPS üzerinde `http://SUNUCU_IP_ADRESINIZ:4283` veya yerel geliştirme için `http://127.0.0.1:4283` adresini açın.
3. Kontrolleri tamamlayıp sahip parolasını oluşturun. Uzak ilk kurulumdan önce en az 24 karakterli benzersiz `SETUP_TOKEN` veya `PANEL_PASSWORD` tanımlayın. Belirteç otomatik üretilmez veya günlüğe yazılmaz.
4. Providers sayfasından bir hesap, API anahtarı veya Ollama bağlantısı ekleyin.
5. Kimlik bilgilerini doğrulayın ve paneldeki bekleme süresi/hata durumunu izleyin. **Credentials** (`/credentials`).
6. Kodlama aracınızı yukarıdaki API yüzeylerinden birine yönlendirin.

Bir Google Antigravity kimlik bilgisi eklerken, oturum açtıktan sonra Google tarayıcıyı `http://localhost:4283/callback` adresine yönlendirir. Yerel bir makinede Polaris bir OAuth başarı sayfası gösterir. Bir VPS'de bu `localhost` adresi kullanıcının tarayıcı makinesine ait olduğundan sayfa yüklenmeyebilir; tarayıcı adres çubuğundaki tam URL'yi kopyalayın, Providers sayfasına dönün, `Callback URL` alanına yapıştırın ve `Save credential` butonuna tıklayın.

Google AI Studio, OAuth yerine API anahtarı kimlik doğrulaması kullanır. Providers sayfasından bir anahtar ekleyin; Polaris bunu Google'ın model kataloğuna karşı doğrular, bir sağlayıcı kimlik bilgisi olarak saklar ve uyumlu Gemini veya Gemma isteklerini bu anahtar üzerinden yönlendirir. Akıllı yönlendirici, paylaşılan Gemini modelleri için AI Studio ile Google Antigravity arasında yük devretme yapabilirken sağlayıcıya özgü modelleri uyumlu kimlik bilgilerinde tutar.

Google AI Studio toplu içe aktarma, JSON dosyalarını ve JSON dosyaları içeren ZIP arşivlerini kabul eder. Bir JSON belgesi tek bir anahtar, bir `api_keys` dizisi veya anahtar nesneleri dizisi içerebilir:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

Dosya içe aktarma çevrimdışıdır: Polaris JSON/ZIP yapısını denetler, yeni anahtarları `unverified` olarak kaydeder ve Google'a bağlanmadan yinelenen veya mevcut anahtarları atlar. İçe aktarılan model listeleri doğrulanmış sayılmaz. Biçim hataları anahtarlar açığa çıkarılmadan bildirilir. Ardından kimlik bilgisinin doğrulama/model keşfi işlemini açıkça çalıştırın; **Test model** çıkarım erişimini ayrıca denetler ve kota tüketebilir veya ücret doğurabilir.

Grok Build, PKCE OAuth kimlik bilgilerini desteklerken SpaceXAI Console, API anahtarlarını destekler. SpaceXAI Console anahtarları saklanmadan önce SpaceXAI Console API model kataloğuna karşı doğrulanır. Grok Build OAuth için Polaris bir yetkilendirme bağlantısı oluşturur; yetkilendirmeden sonra Grok Build yetkilendirme sayfasında görüntülenen kodu kopyalayın ve Grok Build OAuth formuna yapıştırın. Erişim belirteçleri bir yenileme belirteci (refresh token) mevcut olduğunda otomatik olarak yenilenir ve her iki kimlik bilgisi türü de yalnızca mevcut katalogları tarafından bildirilen modelleri sunar. Credentials sayfası, Grok Build OAuth hesapları için aylık kredi kullanımını ve xAI sağladığında haftalık kullanımı alabilir. Bu hesap düzeyinde faturalandırma görünümü SpaceXAI Console API anahtarları için kullanılamaz.

Codex, OpenAI'nin cihaz yetkilendirme akışını kullanır. Providers sayfasından bir cihaz kodu oluşturun, görüntülenen doğrulama URL'sini açın, kodu girin, oturum açmayı tamamlayın ve yetkilendirmeyi kontrol etmek için geri dönün. Polaris, Codex tarafından döndürülen hesap kapsamlı model kataloğunu saklar, gerektiğinde OAuth erişim belirteçlerini yeniler ve uyumlu istekleri Codex Responses aktarımı üzerinden gönderir. OpenAI Platform, API anahtarı kimlik doğrulaması kullanır; anahtarlar Credentials alanına girmeden önce hesap model kataloğu üzerinden doğrulanır. Her iki ürün de sağlayıcıya özel doğrulama ve tekilleştirme ile JSON ve ZIP içe aktarmayı destekler.

Claude Code, Anthropic'in PKCE OAuth akışını kullanır. Bir yetkilendirme bağlantısı oluşturun, yetkilendirmeyi tamamlayın, ardından döndürülen yetkilendirme kodunu Providers sayfasına yapıştırın. Claude Platform, Anthropic API anahtarlarını kabul eder. Her iki ürün de her kimlik bilgisine sunulan modelleri keşfeder, Anthropic Messages aktarımını kullanır, mümkün olduğunda Claude Code erişim belirteçlerini yeniler ve doğrulanmış JSON veya ZIP içe aktarmayı destekler.

Muse Code, Meta cihaz yetkilendirmesini kullanır. **Providers → Muse Code** içinden bağlantıyı alın, Meta'da kodu onaylayın ve **Save credential** işlemine dönün. CLI, Linux veya VPS olmadan doğrudan bağlanır; model öneki `muse-code/`, görünen ad isteğe bağlıdır. Plan, oturum/hafta kotası, sıfırlanma ve gözlem zamanı yalnızca sağlayıcı döndürürse gösterilir. Eksik veri %100 kaldığı anlamına gelmez. Yenileme mevcut oturumla aboneliği denetleyip çıkarım anahtarı alır; oturum geçersizse yeniden giriş gerekir.

Kiro, Google/GitHub tarayıcı OAuth, AWS cihaz yetkilendirmesi ve API anahtarı destekler. Gelişmiş alanlar yönteme bağlıdır: çalışma bölgesi, AWS belirteç bölgesi/başlangıç URL'si veya API anahtarı profil ARN'si.

Ollama bağlantıları uç nokta başına yapılandırılır ve korumalı veya bulut sunucuları için isteğe bağlı bir bearer API anahtarı içerebilir. Polaris modelleri `/api/tags` üzerinden keşfeder ve çıkarımı `/api/chat` üzerinden yönlendirir. Polaris Docker'da çalıştığında `localhost` konteynerin kendisini ifade eder; bir host-gateway adresi veya ağ üzerinden erişilebilen başka bir Ollama uç noktası kullanın.

Credentials içe aktarmaları ve Google Antigravity toplu içe aktarmaları 10 MB'a kadar arşivleri, en fazla 500 dosyayı, 2 MB'a kadar bireysel kimlik bilgisi dosyalarını ve en fazla 25 MB sıkıştırılmamış veriyi kabul eder. Google AI Studio, OpenAI, Anthropic ve Ollama sağlayıcı içe aktarmaları içe aktarılan dosya başına 2 MB, 200 JSON girişi ve 5 MB sıkıştırılmamış veri gibi daha katı sınırlar kullanır.

**Credentials** (`/credentials`) hesap ve anahtarları sağlayıcıya göre gruplar. Yönetim iletişim kutusu kimlik, model, durum ve kullanılabilir işlemleri gösterir. OAuth plan, kredi, zaman penceresi veya model bazında kota sağlayabilir. API anahtarları otomatik olarak e-posta, plan ya da fatura bilgisi sağlamaz; eksik veriler kullanılamaz kalır.

**Download ZIP** kimlik bilgilerini dışa aktarır; **Import ZIP** sağlayıcı bazında doğrulama ve tekilleştirme yapıp kayıt bazında hata bildirir. İçe aktarma veya katalog keşfi çıkarım erişimini kanıtlamaz. **Test model** gerçek çağrı yapar, kota tüketebilir veya ücret oluşturabilir. Arşivler sır içerir. Tüm SQLite ve ayarlar için **Settings** içindeki şifreli yedeği kullanın.

Google Antigravity kimlik bilgileri `google-antigravity-{account_fingerprint}.json` kullanır; burada parmak izi, açığa çıkarılmadan normalleştirilmiş hesap e-postasından türetilir. Google AI Studio kimlik bilgileri `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth kimlik bilgileri `grok-{account_fingerprint}.json`, SpaceXAI Console kimlik bilgileri `xai-console-{key_fingerprint}.json`, Codex kimlik bilgileri `openai-codex-{account_fingerprint}.json`, OpenAI Platform kimlik bilgileri `openai-platform-{key_fingerprint}.json`, Claude Code kimlik bilgileri `claude-code-{account_fingerprint}.json`, Claude Platform kimlik bilgileri `claude-platform-{key_fingerprint}.json` ve Ollama bağlantıları `ollama-{connection_fingerprint}.json` kullanır. Eski `provider_*.json` ve `xai-grok-*.json` kimlik bilgileri uyumlu kalmaya devam eder ve kurallı adlarla dışa aktarılır.

Kimlik bilgisi modu adları:

- `code_assist`: standart Code Assist kimlik bilgileri.
- `provider`: sağlayıcı arka uç kimlik bilgileri.

<a id="storage"></a>

## Depolama

SQLite önerilir. Compose `/app/backend/data` verisini `polaris-data` içinde saklar. Doğrudan Docker için `/app/backend/data/creds` ve `/app/backend/data/logs` yollarını `/opt/polaris/creds` ve `/opt/polaris/logs` gibi kalıcı dizinlere bağlayın.

PostgreSQL isteğe bağlıdır; MongoDB Redis olmadan uyumluluk için korunur. Yalnız birini yapılandırın. Başlatma hatası sessizce SQLite'a dönmek yerine süreci durdurur. Dış depolama yatay ölçekleme sağlamaz: tek worker, tek replika. Taşınabilir şifreli yedek yalnız SQLite içindir; arka uçlar arası canlı geçiş desteklenmez.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[Depolama](../storage.md)

Ortam kimlik bilgisi içe aktarma özelliği kontrol panelinden kullanılabilir. Aşağıdaki değişkenlerden birini ham JSON olarak ayarlayın veya base64 kodlu JSON için eşleşen `_B64` varyantını kullanın:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

Yük; tek bir kimlik bilgisi nesnesi, bir dizi veya `{ "credentials": [...] }` olabilir.

<a id="development"></a>

## Geliştirme

Bu bölüm katkıda bulunanlar ve yerel hata ayıklama içindir. Üretim dağıtımları kalıcı ana makine birimleriyle Docker kullanmalıdır.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

[Kalite kapıları](../quality-gates.md) görev, aşama ve sürümü ayırır. `python tools/quality_gate.py --list-suites` isteğe bağlı canlı dış kontrolleri de listeler. [Uyumluluk sözleşmesi](../compatibility.md) SDK/yönetim yollarını, geçişleri, şemaları ve örnekleri korur.

Kontroller geçtikten sonra hizmeti başlatın:

```bash
python backend/main.py
```

Üretim temeli Python 3.12'dir ve CI şu anda Python 3.12 ve 3.14'ü doğrulamaktadır. Pull request iş akışı ve inceleme beklentileri için [Katkıda Bulunma](../../CONTRIBUTING.md) belgesine bakın.

<a id="deployment-notes"></a>

## Dağıtım Notları

- Kimlik bilgisi JSON dosyalarını veya `.env` dosyasını asla commit etmeyin.
- İstemci entegrasyonları için özel bir `API_KEY` ve konsol erişimi için ayrı bir `PANEL_PASSWORD` kullanın.
- Kalıcı kimlik bilgisi birimine veya harici veritabanına erişimi kısıtlayın ve platform düzeyinde beklemede şifrelemeyi (encryption at rest) etkinleştirin; sağlayıcı belirteçleri yönlendirici tarafından alınabilir kalmalıdır.
- Localhost dışından erişilebildiğinde Polaris'i TLS özellikli bir ters proxy'nin arkasına yerleştirin.
- Ters proxy'yi `Host` başlığını koruyacak ve `X-Forwarded-Proto` başlığını iletecek şekilde yapılandırın; HTTPS sonlandırması garanti edildiğinde `PANEL_COOKIE_SECURE=true` ayarlayın.
- `TRUST_PROXY_HEADERS=true` ayarını yalnızca hizmete `X-Forwarded-For` ve `X-Forwarded-Proto` başlıklarının üzerine yazan güvenilir bir proxy aracılığıyla erişildiğinde etkinleştirin.
- Süreç canlılığı için `GET /health` ve depolamaya duyarlı hazırlık kontrolleri için `GET /ready` kullanın.
- Dış telemetri isteğe bağlıdır. Prometheus için `PROMETHEUS_EXPORT_ENABLED` ve güçlü `METRICS_TOKEN` gerekir; OpenTelemetry yalnız toplamları aktarır, istem/yanıt içeriğini aktarmaz. [Gözlemlenebilirliğe](../observability.md) bakın.
- Docker imajı, yalnızca bağlı veri dizini sahipliğini onaracak kadar kök (root) kullanıcı olarak başlar, ardından hizmeti ayrıcalıksız `gateway` kullanıcısı olarak çalıştırır.
- Tarayıcı istemcileri kaynaklar arası erişime ihtiyaç duyduğunda `CORS_ORIGINS` değişkenini açıkça güvenilir kaynaklara ayarlayın.
- SQLite güncelleme veya taşıma öncesinde [kimliği doğrulanmış şifreli yedek](../backup-and-restore.md) kullanın; arşiv ve parolayı `polaris-data` dışında saklayın.
- Docker imaj yayını; Docker Hub için `DOCKERHUB_USERNAME` ve `DOCKERHUB_TOKEN` depo sırlarını, `ghcr.io/nguywnben/polaris` adresindeki GitHub Packages için yerleşik `GITHUB_TOKEN` kullanır. İsteğe bağlı `IMAGE_NAME` depo değişkenini yalnızca özel bir Docker Hub imaj adına yayınlarken ayarlayın.
- 1.x serisi için `WORKERS=1` ve tek bir uygulama kopyası tutun; harici depolama dağıtılmış koordinasyonun yerine geçmez.
- Kurallı `/api/credentials` yönetim rotalarını kullanın. Beta `/api/creds` takma adları 1.0.0 sürümünde kaldırılmıştır.
- Bir beta dağıtımını taşımadan önce [1.0'a Yükseltme](../upgrading-to-1.0.md) kılavuzunu izleyin.
- Dağıtılmış bir örneği yükseltirken veya bir sürümü geri alırken [güncelleme kılavuzunu](../updating.md) izleyin.
- Bir imajı etiketlemeden veya yükseltmeden önce bakımı yapılan [sürüm kontrol listesini](../release-checklist.md) izleyin.
- Günlük saklama ve kimlik bilgisi rotasyon politikalarını kullanım sınırlarınızla uyumlu tutun.
- Bir depo veya platform tarayıcısı sızdırılmış bir sır bildirirse kimlik bilgilerini derhal değiştirin.
- Render Blueprint, kalıcı diske sahip ücretli bir hizmet kullanır. Render ücretsiz hizmetleri geçici dosya sistemleri kullanır ve yalnızca tek kullanımlık değerlendirmeler için uygundur.

<a id="community-and-project-health"></a>

## Topluluk ve Proje Sağlığı

- Bir pull request açmadan önce [Katkıda Bulunma](../../CONTRIBUTING.md) kılavuzunu okuyun.
- Güvenlik açıklarını [Güvenlik Politikası](../../SECURITY.md) içindeki özel süreç aracılığıyla bildirin.
- Sürüm düzeyindeki değişiklikler için [Değişiklik Günlüğü](../../CHANGELOG.md) belgesini inceleyin.
- Tüm proje alanlarında [Davranış Kuralları](../../CODE_OF_CONDUCT.md) ilkelerine uyun.

<a id="acknowledgements-inspirations"></a>

## Teşekkürler & İlham Kaynakları

Polaris, açık kaynaklı yapay zeka yönlendirme, telemetri ve ağ geçidi topluluğunun omuzlarında yükselmektedir. Bu projelerin yaratıcılarına ve yöneticilerine şükranlarımızı sunarız:

| Proje | Açıklama | Yıldız |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Çok sağlayıcılı anahtar yönetimi ve web tabanlı API toplama ilhamı | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | AI kodlama CLI'ları için öncü çok formatlı proxy ve protokol dönüştürme katmanı | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Standart belirleyen birleşik LLM proxy'si, yük dengeleme ve yük devretme yönlendirmesi | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Ultra hızlı AI ağ geçidi mimarisi, yönlendirme stratejileri ve dayanıklı yük devretme kalıpları | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Açık kaynaklı LLM mühendislik platformu, izleme (tracing), gözlemlenebilirlik ve metrik alımı | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## Lisans

Polaris, [MIT Lisansı](../../LICENSE) altında yayınlanmıştır.
