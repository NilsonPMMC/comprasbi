#!/usr/bin/env bash
# Backfill noturno: reprocessa anos anteriores com --resume e roda mapeamento.
# Pode ser chamado via cron com flock para evitar concorrência.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "${ROOT}/.venv/bin/activate"

LOCK_FILE="/tmp/compras_pncp_backfill.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[backfill] $(date -Iseconds) execução já em andamento; saindo."
  exit 0
fi

ANO_ATUAL="$(date +%Y)"
ANO_1="$((ANO_ATUAL - 1))"
ANO_2="$((ANO_ATUAL - 2))"
ANOS="${PNCP_BACKFILL_ANOS:-$ANO_1 $ANO_2}"
FIM="${PNCP_BACKFILL_SEQUENCIAL_FIM:-12000}"
LIMITE_MAP="${AUTO_MAP_BACKFILL_LIMITE:-250}"
RODADAS_MAP="${AUTO_MAP_BACKFILL_RODADAS:-60}"

export PYTHONUNBUFFERED=1

echo "[backfill] $(date -Iseconds) anos=[$ANOS] faixa=1..$FIM"
for ANO in $ANOS; do
  echo "[backfill] $(date -Iseconds) sync_pncp ano=$ANO 1..$FIM --resume"
  python manage.py sync_pncp --ano "$ANO" --inicio 1 --fim "$FIM" --resume
done

if [[ -f "${ROOT}/logs/auto_map_daemon.pid" ]] && kill -0 "$(cat "${ROOT}/logs/auto_map_daemon.pid")" 2>/dev/null; then
  echo "[backfill] $(date -Iseconds) auto_map_itens pulado (daemon contínuo ativo)."
else
  echo "[backfill] $(date -Iseconds) auto_map_itens --continuo --limit $LIMITE_MAP --max-rodadas $RODADAS_MAP"
  python manage.py auto_map_itens --continuo --limit "$LIMITE_MAP" --max-rodadas "$RODADAS_MAP" --pausa-segundos 0.2 \
    || echo "[backfill] auto_map_itens encerrou com erro (verificar IA)."
fi

echo "[backfill] $(date -Iseconds) ok"
