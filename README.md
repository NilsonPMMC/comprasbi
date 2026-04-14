# Compras públicas — Prefeitura de Mogi das Cruzes

Plataforma de inteligência de compras com backend **Django + Ninja + PostgreSQL + pgvector** e frontend **Vue 3 + Vite + Tailwind**. O sistema integra dados do PNCP, mapeia itens por catálogo master (com apoio de IA) e oferece painéis analíticos com exportação CSV/PDF.

## Visão geral

| Camada | Tecnologias |
|--------|-------------|
| API | Django, Django Ninja, PostgreSQL, pgvector, Gunicorn |
| Web | Vue 3, Vite, Tailwind CSS, ApexCharts, jsPDF + autotable |
| Dados | PNCP (compras/itens), checkpoint de sync, catálogo master |

## Funcionalidades do painel

### Painel Produto Master
- Busca de produto no catálogo, filtros por período, indicadores de menor/maior preço e gráfico.
- **Modos de análise no gráfico**:
  - `Identificação semântica (consolidado)` — série completa do grupo semântico do produto master.
  - `ID exata (uma linha por compra/processo)` — histórico deduplicado por `ano/sequencial`.
- Bloco informativo: **Grupo semântico identificado** (ID, nome, total de registros e processos correlatos).

### Painel Compras
- Seleção de ano e compra com **busca no select** (número/data/objeto).
- Tabela de itens com estimado/homologado/variação e evolução.
- **Modos de análise no gráfico do item**:
  - `Identificação semântica (produto master)` — série consolidada do grupo semântico vinculado.
  - `ID exata (uma linha por compra/processo)` — mesma base histórica deduplicada por processo (sem duplicar compra).
- Bloco informativo: **Grupo semântico identificado** com itens relacionados da compra e processos correlatos.
- Exportação de relatórios da compra em **CSV e PDF** (colunas alinhadas à matriz: maior/menor/último preço + processo/data).

### Matriz de Itens
- Busca semântica de itens do catálogo, seleção múltipla e exportação CSV/PDF.
- Tabela com **altura limitada + scroll** e cabeçalho fixo (`sticky`).
- **Modos de análise no gráfico**:
  - `Identificação semântica (consolidado)`.
  - `ID exata (uma linha por compra/processo)`.
- Bloco informativo: **Grupo semântico identificado** com processos correlatos.

## Requisitos

- Python 3.10+
- Node.js 18+
- PostgreSQL com extensão `vector` (`CREATE EXTENSION IF NOT EXISTS vector;`)
- Serviço de embeddings (opcional, para `auto_map_itens`): `AI_SERVICE_URL`

## Setup local

```bash
cd /var/www/compras
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
```

Frontend:

```bash
cd /var/www/compras/frontend
npm install
```

## Desenvolvimento

API (Django):

```bash
cd /var/www/compras
source .venv/bin/activate
python manage.py runserver 0.0.0.0:8001
```

- Docs: `http://127.0.0.1:8001/api/docs`
- Health: `http://127.0.0.1:8001/api/health`

Frontend:

```bash
cd /var/www/compras/frontend
npm run dev
```

Build frontend:

```bash
cd /var/www/compras/frontend
npm run build
```

## Homologação (servidor)

Subdomínio homologado: `comprasbi.mogidascruzes.sp.gov.br`

### Portas e fluxo
- Apache VirtualHost: **porta 80** (`/etc/apache2/sites-available/comprasbi.conf`).
- Gunicorn: **127.0.0.1:8001** (não exposto externamente).
- Proxy Apache:
  - `/api/` -> `http://127.0.0.1:8001/api/`
  - `/admin/` -> `http://127.0.0.1:8001/admin/`
- Frontend SPA servido por `DocumentRoot /var/www/compras/frontend/dist`.
- Estáticos Django (`/static/`) via `Alias /var/www/compras/staticfiles/`.

> Importante: não rode `runserver` na porta 8001 quando o `gunicorn-compras` estiver ativo.

### Arquivos de deploy no repositório
- `deploy/apache-comprasbi.conf`
- `deploy/gunicorn.comprasbi.py`
- `deploy/gunicorn-compras.service.example`
- `deploy/install-comprasbi-server.sh`

### Instalação rápida (recomendada)

```bash
sudo bash /var/www/compras/deploy/install-comprasbi-server.sh
```

Esse script:
- valida Gunicorn e build do frontend (`dist/branding`);
- roda `collectstatic`;
- instala/atualiza vhost Apache e service do Gunicorn;
- habilita módulos Apache necessários (`proxy`, `proxy_http`, `headers`, `rewrite`);
- faz `configtest`, reload do Apache e restart do serviço `gunicorn-compras`.

### Instalação manual (referência)

```bash
# Apache
sudo cp /var/www/compras/deploy/apache-comprasbi.conf /etc/apache2/sites-available/comprasbi.conf
sudo a2enmod proxy proxy_http headers rewrite
sudo a2ensite comprasbi.conf
sudo apache2ctl configtest && sudo systemctl reload apache2

# Gunicorn (systemd)
sudo cp /var/www/compras/deploy/gunicorn-compras.service.example /etc/systemd/system/gunicorn-compras.service
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn-compras
sudo systemctl status gunicorn-compras
```

### Variáveis de ambiente para homologação
Use `.env.example` como base. Pontos críticos:

- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=comprasbi.mogidascruzes.sp.gov.br,...`
- `DJANGO_USE_TLS=true`
- `DJANGO_SECURE_SSL_REDIRECT=false`
- `DJANGO_USE_X_FORWARDED_HOST=false`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://comprasbi.mogidascruzes.sp.gov.br`
- `CORS_ALLOWED_ORIGINS=https://comprasbi.mogidascruzes.sp.gov.br`
- `POSTGRES_*` corretos do ambiente
- `AI_SERVICE_URL` (quando usar mapeamento por IA)

Opcional frontend:
- `VITE_API_BASE_URL=https://comprasbi.mogidascruzes.sp.gov.br/api`

## Comandos de dados (management)

### Sync PNCP
```bash
cd /var/www/compras
source .venv/bin/activate
python manage.py sync_pncp --ano 2024 --inicio 1 --fim 12000
```

Opções úteis: `--resume`, `--reset-checkpoint`.

### Mapeamento semântico de itens
```bash
python manage.py auto_map_itens --limit 100
```

## Endpoints principais

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/api/health` | Saúde do serviço |
| GET | `/api/compras/{ano}` | Compras em cache (paginação). Query params: `numero_compra`, `modalidade_id`, `ordenar_por` (`sequencial`/`numero_compra`) e `ordem` (`asc`/`desc`) |
| GET | `/api/compras/{ano}/{sequencial}/itens` | Itens da compra |
| GET | `/api/catalogo` | Catálogo master |
| GET | `/api/catalogo/matriz` | Matriz consolidada (maior/menor/último) |
| GET | `/api/catalogo/{id}/historico-precos` | Histórico de preços homologados |
| POST | `/api/catalogo` | Cria item no catálogo master |
| POST | `/api/itens/{item_id}/vincular` | Vincula item ao catálogo |

## Endpoints externos do PNCP utilizados

Os comandos de sincronização (`sync_pncp`) e o cliente PNCP usam estes endpoints oficiais:

| Método | Endpoint PNCP | Uso no projeto |
|--------|----------------|----------------|
| GET | `https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}` | Consulta da compra por varredura sequencial (`sync_pncp`) |
| GET | `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens?pagina={n}&tamanhoPagina={m}` | Paginação dos itens da compra (`sync_pncp`) |
| GET | `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/{numero_item}/resultados?pagina=1&tamanhoPagina=10` | Resultado/homologação do item (`sync_pncp`) |
| GET | `https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao?cnpjOrgao={cnpj}&dataInicial={yyyymmdd}&dataFinal={yyyymmdd}&pagina={n}&tamanhoPagina={m}&codigoModalidadeContratacao={modalidade}` | Listagem anual pública por modalidade (`dashboard/services/pncp_client.py`) |

Observação: o CNPJ padrão do órgão é configurável via `PNCP_CNPJ_ORGAO` (padrão: `46523270000188`).
Observação 2: o campo `numeroCompra` retornado no endpoint de detalhe da compra (`/consulta/v1/orgaos/.../compras/{ano}/{sequencial}`) agora é persistido em `Compra.numero_compra` e exposto no endpoint interno `GET /api/compras/{ano}` para cruzamento ERP ↔ PNCP (ex.: compra `2025/663` → pregão `179`).
Observação 3: os relatórios CSV/PDF do Painel Compras passam a carregar também o contexto aplicado na tela (Número Compra da compra, filtro por Número Compra e ordenação da lista de compras).
Observação 4: os relatórios CSV/PDF de Painel Compras e Matriz de Itens permitem escolher o modo de análise (`Identificação semântica` ou `ID exata`) para manter consistência com os gráficos.
Observação 5: o Painel Compras recebeu fluxo de filtros em duas linhas: (1) Ano + Número Compra + Modalidade (opcional) + Ordenação + botões Aplicar/Limpar; (2) campo Compra com busca textual e select filtrado.

## Estrutura

- `core/` — settings/urls/wsgi
- `dashboard/` — modelos, API e comandos
- `frontend/` — SPA Vue (`src/components/Dashboard.vue`)
- `deploy/` — Gunicorn, Apache e script de instalação de homologação
- `scripts/` — automação de sincronização
- `logs/` — logs de runtime e jobs

## Roadmap (pontos não bloqueantes)

- Otimizar bundle do frontend para reduzir chunks grandes (>500 kB) apontados no build.
- O warning atual não bloqueia homologação (build está passando), então essa otimização fica para ciclo posterior de performance.
