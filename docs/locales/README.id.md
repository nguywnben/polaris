<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Universal AI Router & Gateway Multi-Penyedia Terpadu untuk Alat AI Coding</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">Penyedia yang Didukung</a> • <a href="#core-capabilities">Kemampuan Utama</a> • <a href="#deployment">Penerapan</a> • <a href="#sdk-surfaces">Antarmuka SDK</a> • <a href="#architecture">Arsitektur</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <b>Bahasa Indonesia</b> • <a href="README.th.md">ภาษาไทย</a> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

README ini tersedia dalam 15 bahasa dengan cakupan fungsi yang sama. Panduan tertaut tetap menggunakan bahasa aslinya.

Router AI universal untuk alat pemrograman. Polaris menyediakan auto-fallback cerdas, pembersihan permintaan sadar token, visibilitas penggunaan, dan penerjemahan format mulus sehingga agen lokal, asisten IDE, dan skrip otomatisasi dapat menggunakan kapasitas LLM gratis dan premium melalui satu permukaan API yang stabil.

> Polaris mendukung hosting mandiri untuk individu atau tim tepercaya dengan satu worker dan satu replika. Docker Compose, pemilik lokal, SQLite, perutean, dan antarmuka SDK terdokumentasi merupakan inti. PostgreSQL, OIDC, reverse proxy, dan telemetri eksternal bersifat opsional; MongoDB dipertahankan untuk kompatibilitas. Koordinasi banyak replika dan Kubernetes tidak didukung. [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## Mengapa Polaris

Alur kerja coding modern sering menggabungkan berbagai klien dan penyedia: alat yang kompatibel dengan OpenAI, SDK native Gemini, agen gaya Anthropic, kredensial berbasis Google, dan rute model eksperimental. Polaris berada di antara klien-klien tersebut dan backend model sehingga setiap alat dapat terus berbicara dalam format yang sudah dipahaminya, sementara gateway menangani perutean, percobaan ulang (retry), pembersihan permintaan, dan normalisasi respons.

<a id="core-capabilities"></a>

## Kemampuan Utama

- Failover otomatis dengan reservasi per permintaan, rotasi adil, jeda, dan penanganan kuota habis.
- Pembersihan riwayat panjang sambil mempertahankan instruksi sistem, alat, dan percakapan terbaru.
- Konversi OpenAI Chat Completions/Responses, Gemini, dan Anthropic Messages termasuk streaming.
- Pengelolaan akun OAuth dan kunci API dengan verifikasi serta deduplikasi per penyedia.
- Katalog model per kredensial sesuai hak akses akun.
- Pencatatan rute model yang tidak tersedia dan pemulihan dari Models.
- SSE, pseudo-streaming, dan percobaan ulang terbatas untuk respons terpotong.
- Perutean seimbang, prioritas, berbobot, latensi terendah, atau biaya terendah.
- Kunci virtual dengan anggaran harian/bulanan, RPM/TPM, kedaluwarsa, dan model yang diizinkan.
- Estimasi biaya USD per panggilan dengan agregasi dasbor dan Prometheus.
- Perlindungan opsional terhadap injeksi prompt, kata terlarang, dan data pribadi.
- Cache opsional untuk respons deterministik dengan kecocokan persis.
- Prometheus, ekspor Langfuse opsional, dan pelacakan penggunaan.
- Konsol untuk kredensial, log, konfigurasi, penggunaan, dan versi.

<a id="console-preview"></a>

## Pratinjau Konsol

Tangkapan layar menggunakan data fiktif dari demo luring yang terisolasi.

### Dasbor

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — Dasbor" />
</picture>

### Kredensial

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — Pratinjau Konsol" />
</picture>

<a id="supported-providers"></a>

## Penyedia yang Didukung

Katalog mencakup 23 penyedia. Model dan fitur yang tersedia bergantung pada izin masing-masing kredensial.

| Penyedia | Koneksi | Layanan / cakupan |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | Kunci API | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | Kunci API | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (kode perangkat) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | Kunci API | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | Kunci API | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Endpoint; kunci API opsional | Lokal / hosting mandiri |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | Kunci API | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | Token API + ID akun | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | Kunci API | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | Kunci API | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | Kunci API; ID organisasi opsional | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | Kunci API / layanan | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | Kunci API | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | OAuth browser / perangkat AWS / kunci API | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (perangkat Meta) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | Kunci API | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | Kunci API | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | Kunci API | Inferensi terkelola NVIDIA |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | Kunci API + paket Zen/Go | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | Kunci API | Poolside API |

Klien menggunakan [antarmuka SDK](#sdk-surfaces) bersama. Konversi, streaming, dan failover bergantung pada kemampuan model; opsi yang tidak kompatibel ditolak secara eksplisit. Atur koneksi per penyedia atau kredensial di **Providers**. Muse Code dan Meta Model API memiliki kredensial serta ruang nama model terpisah.

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## Arsitektur

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | Integrasi IDE
        |
        v
Polaris
  autentikasi -> penerjemahan format -> pembersihan sadar token -> perutean -> fallback -> streaming
        |
        v
provider adapters
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

API publik tetap stabil sementara adaptor khusus penyedia berkembang di balik Polaris.

<a id="repository-structure"></a>

## Struktur Repositori

```text
backend/       FastAPI composition root, inti perutean, penerjemah, penyimpanan, dan pengujian
frontend/      Markup konsol manajemen, gaya, skrip, dan aset penyedia
deploy/        Definisi kontainer, manifes platform, dan skrip sistem operasi
docs/          Catatan arsitektur dan aset proyek yang dipelihara
.github/       CI, otomatisasi dependensi, dan template kontribusi
```

Lihat [Arsitektur](../architecture.md) untuk batasan modul, alur permintaan, kepemilikan status, dan batasan rilis saat ini.

<a id="deployment"></a>

## Penerapan

Docker Compose pada satu mesin dan satu worker adalah jalur utama. Ikuti [instalasi](../installation.md) dan [matriks dukungan](../installation.md#support-matrix).

Profil dasar tidak memerlukan layanan eksternal dan menyimpan data dalam `polaris-data`. Templat menargetkan `1.0.0`. Instal hanya dengan tag dan image Polaris yang telah dirilis dan memiliki versi sama; untuk kode sumber yang belum dirilis, buat image lokal terpisah sesuai [daftar periksa rilis](../releases/1.0.0-preparation.md). Ikuti [pembaruan dan rollback](../updating.md); fitur lanjutan bersifat opsional melalui `deploy/compose.advanced.yml`.

Lihat [kontrak pengenal](../migrations/polaris.md) dan [pemecahan masalah](../troubleshooting.md). Skrip native, `docker run`, Render, dan Zeabur adalah jalur kompatibilitas tanpa verifikasi instalasi/pemulihan yang setara. Image diterbitkan untuk `linux/amd64`; publikasi `linux/arm64` masih ditangguhkan.

### Pengembangan atau diagnosis lokal:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

Di Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Buka konsol; penyiapan awal sama dengan Docker:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## Konfigurasi

Prioritas: variabel lingkungan, konfigurasi tersimpan, lalu nilai bawaan. [Referensi yang dihasilkan](../reference/configuration.md) memuat tipe, grup, penanggung jawab, dan penerapan langsung, setelah restart, atau khusus lingkungan. Nilai tidak valid menghentikan startup dan menunjukkan variabelnya; kemungkinan salah ketik `POLARIS_*` diberi peringatan.

| Variabel | Default | Tujuan |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Alamat ikat (bind address). |
| `PORT` | `4283` | Port HTTP. |
| `HOST_PORT` | `4283` | Port sisi host yang hanya digunakan oleh Docker Compose. |
| `WORKERS` | `1` | Hanya satu worker didukung. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Hanya `standalone` didukung. |
| `POLARIS_REPLICA_COUNT` | `1` | Hanya satu replika didukung. |
| `CORS_ORIGINS` | kosong | Asal (origin) peramban yang dipisahkan koma yang diizinkan memanggil API lintas-asal (cross-origin). Biarkan kosong untuk penggunaan konsol origin yang sama. |
| `CORS_ORIGIN_REGEX` | kosong | Regex opsional untuk origin peramban dinamis yang dikelola. |
| `API_KEY` | dibuat otomatis | Kunci API klien dengan awalan `sk-polaris-`. |
| `PANEL_PASSWORD` | kosong sampai penyiapan | Kata sandi untuk panel kontrol web. |
| `SETUP_TOKEN` | kosong | Token penyiapan jarak jauh unik minimal 24 karakter; tidak dibuat atau dicatat otomatis. Tidak diperlukan pada localhost langsung. |
| `SETUP_ALLOW_INSECURE_HTTP` | `false` | Izinkan penyiapan jarak jauh melalui HTTP hanya jika menerima risiko kredensial dan sesi tanpa enkripsi. HTTPS disarankan; token penyiapan yang kuat tetap diperlukan. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Masa berlaku sesi konsol web dalam detik. |
| `PANEL_COOKIE_SECURE` | otomatis | Tetapkan `true` untuk mewajibkan cookie panel hanya melalui HTTPS. Biarkan kosong untuk mendeteksi HTTPS melalui `X-Forwarded-Proto`. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Jendela pembatasan laju login dalam detik. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Percobaan login gagal maksimum yang diizinkan per klien dalam jendela pembatasan laju. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Alamat klien maksimum yang disimpan oleh pembatas login dalam memori. |
| `MAX_REQUEST_BODY_MB` | `64` | Ukuran tubuh permintaan HTTP maksimum dalam MiB. Permintaan SDK yang terlalu besar mengembalikan amplop kesalahan protokol native. |
| `TRUST_PROXY_HEADERS` | `false` | Hanya terima header penerusan klien/protokol dari reverse proxy tepercaya yang menimpanya. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Direktori penyimpanan kredensial. Di Docker, pertahankan `/app/backend/data/creds` dengan volume host. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Endpoint backend Code Assist. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Endpoint backend Google Antigravity. |
| `PROXY` | kosong | Proksi HTTP, HTTPS, atau SOCKS opsional. |
| `RETRY_429_ENABLED` | `true` | Aktifkan percobaan ulang terbatas untuk batas laju dan kegagalan sementara upstream. Nama lama dipertahankan untuk kompatibilitas konfigurasi. |
| `RETRY_429_MAX_RETRIES` | `5` | Upaya percobaan ulang maksimum untuk kegagalan sementara upstream. |
| `RETRY_429_INTERVAL` | `1` | Penundaan dasar antar percobaan ulang sementara dalam detik. |
| `AUTO_DISABLE` | `false` | Nonaktifkan kredensial setelah kegagalan berat (hard failure) yang dikonfigurasi. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Kode status kegagalan berat yang dipisahkan koma. |
| `ROUTING_STRATEGY` | `balanced` | Strategi: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost`. |
| `PREFERRED_PROVIDER` | kosong | Penyedia yang disukai oleh strategi `priority`, seperti `google_antigravity` atau `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Batas waktu inferensi penyedia, dibatasi antara 5 dan 900 detik. |
| `RESPONSE_CACHE_ENABLED` | `false` | Cache memori untuk respons deterministik non-streaming, suhu 0. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Masa berlaku cache dalam detik. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Jumlah maksimum respons cache. |
| `GUARDRAILS_ENABLED` | `false` | Aktifkan perlindungan sebelum panggilan. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Samarkan email, kartu, dan kunci API dalam teks keluar. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Tolak injeksi prompt dengan HTTP 400. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | kosong | Kata terlarang dipisahkan koma, tanpa membedakan huruf besar/kecil. |
| `PRICING_SYNC_ENABLED` | `true` | Perbarui harga LiteLLM di latar belakang; simpan salinan valid terakhir saat offline. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Interval harga: 1–168 jam. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Upaya kelanjutan maksimum untuk streaming anti-pemotongan. |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Kompres riwayat percakapan yang terlalu besar sebelum perutean ke penyedia. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Ambang perkiraan token input yang mengaktifkan kompresi. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Target perkiraan token input setelah kompresi. Harus lebih rendah dari ambang batas. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Jumlah minimum giliran pengguna terkini yang dipertahankan selama kompresi. |
| `COMPATIBILITY_MODE` | `false` | Mengonversi pesan sistem untuk klien/model yang menolaknya. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Sertakan bidang penalaran (reasoning) model jika tersedia. |
| `MONGODB_URI` | kosong | Penyimpanan MongoDB kompatibilitas. |
| `POSTGRESQL_URI` | kosong | Penyimpanan PostgreSQL opsional. |
| `CODE_ASSIST_CLIENT_ID` | klien desktop bawaan | Penimpaan opsional untuk Client ID OAuth Code Assist. |
| `CODE_ASSIST_CLIENT_SECRET` | klien desktop bawaan | Penimpaan opsional untuk Client Secret OAuth Code Assist. |
| `ANTIGRAVITY_CLIENT_ID` | klien desktop bawaan | Penimpaan opsional untuk Client ID OAuth Google Antigravity. Juga dapat dikelola dari halaman Providers. |
| `ANTIGRAVITY_CLIENT_SECRET` | klien desktop bawaan | Penimpaan opsional untuk Client Secret OAuth Google Antigravity. Konfigurasikan melalui env atau halaman Providers saat klien upstream berubah. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Penimpaan opsional untuk endpoint Google AI Studio Generative Language API. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Penimpaan opsional untuk endpoint API SpaceXAI Console untuk kredensial kunci API. Juga dapat dikelola dari halaman Providers. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Penimpaan opsional untuk endpoint langganan OAuth Grok Build. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Penimpaan opsional untuk penerbit OAuth Grok Build. Hanya host HTTPS di bawah `x.ai` yang diterima oleh konsol. |
| `XAI_CLIENT_ID` | klien publik bawaan | Penimpaan opsional untuk Client ID OAuth PKCE Grok Build. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Penimpaan opsional HTTP User-Agent bersama untuk permintaan Grok Build OAuth dan SpaceXAI Console API. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Penimpaan opsional untuk endpoint OpenAI Platform API. Juga dapat dikelola dari halaman Providers. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Penimpaan opsional untuk endpoint inferensi dan model akun Codex. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Penimpaan opsional untuk endpoint batas laju akun Codex. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Penimpaan opsional untuk layanan otorisasi perangkat Codex. |
| `CODEX_CLIENT_ID` | klien publik bawaan | Penimpaan opsional untuk Client ID OAuth perangkat Codex. |
| `CODEX_USER_AGENT` | nilai kompatibel Codex CLI | Penimpaan opsional User-Agent untuk permintaan Codex. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Endpoint Messages khusus Claude Code. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Penimpaan opsional untuk endpoint otorisasi PKCE Claude Code. Hanya host Anthropic dan Claude yang diterima oleh konsol. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Penimpaan opsional untuk endpoint token Claude Code. Hanya host Anthropic dan Claude yang diterima oleh konsol. |
| `CLAUDE_CLIENT_ID` | klien publik bawaan | Penimpaan opsional untuk Client ID OAuth PKCE Claude Code. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | User-Agent khusus Claude Code. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Endpoint Claude Platform terpisah di Providers. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | User-Agent Claude Platform independen. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Penimpaan opsional protokol User-Agent Google Antigravity. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Penimpaan opsional userAgent tingkat payload Google Antigravity. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Aktifkan `GET /metrics` terautentikasi. |
| `METRICS_TOKEN` | kosong | Token Bearer minimal 32 byte UTF-8 untuk Prometheus. |
| `OTEL_EXPORT_ENABLED` | `false` | Aktifkan ekspor agregat OTLP/HTTP tanpa isi. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | kosong | Collector HTTPS; kredensial dalam URL dilarang. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Interval ekspor: 15–300 detik. |
| `LANGFUSE_PUBLIC_KEY` | kosong | Aktifkan Langfuse bersama kunci rahasia. |
| `LANGFUSE_SECRET_KEY` | kosong | Kunci rahasia Langfuse untuk trace. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Endpoint penerimaan Langfuse. |
| `LOG_LEVEL` | `info` | Tingkat log runtime. |
| `LOG_MAX_MB` | `10` | Ukuran file log aktif maksimum sebelum rotasi. |
| `LOG_BACKUP_COUNT` | `3` | Jumlah file log terotasi yang dipertahankan. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | Tujuan file log. Di Docker, pertahankan `/app/backend/data/logs` dengan volume host. |

### Kontrol kompresi

Kebijakan global AI Quality menjadi batas utama. Kunci hanya dapat mewarisi atau menonaktifkan kompresi melalui `PATCH /api/virtual-keys/{key_id}/quality-policy` dengan revisi saat ini; `inherit` menghapus pembatasan kunci. Permintaan terautentikasi dapat mengirim `x-polaris-compression: off`; tanpa header atau `inherit` mengikuti kebijakan global/kunci. Permintaan tidak dapat mengaktifkan kembali kompresi yang dilarang atau membuatnya lebih agresif. Hanya awalan riwayat yang aman dihapus; jika struktur atau estimasi tidak pasti, permintaan dikirim utuh. Jumlah token merupakan estimasi.

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## Antarmuka SDK

Polaris dirancang berdasarkan perilaku URL standar dari Python SDK resmi. Konfigurasikan setiap klien persis seperti yang ditunjukkan di bawah ini; gateway tidak memerlukan awalan jalur duplikat non-standar.

Contoh-contoh ini menggunakan model virtual `polaris`. Konfigurasikan urutan fallback penyedia-model pada halaman Models terlebih dahulu, atau ganti dengan ID model konkret.

### OpenAI Python SDK

Gunakan `/v1` sebagai base URL OpenAI. SDK akan menambahkan `/chat/completions`.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Jelaskan repositori ini dalam satu paragraf."}],
)
```

Klien yang sama dapat menggunakan OpenAI Responses API:

```python
response = client.responses.create(
    model="polaris",
    instructions="Jadilah ringkas.",
    input="Jelaskan repositori ini dalam satu paragraf.",
)

print(response.output_text)
```

Kompatibilitas Responses mendukung teks, input gambar, non-streaming function tools, dan SSE text streaming. Alat bawaan yang dihosting OpenAI, riwayat respons tersimpan, dan streaming function calls ditolak secara eksplisit karena Polaris tidak mengeksekusi, mempertahankan, atau secara diam-diam membuang perilaku khusus OpenAI tersebut.

### Anthropic Python SDK

Gunakan origin gateway sebagai base URL Anthropic. SDK akan menambahkan `/v1/messages`.

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Draf pesan komit."}],
)
```

### Google GenAI Python SDK

Gunakan origin gateway sebagai base URL Google GenAI. SDK akan menambahkan rute model defaultnya, seperti `/v1beta/models/{model}:generateContent`.

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
    contents="Tulis sebuah fungsi Python kecil.",
    config=types.GenerateContentConfig(
        system_instruction="Anda adalah asisten yang membantu.",
    ),
)
```

### Rute yang Didukung

Polaris mengekspos rute yang kompatibel dengan SDK tanpa namespace produk:

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

Kegagalan autentikasi, validasi permintaan, perutean, upstream, dan pra-streaming menggunakan amplop kesalahan native untuk antarmuka SDK yang dipilih. Setiap respons HTTP menyertakan `X-Request-ID`; klien dapat memberikan pengidentifikasi aman dalam header tersebut untuk korelasi menyeluruh (end-to-end). Respons yang dibatasi laju atau sementara tidak tersedia mempertahankan `Retry-After` ketika upstream menyediakannya.

<a id="model-features"></a>

## Fitur Model

Halaman Models membangun model virtual `polaris` dari model yang ditemukan di seluruh kredensial penyedia yang diaktifkan. Atur anggotanya dalam urutan prioritas satu kali, lalu gunakan `polaris` dari SDK yang didukung. Polaris menyeimbangkan kredensial sehat yang mendukung model pertama dan melanjutkan melalui urutan model yang dikonfigurasi saat model tersebut tidak tersedia. ID model penyedia konkret tetap tersedia untuk klien yang memerlukan pemilihan model deterministik. Menyimpan pilihan kosong akan menonaktifkan `polaris` tanpa memengaruhi kredensial penyedia.

Penemuan model berbasis penyedia: model bersama dapat didukung oleh beberapa penyedia, sementara model khusus penyedia hanya menggunakan kredensial yang kompatibel. Setiap kredensial terverifikasi menyimpan katalog penyedianya sendiri, dan router memberikan prioritas dukungan kredensial yang dinyatakan di atas inferensi penyedia umum. Menyegarkan katalog akan memeriksa ulang ketersediaan penyedia saat ini; pilihan yang tidak tersedia tetap terlihat dalam konfigurasi sampai dipulihkan atau dihapus.

Ketika upstream mengembalikan `404` untuk model konkret, Polaris mencatat rute yang tidak tersedia untuk kredensial dan model tersebut alih-alih menekan seluruh penyedia. Rute tersebut langsung dihindari untuk sementara dan tetap terlihat di bawah **Unavailable Model Routes** sampai dihapus atau kredensial divalidasi ulang. Ini mencegah langganan atau hak regional satu akun memengaruhi akun lain di penyedia yang sama. Jika tidak ada kredensial yang diaktifkan menyatakan atau dapat menyimpulkan dukungan untuk model konkret yang diminta, gateway mengembalikan kesalahan kredensial-tidak-kompatibel yang jelas alih-alih mengirim permintaan ke penyedia acak.

Polaris mengenali awalan dan akhiran fitur dalam nama model:

- `fake-streaming/{model}` atau awalan pseudo-streaming yang dikonfigurasi untuk klien yang memerlukan output SSE.
- `streaming-anti-truncation/{model}` atau awalan anti-pemotongan yang dikonfigurasi untuk pemulihan streaming bentuk panjang.
- Akhiran pemikiran seperti `-high`, `-medium`, `-low`, `-minimal`, dan `-max` untuk model keluarga Gemini yang didukung.
- Akhiran pencarian seperti `-search` untuk model yang mendukung grounding Google Search.

Adaptor penyedia menormalkan nama fitur ini sebelum mengirim permintaan ke upstream.

<a id="usage-and-cost-visibility"></a>

## Penggunaan dan Visibilitas Biaya

Setiap percobaan penyedia, retry, dan failover dihitung terpisah; trace menyimpan hasil akhir permintaan logis. Hasil, kredensial, token input/output/cache/penalaran yang dilaporkan, penghematan estimasi, dan biaya USD dicatat. Penggunaan yang hilang bukan nol terukur. Periode memakai batas tetap zona waktu browser; tampilan hari mencakup 00:00–23:00. Harga publik LiteLLM diperbarui saat startup dan setiap 24 jam secara bawaan, mempertahankan salinan valid terakhir secara atomik. Kegagalan tidak memblokir inferensi. `model_pricing.json` dalam direktori kredensial diprioritaskan; harga per sejuta token. Agregat tersedia di dasbor, `/api/virtual-keys`, dan `/metrics`. Tagihan serta tokenizer penyedia tetap menjadi acuan.

Kunci virtual mendukung anggaran harian/bulanan, jendela bergeser RPM/TPM, kedaluwarsa, dan pola glob model. Hanya hash SHA-256 disimpan; rahasia ditampilkan sekali saat dibuat.

<a id="credential-workflow"></a>

## Alur Kerja Kredensial

1. Mulai Polaris.
2. Buka `http://IP_SERVER_ANDA:4283` di VPS, atau `http://127.0.0.1:4283` untuk pengembangan lokal.
3. Selesaikan pemeriksaan dan buat kata sandi pemilik. Sebelum penyiapan jarak jauh, tetapkan `SETUP_TOKEN` unik minimal 24 karakter atau `PANEL_PASSWORD`. Token tidak dibuat atau dicatat otomatis.
4. Tambahkan akun, kunci API, atau koneksi Ollama dari halaman Providers.
5. Verifikasi kredensial dan pantau status cooldown/kesalahan di panel. **Credentials** (`/credentials`).
6. Arahkan alat coding Anda ke salah satu antarmuka API di atas.

Saat menambahkan kredensial Google Antigravity, Google mengarahkan peramban ke `http://localhost:4283/callback` setelah masuk. Pada mesin lokal, Polaris menampilkan halaman keberhasilan OAuth. Pada VPS, alamat `localhost` tersebut milik mesin peramban pengguna, sehingga halaman mungkin tidak dapat dimuat; salin URL lengkap dari bilah alamat peramban, kembali ke halaman Providers, tempel ke `Callback URL`, dan klik `Save credential`.

Google AI Studio menggunakan autentikasi kunci API alih-alih OAuth. Tambahkan kunci dari halaman Providers; Polaris memvalidasinya terhadap katalog model Google, menyimpannya sebagai kredensial penyedia, dan merutekan permintaan Gemini atau Gemma yang kompatibel melaluinya. Router cerdas dapat melakukan fallback antara AI Studio dan Google Antigravity untuk model Gemini bersama sambil mempertahankan model khusus penyedia pada kredensial yang kompatibel.

Impor massal Google AI Studio menerima file JSON dan arsip ZIP yang berisi file JSON. Dokumen JSON dapat berisi satu kunci, larik `api_keys`, atau larik objek kunci:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

Impor berkas dilakukan secara offline: Polaris memeriksa struktur JSON/ZIP, menyimpan kunci baru sebagai `unverified`, dan melewati kunci duplikat atau yang sudah ada tanpa menghubungi Google. Daftar model yang diimpor tidak dianggap terverifikasi. Kesalahan format dilaporkan tanpa mengungkap kunci. Setelah itu, jalankan verifikasi/penemuan model kredensial secara eksplisit; **Test model** memeriksa akses inferensi secara terpisah dan dapat memakai kuota atau menimbulkan biaya.

Grok Build mendukung kredensial PKCE OAuth, sedangkan SpaceXAI Console mendukung kunci API. Kunci SpaceXAI Console divalidasi terhadap katalog model API SpaceXAI Console sebelum disimpan. Untuk Grok Build OAuth, Polaris menghasilkan tautan otorisasi; setelah otorisasi, salin kode yang ditampilkan pada halaman otorisasi Grok Build dan tempelkan ke dalam formulir Grok Build OAuth. Token akses diperbarui secara otomatis saat refresh token tersedia, dan kedua jenis kredensial hanya mengekspos model yang dinyatakan oleh katalog masing-masing. Halaman Credentials dapat mengambil penggunaan kredit bulanan dan, ketika xAI menyediakannya, penggunaan mingguan untuk akun Grok Build OAuth. Tampilan penagihan tingkat akun ini tidak tersedia untuk kunci API SpaceXAI Console.

Codex menggunakan alur otorisasi perangkat OpenAI. Hasilkan kode perangkat dari halaman Providers, buka URL verifikasi yang ditampilkan, masukkan kode, selesaikan proses masuk, dan kembali untuk memeriksa otorisasi. Polaris menyimpan katalog model cakupan akun yang dikembalikan oleh Codex, menyegarkan token akses OAuth saat diperlukan, dan mengirim permintaan yang kompatibel melalui transportasi Codex Responses. OpenAI Platform menggunakan autentikasi kunci API; kunci divalidasi melalui katalog model akun sebelum disimpan di Credentials. Kedua produk mendukung impor JSON dan ZIP dengan validasi khusus penyedia dan deduplikasi.

Claude Code menggunakan alur Anthropic PKCE OAuth. Buat tautan otorisasi, selesaikan otorisasi, lalu tempelkan kode otorisasi yang dikembalikan ke halaman Providers. Claude Platform menerima kunci API Anthropic. Kedua produk menemukan model yang diekspos ke setiap kredensial, menggunakan transportasi Anthropic Messages, menyegarkan token akses Claude Code jika memungkinkan, dan mendukung impor JSON atau ZIP yang divalidasi.

Muse Code memakai otorisasi perangkat Meta. Di **Providers → Muse Code**, ambil tautan, setujui kode di Meta, lalu kembali ke **Save credential**. Koneksi langsung tanpa CLI, Linux, atau VPS; awalan model `muse-code/` dan nama tampilan opsional. Paket, kuota sesi/mingguan, waktu reset, dan waktu pengamatan hanya ditampilkan jika dikembalikan penyedia. Data hilang tidak berarti tersisa 100%. Penyegaran memeriksa langganan dan memperoleh kunci inferensi dengan sesi aktif; masuk kembali jika sesi tidak valid.

Kiro mendukung OAuth browser Google/GitHub, perangkat AWS, dan kunci API. Opsi lanjutan mengikuti metode: wilayah runtime, wilayah token/URL awal AWS, atau ARN profil kunci API.

Koneksi Ollama dikonfigurasi per endpoint dan dapat menyertakan kunci API pembawa (bearer) opsional untuk server yang dilindungi atau di cloud. Polaris menemukan model melalui `/api/tags` dan merutekan inferensi melalui `/api/chat`. Saat Polaris berjalan di Docker, `localhost` mengacu pada kontainer itu sendiri; gunakan alamat host-gateway atau endpoint Ollama lain yang dapat dijangkau jaringan.

Impor Credentials dan impor massal Google Antigravity menerima arsip hingga 10 MB, paling banyak 500 file, file kredensial individual hingga 2 MB, dan paling banyak 25 MB data yang tidak dikompresi. Impor penyedia Google AI Studio, OpenAI, Anthropic, dan Ollama menggunakan batas yang lebih ketat yaitu 2 MB per file yang diimpor, 200 entri JSON, dan 5 MB data yang tidak dikompresi.

**Credentials** (`/credentials`) mengelompokkan akun dan kunci per penyedia. Dialog pengelolaan menampilkan identitas, model, status, dan tindakan yang tersedia. OAuth dapat memberikan paket, kredit, serta kuota per jendela atau model. Kunci API tidak otomatis memberikan email, paket, atau tagihan; data yang hilang tetap tidak tersedia.

**Download ZIP** mengekspor kredensial; **Import ZIP** memvalidasi dan menghapus duplikat per penyedia, dengan kesalahan per entri. Impor atau penemuan katalog tidak membuktikan akses inferensi. **Test model** membuat panggilan nyata yang dapat menghabiskan kuota atau dikenai biaya. Arsip berisi rahasia. Gunakan cadangan terenkripsi di **Settings** untuk seluruh SQLite dan konfigurasi.

Kredensial Google Antigravity menggunakan `google-antigravity-{account_fingerprint}.json`, di mana sidik jari diturunkan dari email akun yang dinormalisasi tanpa mengeksposnya. Kredensial Google AI Studio menggunakan `google-ai-studio-{key_fingerprint}.json`, kredensial Grok Build OAuth menggunakan `grok-{account_fingerprint}.json`, kredensial SpaceXAI Console menggunakan `xai-console-{key_fingerprint}.json`, kredensial Codex menggunakan `openai-codex-{account_fingerprint}.json`, kredensial OpenAI Platform menggunakan `openai-platform-{key_fingerprint}.json`, kredensial Claude Code menggunakan `claude-code-{account_fingerprint}.json`, kredensial Claude Platform menggunakan `claude-platform-{key_fingerprint}.json`, dan koneksi Ollama menggunakan `ollama-{connection_fingerprint}.json`. Kredensial lama `provider_*.json` dan `xai-grok-*.json` tetap kompatibel dan diekspor dengan nama kanonikal.

Nama mode kredensial:

- `code_assist`: kredensial Code Assist standar.
- `provider`: kredensial backend penyedia.

<a id="storage"></a>

## Penyimpanan

SQLite direkomendasikan. Compose menyimpan `/app/backend/data` dalam `polaris-data`; pada Docker langsung, mount `/app/backend/data/creds` dan `/app/backend/data/logs` ke direktori persisten seperti `/opt/polaris/creds` dan `/opt/polaris/logs`.

PostgreSQL opsional; MongoDB dipertahankan untuk kompatibilitas tanpa Redis. Konfigurasikan hanya satu. Kegagalan inisialisasi menghentikan startup tanpa diam-diam kembali ke SQLite. Penyimpanan eksternal tidak menyediakan skala horizontal: tetap satu worker dan satu replika. Cadangan terenkripsi portabel hanya untuk SQLite; migrasi langsung antar-backend tidak didukung.

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[Penyimpanan](../storage.md)

Impor kredensial lingkungan tersedia dari panel kontrol. Tetapkan salah satu variabel berikut ke JSON mentah atau gunakan varian `_B64` yang cocok untuk JSON yang dikodekan base64:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

Muatan dapat berupa objek kredensial tunggal, larik, atau `{ "credentials": [...] }`.

<a id="development"></a>

## Pengembangan

Bagian ini ditujukan bagi kontributor dan debugging lokal. Penerapan produksi harus menggunakan Docker dengan volume host persisten.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

[Gerbang kualitas](../quality-gates.md) memisahkan pemeriksaan tugas, fase, dan rilis. `python tools/quality_gate.py --list-suites` juga mencantumkan pemeriksaan eksternal langsung yang opsional. [Kontrak kompatibilitas](../compatibility.md) melindungi rute SDK/manajemen, migrasi, skema, dan contoh.

Mulai layanan setelah pemeriksaan berhasil:

```bash
python backend/main.py
```

Garis dasar produksi adalah Python 3.12, dan CI saat ini memverifikasi Python 3.12 dan 3.14. Lihat [Berkontribusi](../../CONTRIBUTING.md) untuk alur kerja pull-request dan ekspektasi tinjauan.

<a id="deployment-notes"></a>

## Catatan Penerapan

- Jangan pernah melakukan komit file JSON kredensial atau `.env`.
- Gunakan `API_KEY` khusus untuk integrasi klien dan `PANEL_PASSWORD` terpisah untuk akses konsol.
- Batasi akses ke volume kredensial persisten atau database eksternal dan aktifkan enkripsi tingkat platform saat istirahat (at rest); token penyedia harus tetap dapat diambil oleh router.
- Tempatkan Polaris di belakang reverse proxy dengan TLS ketika dapat dijangkau di luar localhost.
- Konfigurasikan reverse proxy untuk mempertahankan `Host` dan meneruskan `X-Forwarded-Proto`; tetapkan `PANEL_COOKIE_SECURE=true` ketika terminasi HTTPS terjamin.
- Tetapkan `TRUST_PROXY_HEADERS=true` hanya jika layanan dapat dijangkau secara eksklusif melalui proxy tepercaya yang menggantikan `X-Forwarded-For` dan `X-Forwarded-Proto`.
- Gunakan `GET /health` untuk pemeriksaan keaktifan proses (liveness) dan `GET /ready` untuk pemeriksaan kesiapan sadar penyimpanan (readiness).
- Telemetri eksternal opsional: Prometheus memerlukan `PROMETHEUS_EXPORT_ENABLED` dan `METRICS_TOKEN` kuat; OpenTelemetry hanya mengekspor agregat, bukan isi prompt/respons. Lihat [observabilitas](../observability.md).
- Image Docker dimulai sebagai root hanya cukup lama untuk memperbaiki kepemilikan direktori data yang dipasang, kemudian menjalankan layanan sebagai pengguna `gateway` yang tidak memiliki hak istimewa.
- Tetapkan `CORS_ORIGINS` ke asal tepercaya eksplisit saat klien peramban memerlukan akses lintas-asal.
- Sebelum memperbarui atau memindahkan SQLite, gunakan [cadangan terenkripsi terautentikasi](../backup-and-restore.md). Simpan arsip dan frasa sandi di luar `polaris-data`.
- Penerbitan image Docker menggunakan rahasia repositori `DOCKERHUB_USERNAME` dan `DOCKERHUB_TOKEN` untuk Docker Hub, dan `GITHUB_TOKEN` bawaan untuk GitHub Packages di `ghcr.io/nguywnben/polaris`. Tetapkan variabel repositori opsional `IMAGE_NAME` hanya saat memublikasikan ke nama image Docker Hub kustom.
- Pertahankan `WORKERS=1` dan satu replika aplikasi untuk seri 1.x; penyimpanan eksternal bukan pengganti koordinasi terdistribusi.
- Gunakan rute manajemen kanonikal `/api/credentials`. Alias beta `/api/creds` telah dihapus pada 1.0.0.
- Ikuti [Meningkatkan ke 1.0](../upgrading-to-1.0.md) sebelum memigrasikan penerapan beta.
- Ikuti [panduan pembaruan](../updating.md) saat meningkatkan instans yang diterapkan atau mengembalikan (rollback) rilis.
- Ikuti [daftar periksa rilis](../release-checklist.md) yang dipelihara sebelum menandai (tag) atau mempromosikan image.
- Jaga agar kebijakan retensi log dan rotasi kredensial selaras dengan batas penggunaan Anda.
- Segera rotasi kredensial jika repositori atau pemindai platform melaporkan rahasia yang bocor.
- Render Blueprint menggunakan layanan berbayar dengan disk persisten. Layanan gratis Render menggunakan sistem file fana dan hanya cocok untuk evaluasi sekali pakai.

<a id="community-and-project-health"></a>

## Komunitas dan Kesehatan Proyek

- Baca [Berkontribusi](../../CONTRIBUTING.md) sebelum membuka pull request.
- Laporkan kerentanan melalui proses pribadi di [Kebijakan Keamanan](../../SECURITY.md).
- Tinjau [Catatan Perubahan](../../CHANGELOG.md) untuk perubahan tingkat rilis.
- Ikuti [Kode Etik](../../CODE_OF_CONDUCT.md) di semua ruang proyek.

<a id="acknowledgements-inspirations"></a>

## Ucapan Terima Kasih & Inspirasi

Polaris berdiri di atas pundak komunitas perutean AI sumber terbuka, telemetri, dan gateway. Kami mengucapkan terima kasih kepada para pencipta dan pengelola proyek-proyek ini:

| Proyek | Deskripsi | Bintang |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Inspirasi untuk manajemen kunci multi-penyedia dan agregasi API berbasis web | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Memelopori proxy multi-format dan lapisan penerjemahan protokol untuk CLI AI coding | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Proxy LLM terpadu penetap standar, penyeimbangan beban, dan perutean fallback | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Arsitektur gateway AI ultra-cepat, strategi perutean, dan pola fallback tangguh | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Platform rekayasa LLM sumber terbuka, penelusuran, observabilitas, dan penyerapan metrik | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## Lisensi

Polaris dirilis di bawah [Lisensi MIT](../../LICENSE).
