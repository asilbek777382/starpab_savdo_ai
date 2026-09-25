# Navbatchi AI — Claude uchun qo'llanma

Bu fayl shu repoda ishlaydigan har bir Claude sessiyasi uchun. Avval shuni o'qing: loyiha nima, qanday ishlaydi,
qanday sinaladi va **serverga qanday joylanadi** (qat'iy qoidalar bilan). Batafsil tavsif `README.md` da.

## 1. Loyiha nima

**Navbatchi AI** kichik do'konlar uchun 24/7 ishlaydigan AI sotuvchi-operator. U Telegram va Instagram'da mijozlarga
o'zbek (lotin/kirill) va rus tilida javob beradi. Ishlash tartibi:

- katalogdan mahsulot qidiradi va rasmlarini yuboradi;
- savatni yig'adi va buyurtmani rasmiylashtiradi;
- lid rejimida telefon raqamini so'raydi;
- kerak bo'lsa suhbatni odamga uzatadi.

**Narxni hech qachon o'ylab topmaydi**: hamma narx va qoldiq bazadan, tool calling orqali olinadi.

Kim nima qiladi:
- **Mijoz** do'konning Telegram akkauntiga (Telegram Business), botga yoki Instagram Direct'ga yozadi.
- **Sotuvchi (do'kon egasi)** web panelda (`/app`) ro'yxatdan o'tadi. U yerda katalog, AI sozlamalari, ulash, tarif va
  to'lov, xodimlar bo'limlari bor. Buyurtma va lid xabarlari unga Telegram bot orqali keladi.
- **Operator (xodim)** egasi taklif qilgan xodim. U buyurtmalar, lidlar, suhbatlar, katalog va test chat bilan ishlaydi.
- **Platforma admini** (`is_platform_admin`) `/app/admin` da barcha do'konlar, tariflar va qo'lda kiritilgan to'lovlarni boshqaradi.

## 2. Tuzilma

```
backend/                 FastAPI + SQLAlchemy 2 (async) + arq worker + aiogram 3
  app/main.py            API ilovasi (routerlar ro'yxati shu yerda)
  app/config.py          barcha sozlamalar (.env dan; nomlari katta harf bilan)
  app/ai/                agent (Claude tool-use sikli), prompt, tool'lar, LLM klienti (haiku → sonnet fallback)
  app/api/               REST: auth, shops, catalog, orders, leads, conversations, test_chat, stats,
                         payments (billing + Payme/Click callback), staff, instagram, admin, webhooklar
  app/services/          biznes-logika: ingest, conversation (javob sikli), cart, orders, search, billing,
                         staff, reminders (savat eslatmasi), tts, handoff, usage (limitlar), auth ...
  app/payments/          payme.py (Merchant API JSON-RPC), click.py (SHOP API prepare/complete)
  app/telegram/          aiogram handlerlari, polling, xabarnomalar (notify.py)
  app/instagram/         Graph API klienti va outbound
  app/worker/            arq: process_conversation, enrich_product, cron: instagram token, savat eslatmasi
  alembic/versions/      migratsiyalar 0001…0006 (konteyner ishga tushganda `migrate` servisi qo'llaydi)
  tests/                 pytest (Postgres + Redis kerak), fakes.py — FakeLLM/FakeBot/FakeTTS
web/                     React 19 + Vite + Tailwind 4 + TanStack Query, i18n uz/ru
  index.html, src/landing/  statik landing (SEO)
  src/app/               panel SPA (/app): pages/, locales.ts (uz va ru bir xil kalitlar), types.ts
  e2e/panel.mjs          Playwright E2E (ro'yxatdan o'tishdan mobil ko'rinishgacha)
deploy/
  install_remote.sh      O'Z KOMPYUTERDAN serverga o'rnatish/yangilash (SSH orqali)
  server.sh              serverda: preflight | up | status | logs
  nginx.conf             web konteyner ichidagi nginx: /api /tg /ig → api, qolgani statik
  secrets.env.example    kalitlar namunasi (haqiqiysi deploy/secrets.env — git'da yo'q)
docker-compose.yml       loyiha nomi `navbatchi`: postgres(pgvector) redis migrate api worker bot(polling) web
branding/                logo (B2: sakkiz qirrali yulduz + chat pufagi, teal/oltin)
```

## 3. Qanday ishlaydi (xabar oqimi)

1. Telegram yangilanishi keladi. `BOT_MODE=polling` bo'lsa `bot` servisi uni oladi, webhook rejimida esa `/tg/webhook/<secret>` qabul qiladi.
   Instagram xabari `/ig/webhook` ga keladi (X-Hub-Signature-256 tekshiriladi).
2. `services/ingest.py` mijoz va suhbatni topadi yoki yaratadi, xabarni saqlaydi va 24 soatlik oynani hisoblaydi (billing uchun).
   Keyin `process_conversation` job'ini debounce (2.5 s) bilan navbatga qo'yadi.
3. Worker `services/conversation.py::reply_to_conversation` ni suhbat qulfi (`lock:conv:<id>`) ostida chaqiradi.
   Bu yerda tekshiriladi: AI yoqilganmi, suhbat odamga o'tkazilmaganmi, tarif limiti, kunlik token limiti.
   So'ng ovozli xabarlar matnga aylantiriladi (STT), rasmlar Claude'ga beriladi va agent tool'lar bilan javob yozadi.
4. Javob `services/outbound.py` orqali mijozga ketadi: Telegram Business, bot yoki Instagram. Instagram'da 24 soatlik oyna amal qiladi.
   Kerak bo'lsa javob ovozli xabar sifatida ham yuboriladi (Azure TTS).
5. Buyurtma, lid yoki handoff bo'lsa `telegram/notify.py` sotuvchiga va Telegram'ni ulagan xodimlarga xabar yuboradi.
   Xabar commit'dan keyin ketadi.
6. Cron har 10 daqiqada tashlab ketilgan savatlarni tekshiradi (`services/reminders.py`) va bitta eslatma yuboradi.
   Kunlik cron Instagram tokenlarini yangilaydi.

Sotuvchi o'z akkauntidan mijozga yozsa, AI shu suhbatda 30 daqiqa jim turadi.

## 4. Lokal ishga tushirish va testlar

Talablar: Python 3.12 + `uv`, Node 22, PostgreSQL 16 (pgvector, pg_trgm), Redis.

```bash
# backend testlari (Postgres: aiop/aiop@localhost:5432/aiop_test, Redis: db 15 — tests/conftest.py)
cd backend && uv sync && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
# migratsiyalar modelga mosmi
uv run alembic upgrade head && uv run alembic check
# web
cd web && npm ci && npm run build          # tsc + vite (web'da alohida lint skripti yo'q)
# E2E: backend :8000 va `npx vite preview` :4173 ishlab turganda
node e2e/panel.mjs http://localhost:4173 /tmp/shots
```

Qoidalar: har bir o'zgarishga test yozing. Kod izohlari o'zbekcha. Ruff qator uzunligi 120. Yangi panel matni `locales.ts`
ga **uz va ru** ikkalasiga ham qo'shiladi (TypeScript tekshiradi). DB o'zgarsa yangi alembic migratsiya kerak:
`uv run alembic revision --autogenerate -m "..." --rev-id 0007`, so'ng `ruff check --fix`.

## 5. Serverga joylash (runbook)

**Server:** `root@204.168.131.237`, SSH kalit `~/.ssh/aslsmm_deploy` (foydalanuvchi kompyuterida).
**Papka:** `/home/online_savdo`. Serverda foydalanuvchining **boshqa loyihalari ham bor**.

### Qat'iy qoidalar (buzmang)

- Faqat `/home/online_savdo` ichida ishlang. `/etc`, tizim paketlari, boshqa konteynerlar va volume'lar, mavjud nginx,
  firewall — **tegilmaydi**. `docker system prune`, `docker volume rm`, `docker compose down -v` taqiqlanadi.
- Docker yoki `docker compose` yo'q bo'lsa — to'xtang va foydalanuvchidan so'rang (o'rnatish papkadan tashqariga chiqadi).
- Port tashqaridan ochilmasa (firewall/ufw), portni o'zingiz ochmang: foydalanuvchiga ayting va ruxsat so'rang.
- 80/443 portlar boshqa loyihaniki bo'lishi mumkin. Navbatchi 8090–8099 oralig'idagi bo'sh portda ishlaydi (skript o'zi tanlaydi).
- Kalitlarni chatga, logga yoki commit'ga chiqarmang. Ular faqat `deploy/secrets.env` (lokal, git'da yo'q)
  va serverdagi `/home/online_savdo/.env` (chmod 600) da turadi.

### Birinchi o'rnatish

1. Kod: `git clone -b claude/gracious-brahmagupta-4vl0o5 https://github.com/asilbek777382/starpab_savdo_ai.git`
   (yoki foydalanuvchi bergan zip — skript `.git` bo'lmasa ham ishlaydi).
2. SSH tekshiruvi: `ssh -i ~/.ssh/aslsmm_deploy -o BatchMode=yes root@204.168.131.237 'echo ok'`.
3. Kalitlar: `cp deploy/secrets.env.example deploy/secrets.env`. Foydalanuvchi faylni **o'zi** to'ldirgani ma'qul.
   Majburiy qiymatlar: `ANTHROPIC_API_KEY`, `BOT_TOKEN`, `BOT_USERNAME`, `ADMIN_PHONE`, `ADMIN_PASSWORD`.
   Qolganlari ixtiyoriy.
4. Ishga tushirish (repo ildizida): `bash deploy/install_remote.sh`. Skript quyidagilarni bajaradi:
   - preflight (hech narsani o'zgartirmaydi);
   - bo'sh port tanlaydi;
   - kodni `/home/online_savdo` ga ko'chiradi;
   - `.env` yozadi;
   - `docker compose --profile polling up -d --build` ni ishga tushiradi (migratsiyalar avtomatik);
   - platforma adminini yaratadi.
   Birinchi build bir necha daqiqa davom etadi.
5. Tekshirish:
   - `ssh ... "APP_DIR=/home/online_savdo bash /home/online_savdo/deploy/server.sh status"`. Hamma servis `Up` bo'lishi, `health: 200` chiqishi kerak.
   - `... server.sh logs bot` da "Start polling" bo'lishi kerak. `... server.sh logs api worker` da xato bo'lmasligi kerak.
   - Brauzerda `http://204.168.131.237:<port>/` (landing) va `/app/` (panel) ochilishi kerak. Admin telefon va paroli bilan kirib ko'ring.
6. Telegram: @BotFather → bot → Bot Settings → **Business Mode → ON**. Sotuvchi o'z Telegram akkauntida:
   Settings → Business → Chatbots → botni qo'shadi. Panelda: Ulash → "Telegram'ni ulash".

### Yangilash

`git pull && bash deploy/install_remote.sh`. Mavjud `.env` saqlanadi, migratsiyalar avtomatik qo'llanadi.
Kalit qo'shish yoki almashtirish uchun `deploy/secrets.env` ni tahrirlang, so'ng `bash deploy/install_remote.sh --reconfigure`.
Bu buyruq `SECRET_KEY`, `POSTGRES_PASSWORD`, `WEBHOOK_SECRET`, `IG_VERIFY_TOKEN` ni saqlab qoladi.

### Muammolar

| Belgi | Sabab / yechim |
|---|---|
| `Permission denied (publickey)` | Kalit yo'li noto'g'ri: `KEY=~/.ssh/... bash deploy/install_remote.sh` |
| `Bo'sh port topilmadi` | `PORTS="8100 8101" bash deploy/install_remote.sh` |
| api `password authentication failed` | `.env` dagi `POSTGRES_PASSWORD` volume'dagidan farq qiladi. Volume'ni o'chirmang; eski parolni qaytaring |
| Bot javob bermaydi | `logs bot`: token noto'g'ri yoki boshqa joyda shu token bilan webhook/polling ishlayapti |
| AI "texnik nosozlik" deydi | `logs worker`: `ANTHROPIC_API_KEY` noto'g'ri yoki balans tugagan |
| Sayt tashqaridan ochilmaydi | Serverda `curl 127.0.0.1:<port>/health` 200 bo'lsa, muammo firewall'da. Foydalanuvchidan so'rang |

## 6. Nima uchun HTTPS domen kerak

IP va HTTP bilan quyidagilar ishlaydi: landing, panel, Telegram (polling), AI, ovoz, xodimlar, savat eslatmasi.
**Instagram, Payme va Click** HTTPS domen talab qiladi (webhook va callback).

Domen bo'lganda:
1. `PUBLIC_URL=https://domen` ni yozib `--reconfigure` qiling (`COOKIE_SECURE=true` o'zi qo'yiladi).
2. Serverdagi mavjud reverse-proxy'ga Navbatchi portiga yo'naltirish qo'shing. Bu papkadan tashqarida, shuning uchun
   **faqat foydalanuvchi ruxsati bilan**.

Callback manzillari:
- Payme: `https://domen/api/payments/payme`
- Click: `.../api/payments/click/prepare` va `.../click/complete`
- Instagram webhook: `https://domen/ig/webhook` (verify token `.env` da)

## 7. Holat va keyingi ishlar

Tayyor:
- MVP yadrosi (Claude tool calling);
- lid rejimi va vazifalar;
- landing va panel (uz/ru, telefon + parol bilan kirish), platforma admini;
- Instagram Direct;
- ovozli javoblar (Azure TTS);
- rasm bo'yicha qidiruv;
- Payme/Click obuna to'lovi;
- xodimlar va rollar;
- tashlab ketilgan savat eslatmasi.

Tekshirilmagan yoki qilinmagan:
- Payme tranzaksiya timeout'i (12 soat, `payments/payme.py::TRANSACTION_TIMEOUT_MS`) rasmiy hujjat bilan
  solishtirilmagan. Ulashdan oldin Payme sandbox'da sinang.
- SMS orqali telefonni tasdiqlash, WhatsApp — hali yo'q.
- `aslsmm_deploy` SSH kaliti avval chatda ulashilgan edi. Uni almashtirish (rotate) tavsiya qilinadi.
