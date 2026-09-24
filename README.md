<p align="center"><img src="branding/navbatchi-logo.svg" alt="Navbatchi AI — 24/7 sotuvchi-operator" width="460"></p>

# Navbatchi AI — Telegram'da 24/7 AI sotuvchi

Kichik do'konlar uchun sun'iy intellektli sotuvchi-operator: kechasi ham, band paytda ham navbatda. Mijozlarga o'zbek (lotin/kirill) va rus tilida javob beradi,
katalogdan mahsulot topadi, buyurtmani rasmiylashtiradi yoki telefon raqamini olib operatorga uzatadi.

Asosiy tamoyil: **AI hech narsani o'ylab topmaydi.** Narx, qoldiq va yetkazib berish narxi faqat bazadan
(toollar orqali) olinadi, buyurtma summasi serverda qayta hisoblanadi.

## Nimalar tayyor (backend MVP)

| Qism | Tavsif |
|---|---|
| Kanallar | Telegram Business (do'kon akkauntidan javob), oddiy bot rejimi (`t.me/<bot>?start=shop_<id>`), Instagram Direct |
| AI | Claude, tool calling: `search_products`, `get_product`, `send_product_photos`, `update_cart`, `get_delivery_info`, `create_order`, `save_lead`, `handoff_to_human` |
| AI rejimlari | **sell** — suhbatdan buyurtmagacha; **lead** — tanishtiradi, telefon raqamini so'raydi, operatorga yuboradi |
| Vazifalar | Sotuvchi AI'ga erkin matnda ssenariy yozadi (`/tasks` yoki API) |
| Katalog | CRUD, Excel/CSV import (shablon bilan), variantlar (razmer/rang/qoldiq), rasmlar |
| Qidiruv | pg_trgm (lotin/kirill/rus, imlo xatolari) + ixtiyoriy pgvector, RRF bilan birlashtirish |
| Handoff | "operator", shikoyat, qaytarish kabi so'zlar; sotuvchi o'zi yozsa AI 30 daqiqa jim turadi |
| Xabarnomalar | Yangi buyurtma (Tasdiqlash/Bekor/Yuborildi), lid (operatorlar guruhiga), handoff |
| Ishonchlilik | update_id dedup, debounce (2.5 s) + suhbat lock, rate limit, LLM fallback, telefonni maskalash |
| Billing | 14 kunlik trial, tariflar va oylik suhbat limiti, token va xarajat hisobi |
| Web sayt | Landing (uz/ru) + boshqaruv paneli: telefon + parol bilan kirish, platforma admini |
| REST API | Panel (cookie sessiya) va Telegram Mini App (`initData` HMAC) uchun |

Keyingi bosqichlar: Click/Payme avtomatik to'lov, SMS orqali telefonni tasdiqlash, WhatsApp.

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
limitlar, auth), `telegram/` (handlerlar, xabarnomalar), `api/` (REST), `worker/` (arq).
`web/` — landing (`index.html`, statik) va panel SPA (`app/`, React + Tailwind). `deploy/nginx.conf` — ikkalasini
beradi va `/api`, `/tg` ni backend'ga proksi qiladi.

## Ishga tushirish

### Docker Compose

```bash
cp .env.example .env      # BOT_TOKEN, ANTHROPIC_API_KEY, PUBLIC_BASE_URL ni to'ldiring
docker compose up -d --build
```

`migrate` servisi `alembic upgrade head` qiladi, keyin `api`, `worker` va `web` (nginx, 80-port) ishga tushadi.
Sayt: `http://<server>/` (landing), `http://<server>/app/` (panel).

`PUBLIC_BASE_URL` HTTPS bo'lishi kerak: oldiga TLS qo'ying (masalan, Caddy yoki certbot bilan nginx) — API ishga
tushganda Telegram webhook'ni o'zi o'rnatadi, sessiya cookie'si ham `Secure`.

Birinchi platforma admini:

```bash
docker compose exec api python -m app.cli make-admin +998901234567
```

### Serverga bitta buyruq bilan (o'z kompyuteringizdan)

```bash
git checkout claude/gracious-brahmagupta-4vl0o5 && git pull
bash deploy/install_remote.sh            # HOST=root@<ip> KEY=~/.ssh/<kalit> APP_DIR=/home/online_savdo (standart)
```

Skript serverni tekshiradi (Docker bo'lmasa to'xtaydi), 8090–8099 oralig'idan bo'sh port tanlaydi, kodni `APP_DIR` ga
ko'chiradi, kalitlarni yashirin so'rab serverdagi `.env` ga (chmod 600) yozadi, `docker compose` bilan ishga tushiradi va
platforma adminini yaratadi. Qayta ishga tushirish — yangilash (mavjud `.env` saqlanadi; `--reconfigure` — qayta sozlash).

### Domensiz serverga (boshqa loyihalar bilan yonma-yon)

Domen/HTTPS bo'lmasa bot **polling** rejimida ishlaydi (webhook shart emas), sayt esa alohida portda:

```bash
# .env: BOT_MODE=polling, WEB_PORT=8090, COOKIE_SECURE=false, PUBLIC_BASE_URL=http://<server-ip>:8090
bash deploy/server.sh preflight   # faqat tekshiradi: docker, band portlar, disk, xotira
bash deploy/server.sh up          # docker compose --profile polling up -d --build
bash deploy/server.sh status      # konteynerlar va /health
```

Compose loyiha nomi `navbatchi` — konteyner va volume nomlari serverdagi boshqa loyihalar bilan to'qnashmaydi;
postgres va redis tashqariga port ochmaydi. HTTP'da parol ochiq kanal orqali o'tadi — imkon bo'lishi bilan domen va
HTTPS ulang, so'ng `BOT_MODE=webhook`, `COOKIE_SECURE=true`.

### Lokal (dasturlash uchun)

```bash
cd backend
uv sync
uv run alembic upgrade head
COOKIE_SECURE=false uv run uvicorn app.main:app --reload   # API (8000)
uv run arq app.worker.settings.WorkerSettings              # AI worker

cd web
npm install
npm run dev        # http://localhost:5173 (landing), /app/ (panel); /api → 8000 ga proksi
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

## Instagram sozlash

Instagram Direct **Instagram API with Instagram Login** orqali ishlaydi (Facebook sahifa shart emas). Webhook uchun
**HTTPS domen kerak** — polling rejimi Instagram uchun yo'q.

1. [developers.facebook.com](https://developers.facebook.com) da ilova yarating (Business turi) va **Instagram** mahsulotini
   qo'shing → "API setup with Instagram login".
2. **Business login settings**: OAuth redirect URI — `https://<domen>/api/instagram/callback`.
3. **Webhooks**: Callback URL — `https://<domen>/ig/webhook`, Verify token — `.env` dagi `IG_VERIFY_TOKEN`;
   `messages` maydoniga obuna bo'ling.
4. `.env`: `IG_APP_ID`, `IG_APP_SECRET`, `IG_VERIFY_TOKEN`; `PUBLIC_BASE_URL=https://<domen>`.
5. Ruxsatlar: `instagram_business_basic`, `instagram_business_manage_messages`. App Review'dan oldin faqat ilovaga
   **Instagram tester** sifatida qo'shilgan akkauntlar ulana oladi; boshqa do'konlar uchun Advanced Access (App Review,
   screencast) kerak — arizani ertaroq topshiring.

Sotuvchi tomoni: Instagram ilovasida Sozlamalar → Xabarlar → Ulangan vositalar → "Xabarlarga ruxsat berish" ni yoqadi,
so'ng panelda **Ulash → Instagram'ni ulash**. Token shifrlangan holda saqlanadi va har kuni (worker cron) muddati
yaqinlashganda yangilanadi. Instagram qoidasi: mijozning oxirgi xabaridan keyin **24 soat** ichida yozish mumkin —
buyurtma holati xabarlari ham shu oyna ichida yuboriladi. Sotuvchi Instagram'dan o'zi javob yozsa, AI shu suhbatda
jim turadi. Instagram Biznes va Pro tariflarida (va bepul sinovda) ochiq.

## Web panel

Sotuvchi saytda **telefon + parol** bilan ro'yxatdan o'tadi (do'kon va 14 kunlik sinov yaratiladi). Panel bo'limlari:
bosh sahifa (ishga tushirish ro'yxati, statistika, kunlik grafiklar), buyurtmalar, lidlar, suhbatlar (AI'ni to'xtatish),
katalog (Excel import), AI sozlamalari (sotish/lid rejimi, vazifalar, qoidalar), do'kon ma'lumotlari (yetkazib berish
hududlari), Telegram'ni ulash, test chat, profil. Platforma admini (`is_platform_admin`) `/app/admin` da barcha
do'konlarni, tariflarni va qo'lda to'lovlarni boshqaradi.

Telegram bilan bog'lash: panelda "Telegram'ni ulash" → botda Start (xabarnomalar shu Telegram'ga keladi).
Botda ro'yxatdan o'tgan sotuvchi botga `/web` yozadi — saytga bir martalik kirish havolasi keladi.

## REST API

Panel: httpOnly cookie sessiya (`/api/auth/*`). Telegram Mini App: `Authorization: tma <initData>`.
Bir nechta do'kon bo'lsa `X-Shop-Id` bilan tanlanadi. To'liq ro'yxat: `/docs`.

`/api/auth/*` (register, login, logout, me, password, telegram-link, magic), `/api/instagram/*` (connect, callback,
disconnect), `/api/me`, `/api/shop`, `/api/channels`, `/api/settings` (FAQ, yetkazib berish hududlari, rejim, vazifalar, lid guruhi),
`/api/categories`, `/api/products` (+ `/import`, `/api/products-import-template`), `/api/orders`,
`/api/leads`, `/api/conversations` (+ `/{id}/ai` — "men o'zim javob beraman"), `/api/test-chat`, `/api/stats`
(+ `/daily`), `/api/admin/*` (platforma admini).

## Testlar va sifat

```bash
cd backend
uv run ruff check . && uv run pytest    # Postgres (aiop_test bazasi) va Redis kerak

cd web
npm run typecheck && npm run build
# E2E (backend 8000 va `npx vite preview` 4173 ishlab turganda):
node e2e/panel.mjs http://localhost:4173 ./shots
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
