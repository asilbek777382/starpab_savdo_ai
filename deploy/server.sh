#!/usr/bin/env bash
# Navbatchi AI — serverda ishlatiladigan skript. Faqat $APP_DIR ichida ishlaydi:
# tizim paketlariga, /etc ga, boshqa konteynerlar va nginx'ga tegmaydi.
#
#   bash server.sh preflight   # faqat tekshiradi, hech narsani o'zgartirmaydi
#   bash server.sh up          # $APP_DIR/.env bilan ishga tushiradi / yangilaydi
#   bash server.sh status      # konteynerlar holati va health
#   bash server.sh logs [svc]  # oxirgi loglar
set -euo pipefail

APP_DIR="${APP_DIR:-/home/online_savdo}"

compose() {
  local profile=()
  if grep -q '^BOT_MODE=polling' "$APP_DIR/.env" 2>/dev/null; then profile=(--profile polling); fi
  docker compose --project-directory "$APP_DIR" -f "$APP_DIR/docker-compose.yml" "${profile[@]}" "$@"
}

web_port() { grep -E '^WEB_PORT=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d ' ' || true; }

case "${1:-}" in
  preflight)
    echo "== tizim";   uname -srm; . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"
    echo "== docker";  docker --version 2>&1 || echo "DOCKER YO'Q"
    docker compose version 2>&1 || echo "DOCKER COMPOSE YO'Q"
    echo "== band portlar"; ss -ltnH 2>/dev/null | awk '{print $4}' | sed 's/.*://' | sort -n | uniq | tr '\n' ' '; echo
    echo "== ishlayotgan konteynerlar"; docker ps --format '{{.Names}}  {{.Ports}}' 2>/dev/null || true
    echo "== disk";    df -h /home | tail -1
    echo "== xotira";  free -m | awk 'NR==2{print $2" MB jami, "$7" MB bo'\''sh"}'
    echo "== papka";   ls -la "$APP_DIR" 2>/dev/null | head -5 || echo "$APP_DIR hali yo'q"
    ;;
  up)
    test -f "$APP_DIR/.env" || { echo "$APP_DIR/.env yo'q"; exit 1; }
    chmod 600 "$APP_DIR/.env"
    compose up -d --build --remove-orphans
    compose ps
    ;;
  status)
    compose ps
    port="$(web_port)"; port="${port:-80}"
    echo "health: $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/health") (port $port)"
    ;;
  logs)
    shift; compose logs --tail=80 "$@"
    ;;
  *)
    echo "ishlatish: $0 preflight|up|status|logs [servis]"; exit 1
    ;;
esac
