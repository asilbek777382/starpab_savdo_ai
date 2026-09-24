#!/usr/bin/env bash
# Navbatchi AI'ni serverga o'rnatish / yangilash — O'Z KOMPYUTERINGIZDAN ishga tushiring (repo ildizida):
#
#   bash deploy/install_remote.sh
#
# Hamma ish serverdagi $APP_DIR ichida bajariladi: tizim paketlari, /etc, boshqa konteynerlar va nginx'ga
# tegilmaydi. Kalitlar shu yerda yashirin so'raladi va to'g'ridan-to'g'ri server .env fayliga (chmod 600) yoziladi.
#
# Sozlash (ixtiyoriy):
#   HOST=root@1.2.3.4  KEY=~/.ssh/boshqa_kalit  APP_DIR=/home/online_savdo  bash deploy/install_remote.sh
#   bash deploy/install_remote.sh --reconfigure   # .env ni qayta yaratish (kalitlarni almashtirish)
set -euo pipefail

HOST="${HOST:-root@204.168.131.237}"
KEY="${KEY:-$HOME/.ssh/aslsmm_deploy}"
APP_DIR="${APP_DIR:-/home/online_savdo}"
PORTS="${PORTS:-8090 8091 8092 8093 8094 8095 8096 8097 8098 8099}"
RECONFIGURE=0
[ "${1:-}" = "--reconfigure" ] && RECONFIGURE=1

# Testlar uchun: SSH_CMD="bash -c" bilan lokal "server"
# remote    — stdin ishlatmaydi (klaviatura kiritmasini "yutib" yubormasligi uchun /dev/null)
# remote_in — stdin serverga uzatiladi (fayl, .env, parol)
if [ -n "${SSH_CMD:-}" ]; then
  remote_in() { ${SSH_CMD} "$1"; }
  SERVER_IP="${SERVER_IP:-127.0.0.1}"
else
  remote_in() { ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$HOST" "$1"; }
  SERVER_IP="${SERVER_IP:-${HOST#*@}}"
fi
remote() { remote_in "$1" </dev/null; }

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mXATO: %s\033[0m\n' "$*" >&2; exit 1; }
rand() { openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
ask() { local v; read -r -p "$1: " v; printf '%s' "$v"; }
ask_secret() { local v; read -r -s -p "$1: " v; echo >&2; printf '%s' "$v"; }

[ -f docker-compose.yml ] && [ -f deploy/server.sh ] || die "Skriptni repo ildizida ishga tushiring (docker-compose.yml bor papkada)"
command -v git >/dev/null || die "git kerak"

say "1/6 Server tekshiruvi (hech narsa o'zgartirilmaydi)"
remote_in "APP_DIR='$APP_DIR' bash -s -- preflight" < deploy/server.sh
remote "command -v docker >/dev/null && docker compose version >/dev/null 2>&1" || die \
  "Serverda Docker yoki 'docker compose' yo'q. Uni o'rnatish $APP_DIR dan tashqariga chiqadi — avval o'zingiz o'rnating (https://docs.docker.com/engine/install/)."

say "2/6 Port"
EXISTING_PORT="$(remote "grep -E '^WEB_PORT=' '$APP_DIR/.env' 2>/dev/null | cut -d= -f2" || true)"
if [ -n "$EXISTING_PORT" ] && [ "$RECONFIGURE" -eq 0 ]; then
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

say "3/6 Kodni $APP_DIR ga ko'chirish ($(git rev-parse --short HEAD))"
git diff --quiet HEAD -- || echo "Eslatma: commit qilinmagan o'zgarishlar ko'chirilmaydi (faqat HEAD)."
git archive --format=tar HEAD | remote_in "mkdir -p '$APP_DIR' && tar -x -C '$APP_DIR' && echo tayyor"

say "4/6 Sozlamalar (.env)"
HAS_ENV="$(remote "test -f '$APP_DIR/.env' && echo yes || echo no")"
if [ "$HAS_ENV" = "yes" ] && [ "$RECONFIGURE" -eq 0 ]; then
  echo "Mavjud .env saqlanadi (kalitlarni almashtirish: --reconfigure)."
  ADMIN_PHONE=""
else
  echo "Kalitlar ekranda ko'rinmaydi va faqat serverdagi .env ga yoziladi."
  ANTHROPIC_API_KEY="$(ask_secret 'ANTHROPIC_API_KEY (Claude)')"
  BOT_TOKEN="$(ask_secret 'BOT_TOKEN (@BotFather)')"
  BOT_USERNAME="$(ask 'BOT_USERNAME (@ belgisisiz)')"
  ADMIN_PHONE="$(ask 'Platforma admini telefon raqami (+998...)')"
  echo "Instagram (ixtiyoriy, HTTPS domen kerak — hozir bo'sh qoldirsa bo'ladi):"
  IG_APP_ID="$(ask '  IG_APP_ID (Enter — o'"'"'tkazib yuborish)')"
  IG_APP_SECRET=""
  [ -n "$IG_APP_ID" ] && IG_APP_SECRET="$(ask_secret '  IG_APP_SECRET')"
  echo "Ovozli javoblar — Azure Speech (ixtiyoriy):"
  AZURE_SPEECH_KEY="$(ask_secret '  AZURE_SPEECH_KEY (Enter — o'"'"'tkazib yuborish)')"
  AZURE_SPEECH_REGION=""
  [ -n "$AZURE_SPEECH_KEY" ] && AZURE_SPEECH_REGION="$(ask '  AZURE_SPEECH_REGION (masalan westeurope)')"
  [ -n "$ANTHROPIC_API_KEY" ] && [ -n "$BOT_TOKEN" ] && [ -n "$BOT_USERNAME" ] || die "ANTHROPIC_API_KEY, BOT_TOKEN, BOT_USERNAME majburiy"
  remote_in "umask 077; cat > '$APP_DIR/.env'" <<EOF
# Navbatchi AI — deploy/install_remote.sh yaratgan ($(date -u +%Y-%m-%dT%H:%MZ))
BOT_TOKEN=$BOT_TOKEN
BOT_USERNAME=${BOT_USERNAME#@}
BOT_MODE=polling
PUBLIC_BASE_URL=http://$SERVER_IP:$PORT
WEBHOOK_SECRET=$(rand)
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
LLM_MODEL=claude-haiku-4-5
LLM_FALLBACK_MODEL=claude-sonnet-5
IG_APP_ID=$IG_APP_ID
IG_APP_SECRET=$IG_APP_SECRET
IG_VERIFY_TOKEN=$(rand)
AZURE_SPEECH_KEY=$AZURE_SPEECH_KEY
AZURE_SPEECH_REGION=$AZURE_SPEECH_REGION
SECRET_KEY=$(rand)$(rand)
COOKIE_SECURE=false
POSTGRES_PASSWORD=$(rand)
WEB_PORT=$PORT
EOF
  echo ".env yozildi (chmod 600)."
fi

say "5/6 Ishga tushirish (birinchi marta build bir necha daqiqa oladi)"
remote "APP_DIR='$APP_DIR' bash '$APP_DIR/deploy/server.sh' up"

if [ -n "${ADMIN_PHONE:-}" ]; then
  say "6/6 Platforma admini: $ADMIN_PHONE"
  ADMIN_PASSWORD="$(ask_secret 'Admin uchun parol (kamida 8 belgi)')"
  printf '%s\n' "$ADMIN_PASSWORD" | remote_in "cd '$APP_DIR' && docker compose exec -T api python -m app.cli make-admin '$ADMIN_PHONE' --password-stdin"
else
  say "6/6 Admin — o'tkazib yuborildi (mavjud o'rnatish)"
fi

say "Holat"
remote "APP_DIR='$APP_DIR' bash '$APP_DIR/deploy/server.sh' status"
cat <<EOF

Tayyor!
  Sayt:   http://$SERVER_IP:$PORT/
  Panel:  http://$SERVER_IP:$PORT/app/
  Bot:    Telegram'da botingizga /start yozing
Loglar:   ssh -i $KEY $HOST "APP_DIR=$APP_DIR bash $APP_DIR/deploy/server.sh logs api"
Yangilash: git pull && bash deploy/install_remote.sh
EOF
