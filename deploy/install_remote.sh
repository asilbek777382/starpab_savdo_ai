#!/usr/bin/env bash
# Navbatchi AI'ni serverga o'rnatish / yangilash — O'Z KOMPYUTERINGIZDAN ishga tushiring (repo ildizida):
#
#   bash deploy/install_remote.sh
#
# Hamma ish serverdagi $APP_DIR ichida bajariladi: tizim paketlari, /etc, boshqa konteynerlar va nginx'ga
# tegilmaydi. Kalitlar faqat serverdagi .env fayliga (chmod 600) yoziladi, ekranga chiqarilmaydi.
#
# Kalitlarni berish (ikki yo'l):
#   1) deploy/secrets.env fayli (namuna: deploy/secrets.env.example) — skript hech narsa so'ramaydi.
#      Claude Code yoki boshqa avtomatik vosita ishga tushirganda shu yo'l kerak.
#   2) Fayl bo'lmasa va terminal interaktiv bo'lsa — kalitlar yashirin so'raladi.
#
# Sozlash (ixtiyoriy):
#   HOST=root@1.2.3.4  KEY=~/.ssh/boshqa_kalit  APP_DIR=/home/online_savdo  bash deploy/install_remote.sh
#   SECRETS_FILE=boshqa/yo'l.env bash deploy/install_remote.sh
#   bash deploy/install_remote.sh --reconfigure   # server .env ni qayta yozish (kalitlarni almashtirish)
#
# --reconfigure ham SECRET_KEY, POSTGRES_PASSWORD, WEBHOOK_SECRET, IG_VERIFY_TOKEN ni saqlab qoladi —
# aks holda mavjud baza va sessiyalar ishlamay qoladi.
set -euo pipefail

HOST="${HOST:-root@204.168.131.237}"
KEY="${KEY:-$HOME/.ssh/aslsmm_deploy}"
APP_DIR="${APP_DIR:-/home/online_savdo}"
PORTS="${PORTS:-8090 8091 8092 8093 8094 8095 8096 8097 8098 8099}"
SECRETS_FILE="${SECRETS_FILE:-deploy/secrets.env}"
RECONFIGURE=0
[ "${1:-}" = "--reconfigure" ] && RECONFIGURE=1

# Testlar uchun: SSH_CMD="bash -c" bilan lokal "server"
# remote    — stdin ishlatmaydi (klaviatura kiritmasini "yutib" yubormasligi uchun /dev/null)
# remote_in — stdin serverga uzatiladi (fayl, .env, parol)
if [ -n "${SSH_CMD:-}" ]; then
  remote_in() { ${SSH_CMD} "$1"; }
  SERVER_IP="${SERVER_IP:-127.0.0.1}"
else
  remote_in() { ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes "$HOST" "$1"; }
  SERVER_IP="${SERVER_IP:-${HOST#*@}}"
fi
remote() { remote_in "$1" </dev/null; }

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mXATO: %s\033[0m\n' "$*" >&2; exit 1; }
rand() { openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
ask() { local v; read -r -p "$1: " v; printf '%s' "$v"; }
ask_secret() { local v; read -r -s -p "$1: " v; echo >&2; printf '%s' "$v"; }

[ -f docker-compose.yml ] && [ -f deploy/server.sh ] || die "Skriptni repo ildizida ishga tushiring (docker-compose.yml bor papkada)"

# Kalitlar fayli: faqat KEY=VALUE qatorlar o'qiladi (fayl bajarilmaydi)
INTERACTIVE=0
[ -t 0 ] && INTERACTIVE=1
if [ -f "$SECRETS_FILE" ]; then
  echo "Kalitlar fayli: $SECRETS_FILE"
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]] || continue
    name="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
    value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
    if [ -z "${!name:-}" ]; then printf -v "$name" '%s' "$value"; fi   # muhitdagi qiymat ustun
  done < "$SECRETS_FILE"
  INTERACTIVE=0
fi

# need NOM "savol" secret(1/0) majburiy(1/0)
need() {
  local name=$1 prompt=$2 secret=$3 required=$4 val="${!1:-}"
  if [ -z "$val" ] && [ "$INTERACTIVE" -eq 1 ]; then
    if [ "$secret" = 1 ]; then val="$(ask_secret "$prompt")"; else val="$(ask "$prompt")"; fi
  fi
  if [ -z "$val" ] && [ "$required" = 1 ]; then
    die "$name kerak. $SECRETS_FILE ga yozing (namuna: deploy/secrets.env.example)"
  fi
  printf -v "$name" '%s' "$val"
}

if [ -d .git ] && command -v git >/dev/null; then SRC="git"; else SRC="tar"; fi

say "1/6 Server tekshiruvi (hech narsa o'zgartirilmaydi)"
remote_in "APP_DIR='$APP_DIR' bash -s -- preflight" < deploy/server.sh
remote "command -v docker >/dev/null && docker compose version >/dev/null 2>&1" || die \
  "Serverda Docker yoki 'docker compose' yo'q. Uni o'rnatish $APP_DIR dan tashqariga chiqadi — avval o'zingiz o'rnating (https://docs.docker.com/engine/install/)."

existing() { remote "grep -E '^$1=' '$APP_DIR/.env' 2>/dev/null | head -1 | cut -d= -f2-" || true; }

say "2/6 Port"
EXISTING_PORT="$(existing WEB_PORT)"
if [ -n "$EXISTING_PORT" ]; then
  PORT="$EXISTING_PORT"
  echo "Mavjud o'rnatish porti: $PORT"
else
  BUSY=" $(remote "ss -ltnH | awk '{print \$4}' | sed 's/.*://' | sort -u | tr '\n' ' '") "
  PORT=""
  for p in $PORTS; do
    case "$BUSY" in *" $p "*) ;; *) PORT="$p"; break ;; esac
  done
  [ -n "$PORT" ] || die "Bo'sh port topilmadi ($PORTS). PORTS=\"...\" bilan boshqa port bering"
  echo "Tanlangan bo'sh port: $PORT"
fi

if [ "$SRC" = "git" ]; then
  say "3/6 Kodni $APP_DIR ga ko'chirish (git $(git rev-parse --short HEAD))"
  git diff --quiet HEAD -- || echo "Eslatma: commit qilinmagan o'zgarishlar ko'chirilmaydi (faqat HEAD)."
  git archive --format=tar HEAD | remote_in "mkdir -p '$APP_DIR' && tar -x -C '$APP_DIR' && echo tayyor"
else
  say "3/6 Kodni $APP_DIR ga ko'chirish (papkadan, git yo'q)"
  tar -c --exclude=node_modules --exclude=.venv --exclude=dist --exclude=__pycache__ --exclude=.pytest_cache \
    --exclude=.ruff_cache --exclude=.env --exclude=deploy/secrets.env --exclude=.git . \
    | remote_in "mkdir -p '$APP_DIR' && tar -x -C '$APP_DIR' && echo tayyor"
fi

say "4/6 Sozlamalar (.env)"
HAS_ENV="$(remote "test -f '$APP_DIR/.env' && echo yes || echo no")"
if [ "$HAS_ENV" = "yes" ] && [ "$RECONFIGURE" -eq 0 ]; then
  echo "Mavjud .env saqlanadi (kalitlarni almashtirish: --reconfigure)."
else
  echo "Kalitlar ekranga chiqarilmaydi va faqat serverdagi .env ga yoziladi."
  need ANTHROPIC_API_KEY "ANTHROPIC_API_KEY (Claude)" 1 1
  need BOT_TOKEN "BOT_TOKEN (@BotFather)" 1 1
  need BOT_USERNAME "BOT_USERNAME (@ belgisisiz)" 0 1
  need IG_APP_ID "IG_APP_ID (Instagram, ixtiyoriy — Enter)" 0 0
  IG_APP_SECRET="${IG_APP_SECRET:-}"
  if [ -n "$IG_APP_ID" ]; then need IG_APP_SECRET "IG_APP_SECRET" 1 1; fi
  need AZURE_SPEECH_KEY "AZURE_SPEECH_KEY (ovozli javob, ixtiyoriy — Enter)" 1 0
  AZURE_SPEECH_REGION="${AZURE_SPEECH_REGION:-}"
  if [ -n "$AZURE_SPEECH_KEY" ]; then need AZURE_SPEECH_REGION "AZURE_SPEECH_REGION (masalan westeurope)" 0 1; fi
  for v in PAYME_MERCHANT_ID PAYME_KEY PAYME_CHECKOUT_URL CLICK_SERVICE_ID CLICK_MERCHANT_ID CLICK_SECRET_KEY \
    PUBLIC_URL LLM_MODEL LLM_FALLBACK_MODEL; do
    printf -v "$v" '%s' "${!v:-}"
  done

  # Server tomonidagi maxfiy qiymatlar: mavjud bo'lsa saqlanadi (baza paroli va sessiyalar buzilmasin)
  SECRET_KEY_V="$(existing SECRET_KEY)";               SECRET_KEY_V="${SECRET_KEY_V:-$(rand)$(rand)}"
  POSTGRES_PASSWORD_V="$(existing POSTGRES_PASSWORD)"; POSTGRES_PASSWORD_V="${POSTGRES_PASSWORD_V:-$(rand)}"
  WEBHOOK_SECRET_V="$(existing WEBHOOK_SECRET)";       WEBHOOK_SECRET_V="${WEBHOOK_SECRET_V:-$(rand)}"
  IG_VERIFY_TOKEN_V="$(existing IG_VERIFY_TOKEN)";     IG_VERIFY_TOKEN_V="${IG_VERIFY_TOKEN_V:-$(rand)}"

  BASE_URL="${PUBLIC_URL:-http://$SERVER_IP:$PORT}"
  BASE_URL="${BASE_URL%/}"
  case "$BASE_URL" in https://*) COOKIE_SECURE=true ;; *) COOKIE_SECURE=false ;; esac

  remote_in "umask 077; cat > '$APP_DIR/.env'" <<EOF
# Navbatchi AI — deploy/install_remote.sh yaratgan ($(date -u +%Y-%m-%dT%H:%MZ))
BOT_TOKEN=$BOT_TOKEN
BOT_USERNAME=${BOT_USERNAME#@}
BOT_MODE=polling
PUBLIC_BASE_URL=$BASE_URL
PUBLIC_WEB_URL=$BASE_URL
WEBHOOK_SECRET=$WEBHOOK_SECRET_V
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
LLM_MODEL=${LLM_MODEL:-claude-haiku-4-5}
LLM_FALLBACK_MODEL=${LLM_FALLBACK_MODEL:-claude-sonnet-5}
IG_APP_ID=$IG_APP_ID
IG_APP_SECRET=$IG_APP_SECRET
IG_VERIFY_TOKEN=$IG_VERIFY_TOKEN_V
AZURE_SPEECH_KEY=$AZURE_SPEECH_KEY
AZURE_SPEECH_REGION=$AZURE_SPEECH_REGION
PAYME_MERCHANT_ID=$PAYME_MERCHANT_ID
PAYME_KEY=$PAYME_KEY
PAYME_CHECKOUT_URL=${PAYME_CHECKOUT_URL:-https://checkout.paycom.uz}
CLICK_SERVICE_ID=$CLICK_SERVICE_ID
CLICK_MERCHANT_ID=$CLICK_MERCHANT_ID
CLICK_SECRET_KEY=$CLICK_SECRET_KEY
SECRET_KEY=$SECRET_KEY_V
COOKIE_SECURE=$COOKIE_SECURE
POSTGRES_PASSWORD=$POSTGRES_PASSWORD_V
WEB_PORT=$PORT
EOF
  echo ".env yozildi (chmod 600)."
fi

say "5/6 Ishga tushirish (birinchi marta build bir necha daqiqa oladi)"
remote "APP_DIR='$APP_DIR' bash '$APP_DIR/deploy/server.sh' up"

ADMIN_PHONE="${ADMIN_PHONE:-}"
if [ -z "$ADMIN_PHONE" ] && [ "$HAS_ENV" = "no" ]; then need ADMIN_PHONE "Platforma admini telefon raqami (+998...)" 0 0; fi
if [ -n "$ADMIN_PHONE" ]; then
  say "6/6 Platforma admini: $ADMIN_PHONE"
  # Akkaunt bor bo'lsa paroli o'zgarmaydi — faqat admin qilinadi
  need ADMIN_PASSWORD "Admin uchun parol (kamida 8 belgi)" 1 1
  printf '%s\n' "$ADMIN_PASSWORD" | remote_in "cd '$APP_DIR' && docker compose exec -T api python -m app.cli make-admin '$ADMIN_PHONE' --password-stdin"
else
  say "6/6 Admin — o'tkazib yuborildi (ADMIN_PHONE berilmagan)"
fi

say "Holat"
remote "APP_DIR='$APP_DIR' bash '$APP_DIR/deploy/server.sh' status"
URL="$(existing PUBLIC_WEB_URL)"; URL="${URL:-http://$SERVER_IP:$PORT}"
cat <<EOF

Tayyor!
  Sayt:   $URL/
  Panel:  $URL/app/
  Bot:    Telegram'da botingizga /start yozing
Loglar:   ssh -i $KEY $HOST "APP_DIR=$APP_DIR bash $APP_DIR/deploy/server.sh logs api"
Yangilash: git pull && bash deploy/install_remote.sh
EOF
