#!/usr/bin/env bash
# Visão rápida das automações do projeto Compras.
# Mostra processos ativos e últimas linhas de logs com foco em erros.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOGDIR="$ROOT/logs"

print_header() {
  echo ""
  echo "=================================================="
  echo "$1"
  echo "=================================================="
}

show_log_tail() {
  local file="$1"
  local lines="${2:-25}"
  if [[ -f "$file" ]]; then
    echo "-- ${file#$ROOT/} (últimas $lines linhas)"
    tail -n "$lines" "$file"
  else
    echo "-- ${file#$ROOT/} (arquivo inexistente)"
  fi
}

print_header "STATUS AUTOMACOES COMPRAS ($(date -Iseconds))"

print_header "PROCESSOS ATIVOS"
ps -eo pid,etime,%cpu,%mem,cmd \
  | awk '
    /manage.py sync_pncp/ ||
    /manage.py auto_map_itens/ ||
    /auto_map_itens_daemon.sh/ ||
    /cron_diario_pncp_ia.sh/ ||
    /cron_backfill_pncp_ia.sh/ {
      if ($0 !~ /status_automacoes.sh/ && $0 !~ /awk /) print
    }
  '

print_header "CHECKPOINTS (BANCO)"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  "$ROOT/.venv/bin/python" manage.py shell -c "
from dashboard.models import SyncCheckpoint
qs = SyncCheckpoint.objects.order_by('-ano', 'orgao_cnpj')[:12]
print('ano | cnpj | ultimo_sequencial_completo | updated_at')
for c in qs:
    print(f'{c.ano} | {c.orgao_cnpj} | {c.ultimo_sequencial_completo} | {c.updated_at}')
" 2>/dev/null || echo "Falha ao consultar SyncCheckpoint."
else
  echo "Ambiente virtual não encontrado em .venv."
fi

print_header "ULTIMOS LOGS"
show_log_tail "$LOGDIR/sync_pncp_2024_live.log" 20
echo ""
show_log_tail "$LOGDIR/auto_map_daemon.log" 20
echo ""
show_log_tail "$LOGDIR/cron_diario_pncp.log" 20
echo ""
show_log_tail "$LOGDIR/cron_backfill_pncp.log" 20

print_header "ULTIMAS LINHAS COM INDICATIVOS DE ERRO"
for f in \
  "$LOGDIR/sync_pncp_2024_live.log" \
  "$LOGDIR/auto_map_daemon.log" \
  "$LOGDIR/cron_diario_pncp.log" \
  "$LOGDIR/cron_backfill_pncp.log"; do
  if [[ -f "$f" ]]; then
    echo "-- ${f#$ROOT/}"
    grep -E -i "(^|[^[:alpha:]])(erro|error|exception|traceback|timeout|falha|failed|syntax error)($|[^[:alpha:]])" "$f" | tail -n 10 || echo "(sem ocorrencias recentes)"
    echo ""
  fi
done

print_header "FIM"
