# Gunicorn — comprasbi.mogidascruzes.sp.gov.br
# Escuta em 127.0.0.1:8001 (Apache faz proxy reverso para /api/).
# Não use runserver na mesma porta enquanto este serviço estiver ativo.
#
# Uso manual: cd /var/www/compras && source .venv/bin/activate && gunicorn -c deploy/gunicorn.comprasbi.py core.wsgi:application
#
import multiprocessing
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_logs = _root / "logs"
_logs.mkdir(parents=True, exist_ok=True)

bind = "127.0.0.1:8001"
workers = min(multiprocessing.cpu_count() * 2 + 1, 8)
worker_class = "sync"
timeout = 120
graceful_timeout = 30
keepalive = 5
chdir = str(_root)

accesslog = str(_logs / "gunicorn_access.log")
errorlog = str(_logs / "gunicorn_error.log")
capture_output = True
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
