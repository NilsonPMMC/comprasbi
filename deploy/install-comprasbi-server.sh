#!/usr/bin/env bash
# Instala virtual host Apache (comprasbi) e serviço systemd (Gunicorn).
# Execute no servidor: sudo bash /var/www/compras/deploy/install-comprasbi-server.sh
#
set -euo pipefail

ROOT="/var/www/compras"
APACHE_SITE="comprasbi.conf"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Execute como root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -x "${ROOT}/.venv/bin/gunicorn" ]]; then
  echo "Gunicorn não encontrado em ${ROOT}/.venv — rode: pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -d "${ROOT}/frontend/dist" ]]; then
  echo "Build do frontend ausente — rode: cd ${ROOT}/frontend && npm ci && npm run build" >&2
  exit 1
fi
if [[ ! -d "${ROOT}/frontend/dist/branding" ]] || [[ -z "$(ls -A "${ROOT}/frontend/dist/branding" 2>/dev/null)" ]]; then
  echo "dist sem public/branding — rode: cd ${ROOT}/frontend && npm run build" >&2
  exit 1
fi

mkdir -p "${ROOT}/logs"
chown www-data:www-data "${ROOT}/logs" 2>/dev/null || true

# Estáticos Django (admin)
if [[ -f "${ROOT}/manage.py" ]]; then
  "${ROOT}/.venv/bin/python" "${ROOT}/manage.py" collectstatic --noinput || true
fi

cp "${ROOT}/deploy/apache-comprasbi.conf" "/etc/apache2/sites-available/${APACHE_SITE}"

a2enmod proxy proxy_http headers rewrite
a2ensite "${APACHE_SITE}"

apache2ctl configtest
systemctl reload apache2

# Gunicorn (systemd)
cp "${ROOT}/deploy/gunicorn-compras.service.example" /etc/systemd/system/gunicorn-compras.service
systemctl daemon-reload
systemctl enable gunicorn-compras
systemctl restart gunicorn-compras
systemctl --no-pager status gunicorn-compras || true

echo "Concluído. Apache: site ${APACHE_SITE} (*:80, padrão protocolo-sei) | Gunicorn: 127.0.0.1:8001"
