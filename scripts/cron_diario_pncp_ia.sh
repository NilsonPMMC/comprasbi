#!/usr/bin/env bash
# Rotina diária: re-sincroniza o ano corrente (idempotente) e mapeia novos itens.
# Crontab exemplo (root ou usuário do app, ajuste paths):
#   15 2 * * * /var/www/compras/scripts/cron_diario_pncp_ia.sh >> /var/www/compras/logs/cron_diario.log 2>&1

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "${ROOT}/.venv/bin/activate"

LOCK_FILE="/tmp/compras_pncp_diario.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[cron] $(date -Iseconds) execução já em andamento; saindo."
  exit 0
fi

ANO="$(date +%Y)"
FIM="${PNCP_CRON_SEQUENCIAL_FIM:-8000}"
LIMITE_MAP="${AUTO_MAP_CRON_LIMITE:-300}"

export PYTHONUNBUFFERED=1

echo "[cron] $(date -Iseconds) sync_pncp ano=$ANO 1..$FIM --resume"
python manage.py sync_pncp --ano "$ANO" --inicio 1 --fim "$FIM" --resume

if [[ -f "${ROOT}/logs/auto_map_daemon.pid" ]] && kill -0 "$(cat "${ROOT}/logs/auto_map_daemon.pid")" 2>/dev/null; then
  echo "[cron] $(date -Iseconds) auto_map_itens pulado (daemon contínuo ativo)."
else
  echo "[cron] $(date -Iseconds) auto_map_itens --continuo --limit $LIMITE_MAP"
  python manage.py auto_map_itens --continuo --limit "$LIMITE_MAP" --max-rodadas 80 --pausa-segundos 0.2 \
    || echo "[cron] auto_map_itens encerrou com erro (verificar IA)."
fi

echo "[cron] $(date -Iseconds) ok"
