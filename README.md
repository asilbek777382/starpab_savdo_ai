<p align="center"><img src="branding/navbatchi-logo.svg" alt="Navbatchi AI — 24/7 sotuvchi-operator" width="460"></p>

# Navbatchi AI — Telegram'da 24/7 AI sotuvchi

Kichik do'konlar uchun sun'iy intellektli sotuvchi-operator: kechasi ham, band paytda ham navbatda. Mijozlarga o'zbek (lotin/kirill) va rus tilida javob beradi,
katalogdan mahsulot topadi, buyurtmani rasmiylashtiradi yoki telefon raqamini olib operatorga uzatadi.

Asosiy tamoyil: **AI hech narsani o'ylab topmaydi.** Narx, qoldiq va yetkazib berish narxi faqat bazadan
(toollar orqali) olinadi, buyurtma summasi serverda qayta hisoblanadi.

## Nimalar tayyor (backend MVP)

| Qism | Tavsif |
|---|---|
| Kanallar | Telegram Business (do'kon akkauntidan javob), oddiy bot rejimi (`t.me/<bot>?start=shop_<id>`) |
| AI | Claude, tool calling: `search_products`, `get_product`, `send_product_photos`, `update_cart`, `get_delivery_info`, `create_order`, `save_lead`, `handoff_to_human` |
| AI rejimlari | **sell** — suhbatdan buyurtmagacha; **lead** — tanishtiradi, telefon raqamini so'raydi, operatorga yuboradi |
| Vazifalar | Sotuvchi AI'ga erkin matnda ssenariy yozadi (`/tasks` yoki API) |
| Katalog | CRUD, Excel/CSV import (shablon bilan), variantlar (razmer/rang/qoldiq), rasmlar |
| Qidiruv | pg_trgm (lotin/kirill/rus, imlo xatolari) + ixtiyoriy pgvector, RRF bilan birlashtirish |
| Handoff | "operator", shikoyat, qaytarish kabi so'zlar; sotuvchi o'zi yozsa AI 30 daqiqa jim turadi |
| Xabarnomalar | Yangi buyurtma (Tasdiqlash/Bekor/Yuborildi), lid (operatorlar guruhiga), handoff |
| Ishonchlilik | update_id dedup, debounce (2.5 s) + suhbat lock, rate limit, LLM fallback, telefonni maskalash |
| Billing | 14 kunlik trial, tariflar va oylik suhbat limiti, token va xarajat hisobi |
| REST API | Mini App uchun (Telegram `initData` HMAC autentifikatsiyasi) |

Keyingi bosqichlar: Instagram Direct, Mini App (React), Click/Payme avtomatik to'lov.

## Arxitektura

```
Telegram ──webhook──▶ FastAPI (dedup, xabarni saqlash) ──▶ Redis/arq navbat
                                                              │ debounce + lock
                                                              ▼
                                   AI worker ──▶ Claude (tool calling) ──▶ PostgreSQL + pgvector
                                       │
                                       └──▶ mijozga javob / sotuvchiga xabarnoma
Mini App ──REST──▶ FastAPI ──▶ PostgreSQL
```

Kod: `backend/app/` — `ai/` (agent, prompt, toollar, LLM), `services/` (katalog, qidiruv, savat, buyurtma, lid,
limitlar), `telegram/` (handlerlar, xabarnomalar), `api/` (REST), `worker/` (arq).

## Ishga tushirish

### Docker Compose

```bash
cp .env.example .env      # BOT_TOKEN, ANTHROPIC_API_KEY, PUBLIC_BASE_URL ni to'ldiring
docker compose up -d --build
```

`migrate` servisi `alembic upgrade head` qiladi, keyin `api` (8000-port) va `worker` ishga tushadi.
`PUBLIC_BASE_URL` HTTPS bo'lishi kerak (Nginx + Let's Encrypt): API ishga tushganda Telegram webhook'ni o'zi o'rnatadi.

### Lokal (dasturlash uchun)

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload         # API
uv run arq app.worker.settings.WorkerSettings  # AI worker
```

PostgreSQL 16 da `vector` va `pg_trgm` kengaytmalari bo'lishi kerak (`pgvector/pgvector:pg16` image'ida bor).

## Telegram sozlash

1. @BotFather'da bot yarating va Bot Settings → **Business Mode** ni yoqing.
2. Sotuvchi botga `/start` yozadi: do'kon yaratiladi va 14 kunlik trial boshlanadi.
3. Sotuvchi o'z akkauntida: Sozlamalar → **Telegram Business → Chatbots** → `@bot_username`, so'ng
   "xabarlarga javob berish" ruxsatini yoqadi.
4. Operatorlar guruhi (ixtiyoriy): botni guruhga qo'shing va guruhda `/leads_here` yozing. Lidlar shu guruhga keladi.

Sotuvchi buyruqlari:

| Buyruq | Vazifasi |
|---|---|
| `/status` | Do'kon holati, rejim, limitlar |
| `/mode sell` / `/mode lead` | AI rejimi: sotish yoki lid yig'ish |
| `/tasks <matn>` | AI uchun vazifalar, masalan: "Avval do'konni tanishtir, keyin telefon raqamini so'ra" |
| `/leads_here` | Operatorlar guruhida: lidlar shu guruhga keladi |
| `/ai_on`, `/ai_off` | AI'ni yoqish/to'xtatish |

## REST API (Mini App uchun)

Header: `Authorization: tma <Telegram.WebApp.initData>`. Bir nechta do'kon bo'lsa `X-Shop-Id` bilan tanlanadi.
To'liq ro'yxat: `/docs`.

`/api/me`, `/api/shop`, `/api/settings` (FAQ, yetkazib berish hududlari, rejim, vazifalar, lid guruhi),
`/api/categories`, `/api/products` (+ `/import`, `/api/products-import-template`), `/api/orders`,
`/api/leads`, `/api/conversations` (+ `/{id}/ai` — "men o'zim javob beraman"), `/api/test-chat`, `/api/stats`.

## Testlar va sifat

```bash
cd backend
uv run ruff check . && uv run pytest    # Postgres (aiop_test bazasi) va Redis kerak
```

Testlar haqiqiy Postgres/Redis bilan ishlaydi. LLM va Telegram bot soxta (skriptlangan) obyektlar bilan
almashtiriladi: to'liq oqimlar (savol → savat → buyurtma, lid rejimi, handoff, webhook, API) tekshiriladi.

**Eval** — haqiqiy Claude bilan 30 ta holat (uz lotin/kirill, rus, aralash, xatolar, injection, lid rejimi):

```bash
ANTHROPIC_API_KEY=... uv run python -m eval.run_eval --min 0.85
```

Har bir prompt yoki model o'zgarishidan keyin ishga tushiring. Haqiqiy suhbatlardagi xatolarni
`eval/cases.jsonl` ga qo'shib boring (maqsad: 100–200 holat).

## Brend

`branding/` papkasida: `navbatchi-mark.svg` (belgi), `navbatchi-logo.svg` / `navbatchi-logo-dark.svg` (yorug'/qorong'i fon),
`navbatchi-avatar-512.png` (Telegram bot avatari: @BotFather → Edit Bot → Edit Botpic).

Belgi — o'zbek koshin naqshidagi 8 qirrali yulduz ichida "yozmoqda…" holatidagi chat pufakchasi.
Ranglar: firuza `#14B8A6` → `#0F766E`, oltin `#EAB308`, to'q firuza matn `#134E4A`, krem fon `#FFFBEB`.
Shrift: Rubik (logoda vektorga o'girilgan).
