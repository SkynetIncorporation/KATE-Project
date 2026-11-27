#!/usr/bin/env bash
# Arranca el túnel de Cloudflare hacia el backend local y publica su URL en el Worker
# (clave BACKEND_URL del KV). Al cerrarlo con Ctrl+C borra la clave y el Worker vuelve
# a usar Gemini directo. Uso: scripts/tunel.sh [puerto]   (por omisión 8000)
set -euo pipefail

PUERTO="${1:-8000}"
cd "$(dirname "$0")/../worker"
LOG="$(mktemp)"

cloudflared tunnel --url "http://127.0.0.1:${PUERTO}" >"$LOG" 2>&1 &
CF=$!

limpiar() {
  kill "$CF" 2>/dev/null || true
  npx wrangler kv key delete BACKEND_URL --binding KATE_CONFIG --remote >/dev/null 2>&1 || true
  rm -f "$LOG"
  echo "Túnel cerrado: el chat vuelve a usar Gemini directo."
}
trap limpiar EXIT INT TERM

URL=""
for _ in $(seq 1 30); do
  URL="$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1 || true)"
  [ -n "$URL" ] && break
  sleep 1
done
if [ -z "$URL" ]; then echo "No se obtuvo la URL del túnel:"; cat "$LOG"; exit 1; fi

npx wrangler kv key put BACKEND_URL "$URL" --binding KATE_CONFIG --remote
echo "Túnel activo: $URL"
echo "Worker actualizado (puede tardar hasta ~1 min en propagarse). Ctrl+C para cerrar."
wait "$CF"
