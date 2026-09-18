<div align="center">
  <h1><img src="../../frontend/assets/logo.png" alt="Polaris" width="48" height="48" /> Polaris</h1>
  <p><b>Universal AI Router & เกตเวย์รวมศูนย์หลายผู้ให้บริการสำหรับเครื่องมือ AI Coding</b></p>
  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>
  <p><a href="#supported-providers">ผู้ให้บริการที่รองรับ</a> • <a href="#core-capabilities">ความสามารถหลัก</a> • <a href="#deployment">การติดตั้ง</a> • <a href="#sdk-surfaces">พื้นผิว SDK</a> • <a href="#architecture">สถาปัตยกรรม</a></p>
  <p><a href="../../README.md">English</a> • <a href="README.vi.md">Tiếng Việt</a> • <a href="README.zh-CN.md">中文（简体）</a> • <a href="README.zh-TW.md">中文（繁體）</a> • <a href="README.ja.md">日本語</a> • <a href="README.ko.md">한국어</a> • <a href="README.es.md">Español</a> • <a href="README.fr.md">Français</a> • <a href="README.de.md">Deutsch</a> • <a href="README.it.md">Italiano</a> • <a href="README.pt.md">Português</a> • <a href="README.ru.md">Русский</a> • <a href="README.id.md">Bahasa Indonesia</a> • <b>ภาษาไทย</b> • <a href="README.tr.md">Türkçe</a></p>
</div>

---

README นี้มี 15 ภาษาและครอบคลุมความสามารถเดียวกัน คู่มือทางเทคนิคที่เชื่อมโยงยังคงใช้ภาษาต้นฉบับ

เราเตอร์ AI อเนกประสงค์สำหรับเครื่องมือเขียนโค้ด Polaris มอบระบบสลับข้อมูลสำรองอัตโนมัติอัจฉริยะ (smart auto-fallback), การทำความสะอาดคำขอที่คำนึงถึงโทเค็น, การแสดงผลการใช้งานที่โปร่งใส และการแปลงรูปแบบคำขออย่างไร้รอยต่อ เพื่อให้เอเจนต์ในเครื่อง, ส่วนขยาย IDE และสคริปต์อัตโนมัติสามารถใช้ขีดความสามารถของ LLM ทั้งแบบฟรีและพรีเมียมผ่านอินเทอร์เฟซ API ที่เสถียรเพียงหนึ่งเดียว

> Polaris รองรับการโฮสต์เองสำหรับบุคคลหรือทีมที่เชื่อถือได้ โดยใช้ worker และ replica อย่างละหนึ่ง ส่วนหลักคือ Docker Compose การเข้าสู่ระบบของเจ้าของภายในเครื่อง SQLite การกำหนดเส้นทาง และ SDK ที่ระบุในเอกสาร PostgreSQL, OIDC, reverse proxy และ telemetry ภายนอกเป็นตัวเลือก ส่วน MongoDB มีไว้เพื่อความเข้ากันได้ ไม่รองรับการประสานงานหลาย replica และ Kubernetes [Production Self-Hosted R1](../specs/production-self-hosted.md).

<a id="why-polaris"></a>

## ทำไมต้อง Polaris

เวิร์กโฟลว์การเขียนโค้ดยุคใหม่มักผสมผสานไคลเอนต์และผู้ให้บริการที่หลากหลาย: เครื่องมือที่เข้ากันได้กับ OpenAI, SDK ดั้งเดิมของ Gemini, เอเจนต์สไตล์ Anthropic, ข้อมูลรับรองที่รองรับโดย Google และเส้นทางโมเดลทดลอง Polaris ทำหน้าที่เป็นตัวกลางระหว่างไคลเอนต์เหล่านั้นกับโมเดลแบ็กเอนด์ เพื่อให้แต่ละเครื่องมือสามารถสื่อสารในรูปแบบที่เข้าใจอยู่แล้วได้ต่อไป ในขณะที่เกตเวย์จะจัดการเรื่องการกำหนดเส้นทาง, การลองใหม่ (retry), การทำความสะอาดคำขอ และการปรับการตอบกลับให้เป็นมาตรฐาน

<a id="core-capabilities"></a>

## ความสามารถหลัก

- สลับผู้ให้บริการอัตโนมัติ พร้อมการจองต่อคำขอ การหมุนเวียนอย่างเป็นธรรม ช่วงพัก และการจัดการโควตาที่หมด
- ลดประวัติที่ยาวโดยรักษาคำสั่งระบบ เครื่องมือ และบทสนทนาล่าสุด
- แปลง OpenAI Chat Completions/Responses, Gemini และ Anthropic Messages รวมถึงสตรีม
- จัดการบัญชี OAuth และคีย์ API พร้อมตรวจสอบและกำจัดรายการซ้ำตามผู้ให้บริการ
- แค็ตตาล็อกโมเดลต่อข้อมูลรับรองตามสิทธิ์บัญชี
- บันทึกเส้นทางโมเดลที่ใช้ไม่ได้และกู้คืนจากหน้า Models
- รองรับ SSE สตรีมจำลอง และลองใหม่แบบจำกัดสำหรับคำตอบที่ถูกตัด
- กำหนดเส้นทางแบบสมดุล ลำดับความสำคัญ น้ำหนัก ความหน่วงต่ำสุด หรือต้นทุนต่ำสุด
- คีย์เสมือนพร้อมงบรายวัน/เดือน RPM/TPM วันหมดอายุ และโมเดลที่อนุญาต
- ประมาณต้นทุน USD ต่อการเรียกและสรุปในแดชบอร์ดกับ Prometheus
- ตัวเลือกป้องกัน prompt injection คำต้องห้าม และปกปิดข้อมูลส่วนบุคคล
- แคชแบบตรงกันทุกประการสำหรับคำตอบที่ให้ผลแน่นอนโดยเลือกเปิดได้
- Prometheus การส่งออก Langfuse แบบเลือกใช้ และติดตามการใช้งาน
- คอนโซลจัดการข้อมูลรับรอง บันทึก การตั้งค่า การใช้งาน และเวอร์ชัน

<a id="console-preview"></a>

## ตัวอย่างคอนโซล

ภาพหน้าจอใช้ข้อมูลสมมติจากสภาพแวดล้อมสาธิตแบบออฟไลน์ที่แยกไว้

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/dashboard-dark.png" />
  <img src="../assets/screenshots/dashboard-light.png" alt="Polaris — แดชบอร์ด" width="1600" height="1100" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/screenshots/credentials-dark.png" />
  <img src="../assets/screenshots/credentials-light.png" alt="Polaris — ตัวอย่างคอนโซล" width="1600" height="1100" />
</picture>

<a id="supported-providers"></a>

## ผู้ให้บริการที่รองรับ

แค็ตตาล็อกมีผู้ให้บริการ 23 ราย โมเดลและคุณสมบัติที่ใช้ได้ขึ้นอยู่กับสิทธิ์ของข้อมูลรับรองแต่ละรายการ

| ผู้ให้บริการ | วิธีเชื่อมต่อ | บริการ / ขอบเขต |
| --- | --- | --- |
| <img src="../../frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="../../frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | คีย์ API | Gemini / Gemma |
| <img src="../../frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="../../frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | คีย์ API | xAI API |
| <img src="../../frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (รหัสอุปกรณ์) | Codex Responses |
| <img src="../../frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | คีย์ API | OpenAI API |
| <img src="../../frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="../../frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | คีย์ API | Anthropic API |
| <img src="../../frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | ปลายทาง; คีย์ API เป็นตัวเลือก | ภายในเครื่อง / โฮสต์เอง |
| <img src="../../frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | คีย์ API | Cerebras API |
| <img src="../../frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | โทเค็น API + ID บัญชี | Workers AI |
| <img src="../../frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | คีย์ API | DeepSeek API |
| <img src="../../frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | คีย์ API | Groq API |
| <img src="../../frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | คีย์ API; ID องค์กรเป็นตัวเลือก | Kilo Gateway |
| <img src="../../frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | คีย์ API / บริการ | Kimchi Coding API |
| <img src="../assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | คีย์ API | Moonshot API |
| <img src="../../frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | OAuth ผ่านเบราว์เซอร์ / อุปกรณ์ AWS / คีย์ API | Kiro |
| <img src="../../frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (อุปกรณ์ Meta) | `muse-code/` |
| <img src="../../frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | คีย์ API | Meta API |
| <img src="../../frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | คีย์ API | Mistral API |
| <img src="../../frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | คีย์ API | บริการอนุมานที่โฮสต์โดย NVIDIA |
| <img src="../../frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | คีย์ API + แผน Zen/Go | OpenCode Zen / Go |
| <img src="../../frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | คีย์ API | Poolside API |

ไคลเอนต์ใช้ [SDK ร่วมกัน](#sdk-surfaces) การแปลง สตรีม และสลับผู้ให้บริการขึ้นอยู่กับโมเดล ตัวเลือกที่เข้ากันไม่ได้จะถูกปฏิเสธอย่างชัดเจน ตั้งค่าการเชื่อมต่อตามผู้ให้บริการหรือข้อมูลรับรองใน **Providers** ข้อมูลรับรองและเนมสเปซโมเดลของ Muse Code กับ Meta Model API แยกจากกัน

[Meta Model API](../providers/meta-model-api.md) · [API / Kiro](../providers/additional-api-providers.md) · [Groq / DeepSeek / Mistral / Cerebras](../providers/api-platforms.md)

<a id="architecture"></a>

## สถาปัตยกรรม

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | การเชื่อมต่อ IDE
        |
        v
Polaris
  การยืนยันตัวตน -> การแปลงรูปแบบ -> การทำความสะอาดตามโทเค็น -> การกำหนดเส้นทาง -> ระบบสำรอง -> การสตรีม
        |
        v
provider adapters
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama
```

API สาธารณะยังคงเสถียรในขณะที่อะแดปเตอร์เฉพาะของผู้ให้บริการพัฒนาอยู่เบื้องหลัง Polaris

<a id="repository-structure"></a>

## โครงสร้างที่เก็บข้อมูล (Repository)

```text
backend/       รูทการประกอบ FastAPI, แกนหลักการกำหนดเส้นทาง, ตัวแปลง, ที่จัดเก็บข้อมูล และการทดสอบ
frontend/      มาร์กอัปคอนโซลการจัดการ, สไตล์, สคริปต์ และแอสเซทของผู้ให้บริการ
deploy/        คำจำกัดความของคอนเทนเนอร์, แมนิเฟสต์แพลตฟอร์ม และสคริปต์ระบบปฏิบัติการ
docs/          บันทึกสถาปัตยกรรมและแอสเซทโครงการที่ได้รับการดูแล
.github/       CI, ระบบอัตโนมัติของการพึ่งพา และเทมเพลตการมีส่วนร่วม
```

ดู [สถาปัตยกรรม](../architecture.md) สำหรับขอบเขตโมดูล, โฟลว์ของคำขอ, ความเป็นเจ้าของสถานะ และข้อจำกัดของรุ่นปัจจุบัน

<a id="deployment"></a>

## การติดตั้ง

Docker Compose บนเครื่องเดียวและ worker เดียวเป็นแนวทางหลัก ดู[การติดตั้ง](../installation.md)และ[ตารางการรองรับ](../installation.md#support-matrix)

รูปแบบพื้นฐานไม่ต้องใช้บริการภายนอกและเก็บข้อมูลใน `polaris-data` เทมเพลตใช้รุ่น `1.0.0` ติดตั้งด้วยแท็กและอิมเมจ Polaris ที่เผยแพร่แล้วและเป็นรุ่นเดียวกันเท่านั้น หากใช้ซอร์สโค้ดที่ยังไม่เผยแพร่ ให้สร้างอิมเมจภายในเครื่องแยกต่างหากตาม[รายการตรวจสอบการเผยแพร่](../releases/1.0.0-preparation.md) ใช้[ขั้นตอนอัปเดตและย้อนกลับ](../updating.md) และเปิดตัวเลือกขั้นสูงผ่าน `deploy/compose.advanced.yml` เมื่อต้องการ

ดู[ข้อตกลงชื่อระบุ](../migrations/polaris.md)และ[การแก้ปัญหา](../troubleshooting.md) สคริปต์ภายในเครื่อง `docker run`, Render และ Zeabur เป็นแนวทางที่ยังใช้งานร่วมกันได้ แต่ไม่ได้ผ่านการตรวจสอบติดตั้ง/กู้คืนเทียบเท่ากัน อิมเมจเผยแพร่สำหรับ `linux/amd64` ส่วน `linux/arm64` ยังระงับการเผยแพร่

### การพัฒนาหรือวินิจฉัยภายในเครื่อง:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

บน Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

เปิดคอนโซล ขั้นตอนตั้งค่าเริ่มต้นเหมือน Docker:

```text
http://127.0.0.1:4283
```

<a id="configuration"></a>

## การกำหนดค่า

ลำดับความสำคัญคือ ตัวแปรสภาพแวดล้อม การตั้งค่าที่บันทึก และค่าเริ่มต้น [เอกสารอ้างอิงที่สร้างอัตโนมัติ](../reference/configuration.md)ระบุชนิด กลุ่ม โมดูลรับผิดชอบ และการมีผลทันที หลังเริ่มใหม่ หรือผ่านสภาพแวดล้อมเท่านั้น ค่าที่ไม่ถูกต้องหยุดการเริ่มระบบพร้อมระบุตัวแปร และชื่อ `POLARIS_*` ที่อาจพิมพ์ผิดจะมีคำเตือน

| ตัวแปร | ค่าเริ่มต้น | วัตถุประสงค์ |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | ที่อยู่ผูก (bind address) |
| `PORT` | `4283` | พอร์ต HTTP |
| `HOST_PORT` | `4283` | พอร์ตฝั่งโฮสต์ที่ใช้โดย Docker Compose เท่านั้น |
| `WORKERS` | `1` | รองรับ worker เดียวเท่านั้น |
| `POLARIS_RUNTIME_MODE` | `standalone` | รองรับเฉพาะ `standalone` |
| `POLARIS_REPLICA_COUNT` | `1` | รองรับ replica เดียวเท่านั้น |
| `CORS_ORIGINS` | ว่าง | ต้นทางเบราว์เซอร์ที่คั่นด้วยเครื่องหมายจุลภาคที่อนุญาตให้เรียกใช้ API ข้ามต้นทาง เว้นว่างไว้สำหรับการใช้งานคอนโซลต้นทางเดียวกัน |
| `CORS_ORIGIN_REGEX` | ว่าง | Regex ทางเลือกสำหรับต้นทางเบราว์เซอร์แบบไดนามิกที่ได้รับการจัดการ |
| `API_KEY` | สร้างอัตโนมัติ | คีย์ API ไคลเอนต์ที่ขึ้นต้นด้วย `sk-polaris-` |
| `PANEL_PASSWORD` | ว่างจนกว่าจะตั้งค่า | รหัสผ่านสำหรับแผงควบคุมบนเว็บ |
| `SETUP_TOKEN` | ว่าง | โทเค็นตั้งค่าระยะไกลที่ไม่ซ้ำอย่างน้อย 24 ตัวอักษร ไม่สร้างหรือบันทึกอัตโนมัติ ไม่จำเป็นสำหรับ localhost โดยตรง |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | อายุการใช้งานเซสชันคอนโซลเว็บบนหน่วยวินาที |
| `PANEL_COOKIE_SECURE` | อัตโนมัติ | ตั้งค่า `true` เพื่อกำหนดให้คุกกี้พาเนลใช้เฉพาะ HTTPS เท่านั้น เว้นว่างไว้เพื่อตรวจหา HTTPS ผ่าน `X-Forwarded-Proto` โดยอัตโนมัติ |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | หน้าต่างจำกัดอัตราการเข้าสู่ระบบในหน่วยวินาที |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | ความพยายามเข้าสู่ระบบที่ล้มเหลวสูงสุดที่อนุญาตต่อไคลเอนต์ภายในหน้าต่างจำกัดอัตรา |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | ที่อยู่ไคลเอนต์สูงสุดที่เก็บไว้โดยตัวจำกัดการเข้าสู่ระบบในหน่วยความจำ |
| `MAX_REQUEST_BODY_MB` | `64` | ขนาดเนื้อหาคำขอ HTTP สูงสุดในหน่วย MiB คำขอ SDK ที่มีขนาดเกินขีดจำกัดจะส่งกลับข้อผิดพลาดตามโครงสร้างดั้งเดิมของโปรโตคอล |
| `TRUST_PROXY_HEADERS` | `false` | ยอมรับส่วนหัวการส่งต่อไคลเอนต์/โปรโตคอลจาก reverse proxy ที่เชื่อถือได้ซึ่งเขียนทับส่วนหัวเหล่านั้นเท่านั้น |
| `CREDENTIALS_DIR` | `./backend/data/creds` | ไดเรกทอรีจัดเก็บข้อมูลรับรอง ใน Docker ให้คงอยู่ `/app/backend/data/creds` ด้วยวอลุ่มโฮสต์ |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | ปลายทางแบ็กเอนด์ของ Code Assist |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | ปลายทางแบ็กเอนด์ของ Google Antigravity |
| `PROXY` | ว่าง | พร็อกซี HTTP, HTTPS หรือ SOCKS ทางเลือก |
| `RETRY_429_ENABLED` | `true` | เปิดใช้งานการลองใหม่แบบมีขอบเขตสำหรับการจำกัดอัตราและความล้มเหลวชั่วคราวของอัปสตรีม ชื่อเดิมยังคงอยู่เพื่อความเข้ากันได้ของการกำหนดค่า |
| `RETRY_429_MAX_RETRIES` | `5` | ความพยายามลองใหม่สูงสุดสำหรับความล้มเหลวชั่วคราวของอัปสตรีม |
| `RETRY_429_INTERVAL` | `1` | ความล่าช้าพื้นฐานระหว่างการลองใหม่ชั่วคราวในหน่วยวินาที |
| `AUTO_DISABLE` | `false` | ปิดใช้งานข้อมูลรับรองหลังจากความล้มเหลวร้ายแรง (hard failures) ที่กำหนดค่าไว้ |
| `AUTO_DISABLE_ERROR_CODES` | `403` | รหัสสถานะความล้มเหลวร้ายแรงที่คั่นด้วยเครื่องหมายจุลภาค |
| `ROUTING_STRATEGY` | `balanced` | กลยุทธ์: `balanced`, `priority`, `weighted`, `least_latency`, `lowest_cost` |
| `PREFERRED_PROVIDER` | ว่าง | ผู้ให้บริการที่ต้องการโดยกลยุทธ์ `priority` เช่น `google_antigravity` หรือ `google_ai_studio` |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | ระยะเวลาหมดเวลาการอนุมานของผู้ให้บริการ ซึ่งถูกจำกัดระหว่าง 5 ถึง 900 วินาที |
| `RESPONSE_CACHE_ENABLED` | `false` | แคชในหน่วยความจำสำหรับคำตอบแน่นอนแบบไม่สตรีม อุณหภูมิ 0 |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | อายุแคชเป็นวินาที |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | จำนวนคำตอบสูงสุดในแคช |
| `GUARDRAILS_ENABLED` | `false` | เปิดการป้องกันก่อนเรียก |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | ปกปิดอีเมล บัตร และคีย์ API ในข้อความขาออก |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | ปฏิเสธ prompt injection ด้วย HTTP 400 |
| `GUARDRAILS_BLOCKED_KEYWORDS` | ว่าง | คำต้องห้ามคั่นด้วยจุลภาค ไม่แยกตัวพิมพ์ใหญ่เล็ก |
| `PRICING_SYNC_ENABLED` | `true` | อัปเดตราคา LiteLLM เบื้องหลังและเก็บสำเนาล่าสุดที่ถูกต้องเมื่อออฟไลน์ |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | ช่วงอัปเดตราคา: 1–168 ชั่วโมง |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | ความพยายามดำเนินการต่อสูงสุดสำหรับการสตรีมแบบป้องกันการตัดทอน |
| `TOKEN_COMPRESSION_ENABLED` | `true` | บีบอัดประวัติการสนทนาที่มีขนาดใหญ่เกินไปก่อนการกำหนดเส้นทางไปยังผู้ให้บริการ |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | เกณฑ์โทเค็นอินพุตโดยประมาณที่เปิดใช้งานการบีบอัด |
| `TOKEN_COMPRESSION_TARGET` | `24000` | เป้าหมายโทเค็นอินพุตโดยประมาณหลังจากการบีบอัด ต้องต่ำกว่าเกณฑ์เปิดใช้งาน |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | จำนวนรอบการสนทนาล่าสุดขั้นต่ำของผู้ใช้ที่คงไว้ระหว่างการบีบอัด |
| `COMPATIBILITY_MODE` | `false` | แปลงข้อความระบบสำหรับไคลเอนต์/โมเดลที่ไม่รองรับ |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | รวมฟิลด์การใช้เหตุผล (reasoning) ของโมเดลเมื่อมีให้ใช้งาน |
| `MONGODB_URI` | ว่าง | พื้นที่จัดเก็บ MongoDB เพื่อความเข้ากันได้ |
| `POSTGRESQL_URI` | ว่าง | พื้นที่จัดเก็บ PostgreSQL แบบเลือกใช้ |
| `CODE_ASSIST_CLIENT_ID` | ไคลเอนต์เดสก์ท็อปที่ให้มา | การแทนที่ทางเลือกสำหรับ Client ID OAuth ของ Code Assist |
| `CODE_ASSIST_CLIENT_SECRET` | ไคลเอนต์เดสก์ท็อปที่ให้มา | การแทนที่ทางเลือกสำหรับ Client Secret OAuth ของ Code Assist |
| `ANTIGRAVITY_CLIENT_ID` | ไคลเอนต์เดสก์ท็อปที่ให้มา | การแทนที่ทางเลือกสำหรับ Client ID OAuth ของ Google Antigravity สามารถจัดการได้จากหน้า Providers |
| `ANTIGRAVITY_CLIENT_SECRET` | ไคลเอนต์เดสก์ท็อปที่ให้มา | การแทนที่ทางเลือกสำหรับ Client Secret OAuth ของ Google Antigravity กำหนดค่าผ่าน env หรือหน้า Providers เมื่อไคลเอนต์อัปสตรีมเปลี่ยน |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | การแทนที่ทางเลือกสำหรับปลายทาง Google AI Studio Generative Language API |
| `XAI_API_URL` | `https://api.x.ai/v1` | การแทนที่ทางเลือกสำหรับปลายทาง API ของ SpaceXAI Console สำหรับข้อมูลรับรองคีย์ API สามารถจัดการได้จากหน้า Providers |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | การแทนที่ทางเลือกสำหรับปลายทางการสมัครสมาชิก OAuth ของ Grok Build |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | การแทนที่ทางเลือกสำหรับผู้ออก OAuth ของ Grok Build คอนโซลยอมรับเฉพาะโฮสต์ HTTPS ภายใต้ `x.ai` เท่านั้น |
| `XAI_CLIENT_ID` | ไคลเอนต์สาธารณะที่ให้มา | การแทนที่ทางเลือกสำหรับ Client ID OAuth PKCE ของ Grok Build |
| `XAI_USER_AGENT` | `grok-cli/polaris` | การแทนที่ทางเลือกสำหรับ HTTP User-Agent ที่ใช้ร่วมกันสำหรับคำขอ Grok Build OAuth และ SpaceXAI Console API |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | การแทนที่ทางเลือกสำหรับปลายทาง OpenAI Platform API สามารถจัดการได้จากหน้า Providers |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | การแทนที่ทางเลือกสำหรับปลายทางการอนุมานและโมเดลบัญชีของ Codex |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | การแทนที่ทางเลือกสำหรับปลายทางการจำกัดอัตราของบัญชี Codex |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | การแทนที่ทางเลือกสำหรับบริการอนุมัติอุปกรณ์ของ Codex |
| `CODEX_CLIENT_ID` | ไคลเอนต์สาธารณะที่ให้มา | การแทนที่ทางเลือกสำหรับ Client ID OAuth อุปกรณ์ของ Codex |
| `CODEX_USER_AGENT` | ค่าที่เข้ากันได้กับ Codex CLI | การแทนที่ทางเลือกสำหรับ User-Agent สำหรับคำขอ Codex |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | ปลายทาง Messages เฉพาะ Claude Code |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | การแทนที่ทางเลือกสำหรับปลายทางการอนุญาต PKCE ของ Claude Code คอนโซลยอมรับเฉพาะโฮสต์ Anthropic และ Claude |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | การแทนที่ทางเลือกสำหรับปลายทางโทเค็นของ Claude Code คอนโซลยอมรับเฉพาะโฮสต์ Anthropic และ Claude |
| `CLAUDE_CLIENT_ID` | ไคลเอนต์สาธารณะที่ให้มา | การแทนที่ทางเลือกสำหรับ Client ID OAuth PKCE ของ Claude Code |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | User-Agent เฉพาะ Claude Code |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | ปลายทาง Claude Platform แยกต่างหากใน Providers |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | User-Agent อิสระของ Claude Platform |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | การแทนที่ทางเลือกสำหรับโปรโตคอล User-Agent ของ Google Antigravity |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | การแทนที่ทางเลือกสำหรับ userAgent ระดับเพย์โหลดของ Google Antigravity |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | เปิด `GET /metrics` ที่ต้องยืนยันตัวตน |
| `METRICS_TOKEN` | ว่าง | โทเค็น Bearer อย่างน้อย 32 ไบต์ UTF-8 สำหรับ Prometheus |
| `OTEL_EXPORT_ENABLED` | `false` | เปิดการส่งข้อมูลรวม OTLP/HTTP โดยไม่มีเนื้อหา |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | ว่าง | ตัวรับ HTTPS ห้ามฝังข้อมูลรับรองใน URL |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | ช่วงส่งออก: 15–300 วินาที |
| `LANGFUSE_PUBLIC_KEY` | ว่าง | เปิด Langfuse ร่วมกับคีย์ลับ |
| `LANGFUSE_SECRET_KEY` | ว่าง | คีย์ลับ Langfuse สำหรับ trace |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | ปลายทางรับข้อมูล Langfuse |
| `LOG_LEVEL` | `info` | ระดับบันทึกการทำงานของรันไทม์ |
| `LOG_MAX_MB` | `10` | ขนาดไฟล์บันทึกที่ใช้งานสูงสุดก่อนการหมุนเวียน (rotation) |
| `LOG_BACKUP_COUNT` | `3` | จำนวนไฟล์บันทึกที่หมุนเวียนที่คงไว้ |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | ปลายทางไฟล์บันทึก ใน Docker ให้คงอยู่ `/app/backend/data/logs` ด้วยวอลุ่มโฮสต์ |

### การควบคุมการบีบอัด

นโยบาย AI Quality ส่วนกลางเป็นข้อจำกัดหลัก คีย์เสมือนเลือกได้เพียงสืบทอดหรือปิดการบีบอัดผ่าน `PATCH /api/virtual-keys/{key_id}/quality-policy` พร้อม revision ปัจจุบัน โดย `inherit` ยกเลิกข้อจำกัดของคีย์ คำขอที่ยืนยันตัวตนแล้วส่ง `x-polaris-compression: off` ได้ หากไม่ส่งหรือใช้ `inherit` จะทำตามนโยบายส่วนกลาง/คีย์ ไม่สามารถเปิดการบีบอัดที่ส่วนกลางปิดไว้หรือเพิ่มความเข้มข้นได้ ระบบลบเฉพาะส่วนต้นของประวัติที่ปลอดภัย หากโครงสร้างหรือการประมาณไม่แน่นอนจะส่งโดยไม่เปลี่ยนแปลง จำนวนโทเค็นเป็นค่าประมาณ

```json
{"expected_revision": 3, "compression": "disabled"}
```

<a id="sdk-surfaces"></a>

## พื้นผิว SDK

Polaris ได้รับการออกแบบตามพฤติกรรม URL มาตรฐานของ Python SDK อย่างเป็นทางการ กำหนดค่าแต่ละไคลเอนต์ให้ตรงตามที่แสดงด้านล่าง เกตเวย์ไม่ต้องการคำนำหน้าเส้นทางที่ซ้ำซ้อนซึ่งไม่ได้มาตรฐาน

ตัวอย่างใช้โมเดลเสมือน `polaris` กำหนดค่าลำดับการสำรองข้อมูลผู้ให้บริการ-โมเดลในหน้า Models ก่อน หรือแทนที่ด้วย ID โมเดลที่เป็นรูปธรรม

### OpenAI Python SDK

ใช้ `/v1` เป็น base URL ของ OpenAI โดย SDK จะต่อท้าย `/chat/completions` โดยอัตโนมัติ

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4283/v1",
    api_key="sk-polaris-..."
)

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "อธิบายที่เก็บข้อมูลนี้ในหนึ่งย่อหน้า"}],
)
```

ไคลเอนต์เดียวกันสามารถใช้ OpenAI Responses API ได้:

```python
response = client.responses.create(
    model="polaris",
    instructions="ตอบอย่างกระชับ",
    input="อธิบายที่เก็บข้อมูลนี้ในหนึ่งย่อหน้า",
)

print(response.output_text)
```

ความเข้ากันได้ของ Responses รองรับข้อความ, อินพุตรูปภาพ, non-streaming function tools และการสตรีมข้อความ SSE เครื่องมือในตัวที่โฮสต์โดย OpenAI, ประวัติการตอบกลับที่จัดเก็บไว้ และการเรียกฟังก์ชันแบบสตรีมมิ่งจะถูกปฏิเสธอย่างชัดเจนเนื่องจาก Polaris ไม่ได้เรียกใช้, จัดเก็บ หรือละทิ้งพฤติกรรมเฉพาะของ OpenAI เหล่านั้นอย่างเงียบๆ

### Anthropic Python SDK

ใช้ต้นทางของเกตเวย์เป็น base URL ของ Anthropic โดย SDK จะต่อท้าย `/v1/messages` โดยอัตโนมัติ

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://127.0.0.1:4283",
    api_key="sk-polaris-..."
)

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "ร่างข้อความคอมมิตสั้นๆ"}],
)
```

### Google GenAI Python SDK

ใช้ต้นทางของเกตเวย์เป็น base URL ของ Google GenAI โดย SDK จะต่อท้ายเส้นทางโมเดลเริ่มต้น เช่น `/v1beta/models/{model}:generateContent`

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
    contents="เขียนฟังก์ชัน Python สั้นๆ หนึ่งฟังก์ชัน",
    config=types.GenerateContentConfig(
        system_instruction="คุณเป็นผู้ช่วยที่เป็นประโยชน์",
    ),
)
```

### เส้นทางที่รองรับ

Polaris เปิดเผยเส้นทางที่เข้ากันได้กับ SDK โดยไม่ต้องมีเนมสเปซของผลิตภัณฑ์:

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

ความล้มเหลวในการยืนยันตัวตน, การตรวจสอบความถูกต้องของคำขอ, การกำหนดเส้นทาง, อัปสตรีม และข้อผิดพลาดก่อนการสตรีมจะใช้โครงสร้างข้อผิดพลาดดั้งเดิมสำหรับพื้นผิว SDK ที่เลือก ทุกการตอบกลับ HTTP จะรวมส่วนหัว `X-Request-ID` ไคลเอนต์สามารถระบุตัวระบุที่ปลอดภัยในส่วนหัวนั้นเพื่อการเชื่อมโยงแบบครบวงจร (end-to-end) การตอบกลับที่จำกัดอัตราและไม่พร้อมใช้งานชั่วคราวจะคงส่วนหัว `Retry-After` ไว้เมื่ออัปสตรีมระบุให้

<a id="model-features"></a>

## คุณสมบัติโมเดล

หน้า Models จะสร้างโมเดลเสมือน `polaris` จากโมเดลที่ค้นพบในข้อมูลรับรองของผู้ให้บริการที่เปิดใช้งาน จัดเรียงสมาชิกตามลำดับความสำคัญเพียงครั้งเดียว จากนั้นใช้ `polaris` จาก SDK ที่รองรับ Polaris จะปรับสมดุลข้อมูลรับรองที่สมบูรณ์ซึ่งรองรับโมเดลแรก และดำเนินการต่อไปตามลำดับโมเดลที่กำหนดค่าไว้เมื่อโมเดลนั้นไม่พร้อมใช้งาน ID โมเดลของผู้ให้บริการที่เป็นรูปธรรมยังคงมีให้ใช้งานสำหรับไคลเอนต์ที่ต้องการการเลือกโมเดลแบบกำหนดแน่นอน การบันทึกการเลือกที่ว่างเปล่าจะปิดใช้งาน `polaris` โดยไม่ส่งผลกระทบต่อข้อมูลรับรองของผู้ให้บริการ

การค้นพบโมเดลจะคำนึงถึงผู้ให้บริการ: โมเดลที่ใช้ร่วมกันสามารถรองรับโดยผู้ให้บริการหลายราย ในขณะที่โมเดลเฉพาะของผู้ให้บริการจะใช้เฉพาะข้อมูลรับรองที่เข้ากันได้เท่านั้น แต่ละข้อมูลรับรองที่ได้รับการยืนยันจะจัดเก็บแคตตาล็อกผู้ให้บริการของตนเอง และเราเตอร์จะให้ความสำคัญกับการสนับสนุนที่ประกาศไว้ของข้อมูลรับรองมากกว่าการอนุมานผู้ให้บริการทั่วไป การรีเฟรชแคตตาล็อกจะตรวจสอบความพร้อมใช้งานของผู้ให้บริการปัจจุบันอีกครั้ง ตัวเลือกที่ไม่พร้อมใช้งานจะยังคงมองเห็นได้ในการกำหนดค่าจนกว่าจะได้รับการกู้คืนหรือลบออก

เมื่ออัปสตรีมส่งคืน `404` สำหรับโมเดลที่เป็นรูปธรรม Polaris จะบันทึกเส้นทางที่ไม่พร้อมใช้งานสำหรับข้อมูลรับรองและโมเดลนั้นแทนที่จะระงับผู้ให้บริการทั้งหมด เส้นทางดังกล่าวจะถูกหลีกเลี่ยงชั่วคราวในทันทีและยังคงมองเห็นได้ใน **Unavailable Model Routes** จนกว่าจะถูกลบออกหรือข้อมูลรับรองได้รับการตรวจสอบใหม่ ซึ่งจะช่วยป้องกันไม่ให้การสมัครสมาชิกหรือสิทธิ์ตามภูมิภาคของบัญชีหนึ่งส่งผลกระทบต่อบัญชีอื่นที่ผู้ให้บริการรายเดียวกัน หากไม่มีข้อมูลรับรองที่เปิดใช้งานประกาศหรือสามารถอนุมานการสนับสนุนสำหรับโมเดลที่เป็นรูปธรรมที่ร้องขอ เกตเวย์จะส่งกลับข้อผิดพลาดไม่มีข้อมูลรับรองที่เข้ากันได้ที่ชัดเจนแทนที่จะส่งคำขอไปยังผู้ให้บริการแบบสุ่ม

Polaris รู้จักคำนำหน้าและคำต่อท้ายคุณสมบัติในชื่อโมเดล:

- `fake-streaming/{model}` หรือคำนำหน้าการจำลองสตรีมที่กำหนดค่าไว้สำหรับไคลเอนต์ที่ต้องการเอาต์พุต SSE
- `streaming-anti-truncation/{model}` หรือคำนำหน้าป้องกันการตัดทอนที่กำหนดค่าไว้สำหรับการกู้คืนการสตรีมแบบยาว
- คำต่อท้ายการคิด เช่น `-high`, `-medium`, `-low`, `-minimal` และ `-max` สำหรับโมเดลตระกูล Gemini ที่รองรับ
- คำต่อท้ายการค้นหา เช่น `-search` สำหรับโมเดลที่รองรับการอิงข้อมูลด้วย Google Search (grounding)

อะแดปเตอร์ของผู้ให้บริการจะปรับชื่อคุณสมบัติเหล่านี้ให้เป็นมาตรฐานก่อนส่งคำขอไปยังอัปสตรีม

<a id="usage-and-cost-visibility"></a>

## ความโปร่งใสในการใช้งานและค่าใช้จ่าย

แต่ละความพยายามเรียกผู้ให้บริการ การลองใหม่ และการสลับถูกนับแยกกัน ส่วน trace เก็บผลสุดท้ายของคำขอเชิงตรรกะ บันทึกผล ข้อมูลรับรอง โทเค็นขาเข้า/ขาออก/แคช/การใช้เหตุผลที่รายงาน การประหยัดโดยประมาณ และต้นทุน USD ข้อมูลการใช้ที่ไม่มีไม่เท่ากับวัดได้ศูนย์ ช่วงเวลาใช้ขอบเขตคงที่ตามเขตเวลาของเบราว์เซอร์ โดยมุมมองวันครอบคลุม 00:00–23:00 ราคา LiteLLM อัปเดตเมื่อเริ่มและทุก 24 ชั่วโมงตามค่าเริ่มต้น เก็บสำเนาล่าสุดที่ถูกต้องแบบอะตอมมิก ความล้มเหลวไม่ขัดขวางการอนุมาน `model_pricing.json` ในโฟลเดอร์ข้อมูลรับรองมีความสำคัญกว่า หน่วยราคาคือต่อล้านโทเค็น ดูยอดรวมในแดชบอร์ด `/api/virtual-keys` และ `/metrics` ให้ยึดใบเรียกเก็บเงินและ tokenizer ของผู้ให้บริการเป็นหลัก

คีย์เสมือนรองรับงบรายวัน/เดือน หน้าต่างเลื่อน RPM/TPM วันหมดอายุ และกฎโมเดลแบบ glob เก็บเฉพาะแฮช SHA-256 และแสดงค่าลับเฉพาะตอนสร้าง

<a id="credential-workflow"></a>

## เวิร์กโฟลว์ข้อมูลรับรอง

1. เริ่มต้น Polaris
2. เปิด `http://YOUR_SERVER_IP:4283` บน VPS หรือ `http://127.0.0.1:4283` สำหรับการพัฒนาในเครื่อง
3. ตรวจสอบให้เสร็จและสร้างรหัสผ่านเจ้าของ ก่อนตั้งค่าจากระยะไกลให้กำหนด `SETUP_TOKEN` ที่ไม่ซ้ำอย่างน้อย 24 ตัวอักษร หรือ `PANEL_PASSWORD` โทเค็นไม่ถูกสร้างหรือเขียนลงบันทึกโดยอัตโนมัติ
4. เพิ่มบัญชี, คีย์ API หรือการเชื่อมต่อ Ollama จากหน้า Providers
5. ตรวจสอบข้อมูลรับรองและดูสถานะคูลดาวน์/ข้อผิดพลาดในพาเนล **Credentials** (`/credentials`).
6. ชี้เครื่องมือเขียนโค้ดของคุณไปยังหนึ่งในพื้นผิว API ด้านบน

เมื่อเพิ่มข้อมูลรับรอง Google Antigravity ทาง Google จะเปลี่ยนเส้นทางเบราว์เซอร์ไปที่ `http://localhost:4283/callback` หลังจากลงชื่อเข้าใช้ ในเครื่องโลคัล Polaris จะแสดงหน้าความสำเร็จของ OAuth บน VPS ที่อยู่ `localhost` นั้นเป็นของเครื่องเบราว์เซอร์ของผู้ใช้ ดังนั้นหน้าเว็บอาจโหลดไม่สำเร็จ ให้คัดลอก URL แบบเต็มจากแถบที่อยู่ของเบราว์เซอร์ กลับไปที่หน้า Providers วางลงใน `Callback URL` แล้วคลิก `Save credential`

Google AI Studio ใช้การยืนยันตัวตนด้วยคีย์ API แทน OAuth เพิ่มคีย์จากหน้า Providers แล้ว Polaris จะตรวจสอบความถูกต้องกับแคตตาล็อกโมเดลของ Google จัดเก็บเป็นข้อมูลรับรองของผู้ให้บริการ และกำหนดเส้นทางคำขอ Gemini หรือ Gemma ที่เข้ากันได้ผ่านคีย์นั้น เราเตอร์อัจฉริยะสามารถสลับสำรองระหว่าง AI Studio และ Google Antigravity สำหรับโมเดล Gemini ที่ใช้ร่วมกันได้ ในขณะที่ยังคงรักษาโมเดลเฉพาะของผู้ให้บริการไว้บนข้อมูลรับรองที่เข้ากันได้

การนำเข้าแบบกลุ่มของ Google AI Studio รองรับไฟล์ JSON และไฟล์บีบอัด ZIP ที่มีไฟล์ JSON เอกสาร JSON อาจมีหนึ่งคีย์, อาร์เรย์ `api_keys` หรืออาร์เรย์ของออบเจกต์คีย์:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

การนำเข้าไฟล์ทำแบบออฟไลน์: Polaris ตรวจสอบโครงสร้าง JSON/ZIP บันทึกคีย์ใหม่เป็น `unverified` และข้ามคีย์ซ้ำหรือคีย์ที่มีอยู่แล้วโดยไม่ติดต่อ Google รายการโมเดลที่นำเข้าจะไม่ถือว่าผ่านการยืนยันแล้ว ข้อผิดพลาดด้านรูปแบบจะแสดงโดยไม่เปิดเผยคีย์ จากนั้นให้สั่งตรวจสอบข้อมูลรับรอง/ค้นหาโมเดลโดยตรง ส่วน **Test model** เป็นการตรวจสอบสิทธิ์เรียกใช้งานจริงแยกต่างหาก ซึ่งอาจใช้โควตาหรือมีค่าใช้จ่าย

Grok Build รองรับข้อมูลรับรอง PKCE OAuth ในขณะที่ SpaceXAI Console รองรับคีย์ API คีย์ SpaceXAI Console จะได้รับการตรวจสอบความถูกต้องกับแคตตาล็อกโมเดล API ของ SpaceXAI Console ก่อนจัดเก็บ สำหรับ Grok Build OAuth นั้น Polaris จะสร้างลิงก์การอนุญาต หลังจากการอนุญาต ให้คัดลอกโค้ดที่แสดงบนหน้าการอนุญาต Grok Build แล้ววางลงในแบบฟอร์ม Grok Build OAuth โทเค็นการเข้าถึงจะได้รับการรีเฟรชโดยอัตโนมัติเมื่อมีรีเฟรชโทเค็น และข้อมูลรับรองทั้งสองประเภทจะแสดงเฉพาะโมเดลที่ประกาศโดยแคตตาล็อกปัจจุบันของแต่ละประเภทเท่านั้น หน้า Credentials สามารถดึงข้อมูลการใช้เครดิตรายเดือน และการใช้งานรายสัปดาห์ (เมื่อ xAI ระบุให้) สำหรับบัญชี Grok Build OAuth มุมมองการเรียกเก็บเงินระดับบัญชีนี้ไม่สามารถใช้ได้กับคีย์ API ของ SpaceXAI Console

Codex ใช้โฟลว์การอนุญาตอุปกรณ์ของ OpenAI สร้างรหัสอุปกรณ์จากหน้า Providers เปิด URL การยืนยันที่แสดง ป้อนรหัส เสร็จสิ้นการลงชื่อเข้าใช้ และกลับมาตรวจสอบการอนุญาต Polaris จะจัดเก็บแคตตาล็อกโมเดลตามขอบเขตบัญชีที่ Codex ส่งคืน รีเฟรชโทเค็นการเข้าถึง OAuth เมื่อจำเป็น และส่งคำขอที่เข้ากันได้ผ่านการขนส่ง Codex Responses ส่วน OpenAI Platform ใช้การยืนยันตัวตนด้วยคีย์ API คีย์จะได้รับการตรวจสอบผ่านแคตตาล็อกโมเดลบัญชีก่อนเข้าสู่Credentials ผลิตภัณฑ์ทั้งสองรองรับการนำเข้า JSON และ ZIP พร้อมการตรวจสอบความถูกต้องและการตัดข้อมูลซ้ำซ้อนเฉพาะผู้ให้บริการ

Claude Code ใช้โฟลว์ Anthropic PKCE OAuth สร้างลิงก์การอนุญาต เสร็จสิ้นการอนุญาต จากนั้นวางรหัสการอนุญาตที่ส่งคืนลงในหน้า Providers ส่วน Claude Platform จะยอมรับคีย์ API ของ Anthropic ผลิตภัณฑ์ทั้งสองจะค้นพบโมเดลที่เปิดเผยต่อแต่ละข้อมูลรับรอง ใช้การขนส่ง Anthropic Messages รีเฟรชโทเค็นการเข้าถึง Claude Code เมื่อเป็นไปได้ และรองรับการนำเข้า JSON หรือ ZIP ที่ผ่านการตรวจสอบแล้ว

Muse Code ใช้การอนุญาตอุปกรณ์ Meta ที่ **Providers → Muse Code** รับลิงก์ อนุมัติรหัสบน Meta แล้วกลับมาที่ **Save credential** เชื่อมต่อโดยตรง ไม่ต้องใช้ CLI, Linux หรือ VPS โมเดลมีคำนำหน้า `muse-code/` และตั้งชื่อแสดงผลได้ แผน โควตาเซสชัน/สัปดาห์ เวลาตั้งใหม่และเวลาสังเกตแสดงเฉพาะเมื่อผู้ให้บริการส่งมา ข้อมูลที่ไม่มีไม่ได้หมายถึงเหลือ 100% การรีเฟรชตรวจสอบสมาชิกและรับคีย์อนุมานผ่านเซสชันปัจจุบัน หากเซสชันใช้ไม่ได้ให้เข้าสู่ระบบใหม่

Kiro รองรับ OAuth เบราว์เซอร์ Google/GitHub การอนุญาตอุปกรณ์ AWS และคีย์ API ช่องขั้นสูงขึ้นอยู่กับวิธี ได้แก่ภูมิภาคการทำงาน ภูมิภาคโทเค็น/URL เริ่มต้น AWS หรือ ARN โปรไฟล์สำหรับคีย์ API

การเชื่อมต่อ Ollama ได้รับการกำหนดค่าตามแต่ละจุดปลายทาง และอาจรวมคีย์ API bearer ทางเลือกสำหรับเซิร์ฟเวอร์ที่ได้รับการป้องกันหรือบนคลาวด์ Polaris ค้นพบโมเดลผ่าน `/api/tags` และกำหนดเส้นทางการอนุมานผ่าน `/api/chat` เมื่อ Polaris ทำงานใน Docker คำว่า `localhost` จะหมายถึงตัวคอนเทนเนอร์เอง ให้ใช้ที่อยู่ host-gateway หรือปลายทาง Ollama อื่นที่สามารถเข้าถึงได้ผ่านเครือข่าย

การนำเข้าCredentialsและการนำเข้าแบบกลุ่มของ Google Antigravity รองรับไฟล์เก็บถาวรสูงสุด 10 MB, ไม่เกิน 500 ไฟล์, ไฟล์ข้อมูลรับรองแต่ละไฟล์สูงสุด 2 MB และข้อมูลที่ไม่ได้บีบอัดสูงสุด 25 MB การนำเข้าผู้ให้บริการ Google AI Studio, OpenAI, Anthropic และ Ollama ใช้ขีดจำกัดที่เข้มงวดกว่าคือ 2 MB ต่อไฟล์ที่นำเข้า, 200 รายการ JSON และข้อมูลที่ไม่ได้บีบอัด 5 MB

**Credentials** (`/credentials`) จัดกลุ่มบัญชีและคีย์ตามผู้ให้บริการ หน้าต่างจัดการแสดงตัวตน โมเดล สถานะ และการทำงานที่รองรับ OAuth อาจให้ข้อมูลแผน เครดิต และโควตาตามช่วงเวลาหรือโมเดล คีย์ API ไม่ได้ให้อีเมล แผน หรือข้อมูลการเรียกเก็บเงินโดยอัตโนมัติ ข้อมูลที่ไม่มีจะแสดงว่าไม่พร้อมใช้งาน

**Download ZIP** ส่งออกข้อมูลรับรอง ส่วน **Import ZIP** ตรวจสอบและกำจัดรายการซ้ำตามผู้ให้บริการ พร้อมแจ้งข้อผิดพลาดแต่ละรายการ การนำเข้าหรือพบแค็ตตาล็อกสำเร็จไม่ยืนยันสิทธิ์อนุมาน **Test model** ส่งคำขอจริงซึ่งอาจใช้โควตาหรือเสียค่าใช้จ่าย ไฟล์ ZIP มีข้อมูลลับ หากต้องการสำรอง SQLite และการตั้งค่าทั้งหมดให้ใช้ขั้นตอนเข้ารหัสใน **Settings**

ข้อมูลรับรอง Google Antigravity ใช้ `google-antigravity-{account_fingerprint}.json` ซึ่งลายนิ้วมือได้มาจากอีเมลบัญชีที่ปรับให้เป็นมาตรฐานโดยไม่เปิดเผยอีเมล ข้อมูลรับรอง Google AI Studio ใช้ `google-ai-studio-{key_fingerprint}.json`, ข้อมูลรับรอง Grok Build OAuth ใช้ `grok-{account_fingerprint}.json`, ข้อมูลรับรอง SpaceXAI Console ใช้ `xai-console-{key_fingerprint}.json`, ข้อมูลรับรอง Codex ใช้ `openai-codex-{account_fingerprint}.json`, ข้อมูลรับรอง OpenAI Platform ใช้ `openai-platform-{key_fingerprint}.json`, ข้อมูลรับรอง Claude Code ใช้ `claude-code-{account_fingerprint}.json`, ข้อมูลรับรอง Claude Platform ใช้ `claude-platform-{key_fingerprint}.json` และการเชื่อมต่อ Ollama ใช้ `ollama-{connection_fingerprint}.json` ข้อมูลรับรองเดิม `provider_*.json` และ `xai-grok-*.json` ยังคงเข้ากันได้และจะถูกส่งออกด้วยชื่อตามแบบแผนมาตรฐาน

ชื่อโหมดข้อมูลรับรอง:

- `code_assist`: ข้อมูลรับรอง Code Assist มาตรฐาน
- `provider`: ข้อมูลรับรองแบ็กเอนด์ของผู้ให้บริการ

<a id="storage"></a>

## การจัดเก็บข้อมูล

แนะนำ SQLite โดย Compose เก็บ `/app/backend/data` ใน `polaris-data` หากใช้ Docker โดยตรงให้เมานต์ `/app/backend/data/creds` และ `/app/backend/data/logs` ไปยังตำแหน่งถาวร เช่น `/opt/polaris/creds` และ `/opt/polaris/logs`

PostgreSQL เป็นตัวเลือก ส่วน MongoDB คงไว้เพื่อความเข้ากันได้และไม่ต้องใช้ Redis ตั้งค่าเพียงตัวเดียว หากเริ่มต้นล้มเหลวระบบจะหยุด ไม่กลับไป SQLite เงียบ ๆ ฐานข้อมูลภายนอกไม่ได้เพิ่มการขยายแนวนอน ยังคงใช้ worker และ replica อย่างละหนึ่ง การสำรองแบบเข้ารหัสที่ย้ายได้รองรับเฉพาะ SQLite และไม่รองรับย้าย backend ขณะทำงาน

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

[การจัดเก็บข้อมูล](../storage.md)

การนำเข้าข้อมูลรับรองจากสภาพแวดล้อมมีให้ใช้งานได้จากแผงควบคุม กำหนดค่าหนึ่งในตัวแปรต่อไปนี้เป็น JSON ดิบ หรือใช้ตัวแปร `_B64` ที่ตรงกันสำหรับ JSON ที่เข้ารหัส base64:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

เพย์โหลดสามารถเป็นออบเจกต์ข้อมูลรับรองเดี่ยว, อาร์เรย์ หรือ `{ "credentials": [...] }`

<a id="development"></a>

## การพัฒนา

ส่วนนี้สำหรับผู้มีส่วนร่วมและการดีบักในเครื่อง การติดตั้งใช้งานจริงในระบบโปรดักชันควรใช้ Docker พร้อมวอลุ่มโฮสต์แบบถาวร

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

[เกณฑ์คุณภาพ](../quality-gates.md)แยกการตรวจสอบระดับงาน ระยะ และรุ่น `python tools/quality_gate.py --list-suites` แสดงการตรวจสอบบริการภายนอกแบบเลือกใช้ด้วย [ข้อตกลงความเข้ากันได้](../compatibility.md)คุ้มครองเส้นทาง SDK/จัดการ การย้ายข้อมูล สคีมา และตัวอย่าง

เริ่มบริการหลังจากผ่านการตรวจสอบทั้งหมด:

```bash
python backend/main.py
```

เกณฑ์มาตรฐานในการผลิตคือ Python 3.12 และปัจจุบัน CI ตรวจสอบความถูกต้องของ Python 3.12 และ 3.14 ดู [การมีส่วนร่วม](../../CONTRIBUTING.md) สำหรับเวิร์กโฟลว์ pull-request และความคาดหวังในการตรวจสอบ

<a id="deployment-notes"></a>

## หมายเหตุการติดตั้ง

- ห้ามคอมมิตไฟล์ JSON ข้อมูลรับรองหรือไฟล์ `.env` โดยเด็ดขาด
- ใช้ `API_KEY` โดยเฉพาะสำหรับการรวมเข้ากับไคลเอนต์ และใช้ `PANEL_PASSWORD` แยกต่างหากสำหรับการเข้าถึงคอนโซล
- จำกัดการเข้าถึงวอลุ่มข้อมูลรับรองแบบถาวรหรือฐานข้อมูลภายนอก และเปิดใช้งานการเข้ารหัสระดับแพลตฟอร์มเมื่อไม่มีการใช้งาน (encryption at rest) โทเค็นของผู้ให้บริการจะต้องสามารถเรียกค้นได้โดยเราเตอร์
- วาง Polaris ไว้ด้านหลัง reverse proxy พร้อม TLS เมื่อสามารถเข้าถึงได้จากภายนอก localhost
- กำหนดค่า reverse proxy เพื่อรักษา `Host` และส่งผ่าน `X-Forwarded-Proto` กำหนด `PANEL_COOKIE_SECURE=true` เมื่อรับประกันการยุติ HTTPS
- ตั้งค่า `TRUST_PROXY_HEADERS=true` เฉพาะเมื่อบริการสามารถเข้าถึงได้ผ่านพร็อกซีที่เชื่อถือได้ซึ่งเขียนทับ `X-Forwarded-For` และ `X-Forwarded-Proto` เท่านั้น
- ใช้ `GET /health` สำหรับการตรวจสอบการทำงานของกระบวนการ (liveness) และ `GET /ready` สำหรับการตรวจสอบความพร้อมที่คำนึงถึงที่จัดเก็บข้อมูล (readiness)
- telemetry ภายนอกเป็นตัวเลือก Prometheus ต้องมี `PROMETHEUS_EXPORT_ENABLED` และ `METRICS_TOKEN` ที่รัดกุม OpenTelemetry ส่งเฉพาะข้อมูลรวม ไม่ส่งเนื้อหา prompt/คำตอบ ดู[การสังเกตระบบ](../observability.md)
- อิมเมจ Docker เริ่มต้นด้วยสิทธิ์ root เพียงนานพอที่จะแก้ไขความเป็นเจ้าของไดเรกทอรีข้อมูลที่เมานต์ไว้ จากนั้นจะเรียกใช้บริการในฐานะผู้ใช้ `gateway` ที่ไม่มีสิทธิ์พิเศษ
- กำหนด `CORS_ORIGINS` เป็นต้นทางที่เชื่อถือได้ชัดเจนเมื่อไคลเอนต์เบราว์เซอร์ต้องการการเข้าถึงข้ามต้นทาง
- ก่อนอัปเดตหรือย้าย SQLite ใช้[การสำรองที่เข้ารหัสและยืนยันตัวตน](../backup-and-restore.md) เก็บไฟล์และวลีรหัสผ่านไว้นอก `polaris-data`
- การเผยแพร่อิมเมจ Docker ใช้ข้อมูลลับของที่เก็บข้อมูล `DOCKERHUB_USERNAME` และ `DOCKERHUB_TOKEN` สำหรับ Docker Hub และ `GITHUB_TOKEN` ในตัวสำหรับ GitHub Packages ที่ `ghcr.io/nguywnben/polaris` กำหนดตัวแปรที่เก็บข้อมูลทางเลือก `IMAGE_NAME` เฉพาะเมื่อเผยแพร่ไปยังชื่ออิมเมจ Docker Hub ที่กำหนดเอง
- คงค่า `WORKERS=1` และแบบจำลองแอปพลิเคชันหนึ่งชุดสำหรับซีรีส์ 1.x ที่จัดเก็บข้อมูลภายนอกไม่สามารถทดแทนการประสานงานแบบกระจายได้
- ใช้เส้นทางการจัดการมาตรฐาน `/api/credentials` นามแฝงเบต้า `/api/creds` ถูกลบออกใน 1.0.0 แล้ว
- ปฏิบัติตาม [การอัปเกรดเป็น 1.0](../upgrading-to-1.0.md) ก่อนที่จะย้ายการติดตั้งรุ่นเบต้า
- ปฏิบัติตาม [คู่มือการอัปเดต](../updating.md) เมื่ออัปเกรดอินสแตนซ์ที่ติดตั้งใช้งานหรือย้อนกลับรุ่น
- ปฏิบัติตาม [รายการตรวจสอบการเปิดตัว](../release-checklist.md) ที่ดูแลไว้ก่อนที่จะแท็กหรือโปรโมตอิมเมจ
- เก็บนโยบายการเก็บรักษาบันทึกและการหมุนเวียนข้อมูลรับรองให้สอดคล้องกับขีดจำกัดการใช้งานของคุณ
- หมุนเวียนข้อมูลรับรองทันทีหากที่เก็บข้อมูลหรือเครื่องสแกนแพลตฟอร์มรายงานความลับรั่วไหล
- Render Blueprint ใช้บริการแบบชำระเงินพร้อมดิสก์แบบถาวร บริการฟรีของ Render ใช้ระบบไฟล์ชั่วคราวและเหมาะสำหรับการประเมินแบบใช้แล้วทิ้งเท่านั้น

<a id="community-and-project-health"></a>

## ชุมชนและสุขภาพของโครงการ

- อ่าน [การมีส่วนร่วม](../../CONTRIBUTING.md) ก่อนเปิด pull request
- รายงานช่องโหว่ผ่านกระบวนการส่วนตัวใน [นโยบายความปลอดภัย](../../SECURITY.md)
- ตรวจสอบ [บันทึกการเปลี่ยนแปลง](../../CHANGELOG.md) สำหรับการเปลี่ยนแปลงระดับรุ่น
- ปฏิบัติตาม [หลักจรรยาบรรณ](../../CODE_OF_CONDUCT.md) ในทุกพื้นที่ของโครงการ

<a id="acknowledgements-inspirations"></a>

## การแสดงความขอบคุณ & แรงบันดาลใจ

Polaris ยืนอยู่บนไหล่ของชุมชนเราเตอร์ AI, การวัดระยะไกล และเกตเวย์แบบโอเพนซอร์ส เราขอแสดงความขอบคุณต่อผู้สร้างและผู้ดูแลโครงการเหล่านี้:

| โครงการ | คำอธิบาย | ดาว |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | แรงบันดาลใจสำหรับการจัดการคีย์แบบหลายผู้ให้บริการและการรวม API บนเว็บ | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | ผู้บุกเบิกพร็อกซีหลายรูปแบบและเลเยอร์การแปลงโปรโตคอลสำหรับ AI coding CLI | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | พร็อกซี LLM แบบรวมศูนย์ที่เป็นมาตรฐาน, การกระจายโหลด และการกำหนดเส้นทางสำรอง | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | สถาปัตยกรรมเกตเวย์ AI ความเร็วสูงพิเศษ, กลยุทธ์การกำหนดเส้นทาง และรูปแบบการสำรองที่ยืดหยุ่น | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | แพลตฟอร์มวิศวกรรม LLM แบบโอเพนซอร์ส, การติดตามร่องรอย, การสังเกตการณ์ และการรับข้อมูลเมตริก | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

<a id="license"></a>

## ใบอนุญาต

Polaris เผยแพร่ภายใต้ [ใบอนุญาต MIT](../../LICENSE)
