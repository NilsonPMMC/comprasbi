#!/usr/bin/env bash
# Sincronização PNCP (2024–2026) + auto_map_itens em lote.
# Uso: ./scripts/run_sync_massivo.sh
# Opcional: PNCP_SEQUENCIAL_FIM=12000 ./scripts/run_sync_massivo.sh
# Opcional: AUTO_MAP_RODADAS=30 AUTO_MAP_LIMITE=500 ./scripts/run_sync_massivo.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "${ROOT}/.venv/bin/activate"
export PYTHONUNBUFFERED=1

LOCK_FILE="/tmp/compras_pncp_massivo.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[massivo] Já existe uma execução massiva em andamento; saindo."
  exit 0
fi

LOGDIR="${ROOT}/logs"
mkdir -p "$LOGDIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOGDIR}/massivo_${STAMP}.log"

FIM="${PNCP_SEQUENCIAL_FIM:-12000}"
AUTO_MAP_LIMITE="${AUTO_MAP_LIMITE:-500}"
AUTO_MAP_RODADAS="${AUTO_MAP_RODADAS:-200}"
ANOS="${PNCP_MASSIVO_ANOS:-2024 2025 2026}"

exec > >(tee -a "$LOG") 2>&1

echo "=========================================="
echo "[massivo] Início: $(date -Iseconds)"
echo "[massivo] Log: $LOG"
echo "[massivo] PNCP faixa sequencial: 1..$FIM (ajuste PNCP_SEQUENCIAL_FIM se necessário)"
echo "=========================================="

for ANO in $ANOS; do
  echo ""
  echo ">>> sync_pncp --ano $ANO --inicio 1 --fim $FIM --resume"
  python manage.py sync_pncp --ano "$ANO" --inicio 1 --fim "$FIM" --resume
done

echo ""
echo ">>> auto_map_itens (até não haver pendentes ou atingir $AUTO_MAP_RODADAS rodadas de $AUTO_MAP_LIMITE itens)"

pendentes() {
  # Só órfãos com descrição utilizável (igual ao auto_map_itens)
  python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
from django.db.models import CharField, Value
from django.db.models.functions import Coalesce, Trim
from dashboard.models import ItemCompra
qs = (
    ItemCompra.objects.filter(produto_master__isnull=True)
    .annotate(
        _d=Coalesce(
            Trim('descricao'),
            Value('', output_field=CharField()),
            output_field=CharField(),
        )
    )
    .exclude(_d='')
)
print(qs.count())
"
}

for ((i = 1; i <= AUTO_MAP_RODADAS; i++)); do
  N="$(pendentes || echo 0)"
  echo "[massivo] Rodada $i — itens órfãos pendentes: $N"
  if [[ "$N" == "0" ]]; then
    echo "[massivo] Nenhum item pendente de mapeamento."
    break
  fi
  if ! python manage.py auto_map_itens --limit "$AUTO_MAP_LIMITE"; then
    echo "[massivo] AVISO: auto_map_itens falhou (ex.: IA indisponível). Interrompendo lote de mapeamento."
    break
  fi
done

echo ""
echo "=========================================="
echo "[massivo] Fim: $(date -Iseconds)"
echo "=========================================="
