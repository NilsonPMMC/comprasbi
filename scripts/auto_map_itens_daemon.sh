#!/usr/bin/env bash
# Mapeamento contínuo ao catálogo: lotes até esvaziar a fila mapeável, pausa, repete.
# Uso manual: ./scripts/auto_map_itens_daemon.sh
# Segundo plano: nohup ./scripts/auto_map_itens_daemon.sh >> logs/auto_map_daemon.log 2>&1 &
#
# Variáveis (opcional):
#   AUTO_MAP_DAEMON_LIMITE      — itens por rodada interna (padrão 250)
#   AUTO_MAP_DAEMON_PAUSA_SEG   — pausa entre rodadas do --continuo (padrão 0.25)
#   AUTO_MAP_DAEMON_MAX_RODADAS — teto de rodadas por ciclo (padrão 400)
#   AUTO_MAP_DAEMON_SLEEP_VAZIO — segundos após um ciclo completo (padrão 180)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "${ROOT}/.venv/bin/activate"
export PYTHONUNBUFFERED=1

mkdir -p "${ROOT}/logs"

LIMITE="${AUTO_MAP_DAEMON_LIMITE:-250}"
PAUSA_SEG="${AUTO_MAP_DAEMON_PAUSA_SEG:-0.25}"
MAX_RODADAS="${AUTO_MAP_DAEMON_MAX_RODADAS:-400}"
SLEEP_VAZIO="${AUTO_MAP_DAEMON_SLEEP_VAZIO:-180}"

echo "[auto_map_daemon] $(date -Iseconds) iniciando (ROOT=$ROOT)"
echo "[auto_map_daemon] limite=$LIMITE pausa_seg=$PAUSA_SEG max_rodadas=$MAX_RODADAS sleep_vazio=${SLEEP_VAZIO}s"

while true; do
  echo "[auto_map_daemon] $(date -Iseconds) ciclo --continuo..."
  if python manage.py auto_map_itens \
    --continuo \
    --limit "$LIMITE" \
    --pausa-segundos "$PAUSA_SEG" \
    --max-rodadas "$MAX_RODADAS"; then
    echo "[auto_map_daemon] $(date -Iseconds) ciclo OK; pausa ${SLEEP_VAZIO}s"
  else
    echo "[auto_map_daemon] $(date -Iseconds) ciclo com erro (ex.: IA indisponível); pausa 60s"
    sleep 60
    continue
  fi
  sleep "$SLEEP_VAZIO"
done
