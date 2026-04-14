from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import IntegrityError
from django.db.models import OuterRef, Q, Subquery
from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from dashboard.models import Compra, ItemCompra, ProdutoCatalogo

logger = logging.getLogger(__name__)


class HealthResponse(Schema):
    status: str


class CompraOut(Schema):
    pncp_id: str
    orgao_cnpj: str
    ano: int
    sequencial: int
    numero_compra: str
    modalidade_id: int
    modalidade_nome: str
    data_publicacao: str | None
    objeto: str
    valor_total_estimado: str | None


class CompraListResponse(Schema):
    ano: int
    pagina: int
    tamanhoPagina: int
    totalRegistros: int
    data: list[CompraOut]


class ItemCompraOut(Schema):
    compra_pncp_id: str
    compra_ano: int
    compra_sequencial: int
    numero_item: int
    descricao: str
    valor_unitario_estimado: str | None
    valor_total: str | None
    valor_unitario_homologado: str | None
    cnpj_vencedor: str
    nome_vencedor: str
    marca_vencedor: str
    produto_master_id: int | None


class ItemCompraListResponse(Schema):
    ano: int
    sequencial: int
    pagina: int
    tamanhoPagina: int
    totalRegistros: int
    data: list[ItemCompraOut]


class ProdutoCatalogoOut(Schema):
    id: int
    nome_padrao: str
    categoria: str | None
    data_criacao: str


class ProdutoCatalogoCreateIn(Schema):
    nome_padrao: str
    categoria: str | None = None


class VincularCatalogoIn(Schema):
    catalogo_id: int


class VinculoResponse(Schema):
    item_id: int
    catalogo_id: int
    catalogo_nome: str
    status: str


class HistoricoPrecoOut(Schema):
    ano: int
    sequencial: int
    valor_estimado: str | None
    valor_homologado: str
    fornecedor_vencedor: str
    data_publicacao: str | None


class MatrizItemOut(Schema):
    catalogo_id: int
    descricao: str
    maior_valor: str | None
    maior_ano: int | None
    maior_sequencial: int | None
    maior_data_publicacao: str | None
    menor_valor: str | None
    menor_ano: int | None
    menor_sequencial: int | None
    menor_data_publicacao: str | None
    ultimo_valor: str | None
    ultimo_ano: int | None
    ultimo_sequencial: int | None
    ultimo_data_publicacao: str | None


class MatrizItemListResponse(Schema):
    pagina: int
    tamanhoPagina: int
    totalRegistros: int
    data: list[MatrizItemOut]


api = NinjaAPI(
    title="Compras públicas — API",
    version="1.0.0",
    description="Motor de dados para o painel de Business Intelligence.",
)


@api.get("/health", response=HealthResponse, tags=["system"])
def health(request: HttpRequest) -> HealthResponse:
    """Verificação de disponibilidade da API."""
    return HealthResponse(status="ok")


def _decimal_to_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


@api.get("/compras/{ano}", response=CompraListResponse, tags=["pncp"])
def compras_por_ano(
    request: HttpRequest,
    ano: int,
    pagina: int = 1,
    tamanho_pagina: int = 50,
    numero_compra: str = "",
    modalidade_id: int | None = None,
    ordenar_por: str = "sequencial",
    ordem: str = "asc",
) -> CompraListResponse:
    """Retorna compras do cache local (tabela Compra)."""
    pagina_efetiva = max(1, pagina)
    tamanho_efetivo = max(1, min(tamanho_pagina, 200))
    inicio = (pagina_efetiva - 1) * tamanho_efetivo
    fim = inicio + tamanho_efetivo

    queryset = Compra.objects.filter(ano=ano)
    numero_compra_limpo = numero_compra.strip()
    if numero_compra_limpo:
        queryset = queryset.filter(numero_compra__icontains=numero_compra_limpo)
    if modalidade_id is not None:
        queryset = queryset.filter(modalidade_id=modalidade_id)

    campo_ordenacao = "sequencial"
    if ordenar_por == "numero_compra":
        campo_ordenacao = "numero_compra"
    ordem_desc = ordem.lower() == "desc"
    if ordem_desc:
        campo_ordenacao = f"-{campo_ordenacao}"
    queryset = queryset.order_by(campo_ordenacao, "sequencial")
    total = queryset.count()
    registros = [
        CompraOut(
            pncp_id=compra.pncp_id,
            orgao_cnpj=compra.orgao_cnpj,
            ano=compra.ano,
            sequencial=compra.sequencial,
            numero_compra=compra.numero_compra or "",
            modalidade_id=compra.modalidade_id,
            modalidade_nome=compra.modalidade_nome,
            data_publicacao=compra.data_publicacao.isoformat() if compra.data_publicacao else None,
            objeto=compra.objeto,
            valor_total_estimado=_decimal_to_str(compra.valor_total_estimado),
        )
        for compra in queryset[inicio:fim]
    ]

    return CompraListResponse(
        ano=ano,
        pagina=pagina_efetiva,
        tamanhoPagina=tamanho_efetivo,
        totalRegistros=total,
        data=registros,
    )


@api.get("/compras/{ano}/{sequencial}/itens", response=ItemCompraListResponse, tags=["pncp"])
def itens_compra(
    request: HttpRequest,
    ano: int,
    sequencial: int,
    pagina: int = 1,
    tamanho_pagina: int = 100,
) -> ItemCompraListResponse:
    """Retorna itens salvos no cache local para uma compra específica."""
    pagina_efetiva = max(1, pagina)
    tamanho_efetivo = max(1, min(tamanho_pagina, 500))
    inicio = (pagina_efetiva - 1) * tamanho_efetivo
    fim = inicio + tamanho_efetivo

    queryset = ItemCompra.objects.filter(
        compra__ano=ano,
        compra__sequencial=sequencial,
    ).select_related("compra").order_by("numero_item")
    total = queryset.count()

    registros = [
        ItemCompraOut(
            compra_pncp_id=item.compra.pncp_id,
            compra_ano=item.compra.ano,
            compra_sequencial=item.compra.sequencial,
            numero_item=item.numero_item,
            descricao=item.descricao,
            valor_unitario_estimado=_decimal_to_str(item.valor_unitario_estimado),
            valor_total=_decimal_to_str(item.valor_total),
            valor_unitario_homologado=_decimal_to_str(item.valor_unitario_homologado),
            cnpj_vencedor=item.cnpj_vencedor,
            nome_vencedor=item.nome_vencedor,
            marca_vencedor=item.marca_vencedor,
            produto_master_id=item.produto_master_id,
        )
        for item in queryset[inicio:fim]
    ]

    return ItemCompraListResponse(
        ano=ano,
        sequencial=sequencial,
        pagina=pagina_efetiva,
        tamanhoPagina=tamanho_efetivo,
        totalRegistros=total,
        data=registros,
    )


@api.get("/catalogo/matriz", response=MatrizItemListResponse, tags=["catalogo"])
def matriz_itens_catalogo(
    request: HttpRequest,
    q: str = "",
    pagina: int = 1,
    tamanho_pagina: int = 200,
) -> MatrizItemListResponse:
    """Matriz de itens de catálogo com maior/menor/último preço homologado."""
    pagina_efetiva = max(1, pagina)
    tamanho_efetivo = max(1, min(tamanho_pagina, 500))
    inicio = (pagina_efetiva - 1) * tamanho_efetivo
    fim = inicio + tamanho_efetivo

    produtos_qs = ProdutoCatalogo.objects.all().order_by("nome_padrao")
    termo = q.strip()
    if termo:
        produtos_qs = produtos_qs.filter(
            Q(nome_padrao__icontains=termo) | Q(categoria__icontains=termo)
        )

    base_item_qs = ItemCompra.objects.filter(
        produto_master_id=OuterRef("pk"),
        valor_unitario_homologado__isnull=False,
    )
    maior_qs = base_item_qs.order_by(
        "-valor_unitario_homologado",
        "-compra__data_publicacao",
        "-compra__ano",
        "-compra__sequencial",
        "-numero_item",
    )
    menor_qs = base_item_qs.order_by(
        "valor_unitario_homologado",
        "-compra__data_publicacao",
        "-compra__ano",
        "-compra__sequencial",
        "-numero_item",
    )
    ultimo_qs = base_item_qs.order_by(
        "-compra__data_publicacao",
        "-compra__ano",
        "-compra__sequencial",
        "-numero_item",
    )

    queryset = produtos_qs.annotate(
        maior_valor=Subquery(maior_qs.values("valor_unitario_homologado")[:1]),
        maior_ano=Subquery(maior_qs.values("compra__ano")[:1]),
        maior_sequencial=Subquery(maior_qs.values("compra__sequencial")[:1]),
        maior_data_publicacao=Subquery(maior_qs.values("compra__data_publicacao")[:1]),
        menor_valor=Subquery(menor_qs.values("valor_unitario_homologado")[:1]),
        menor_ano=Subquery(menor_qs.values("compra__ano")[:1]),
        menor_sequencial=Subquery(menor_qs.values("compra__sequencial")[:1]),
        menor_data_publicacao=Subquery(menor_qs.values("compra__data_publicacao")[:1]),
        ultimo_valor=Subquery(ultimo_qs.values("valor_unitario_homologado")[:1]),
        ultimo_ano=Subquery(ultimo_qs.values("compra__ano")[:1]),
        ultimo_sequencial=Subquery(ultimo_qs.values("compra__sequencial")[:1]),
        ultimo_data_publicacao=Subquery(ultimo_qs.values("compra__data_publicacao")[:1]),
    )
    total = queryset.count()
    registros = [
        MatrizItemOut(
            catalogo_id=produto.id,
            descricao=produto.nome_padrao,
            maior_valor=_decimal_to_str(produto.maior_valor),
            maior_ano=produto.maior_ano,
            maior_sequencial=produto.maior_sequencial,
            maior_data_publicacao=(
                produto.maior_data_publicacao.isoformat()
                if produto.maior_data_publicacao
                else None
            ),
            menor_valor=_decimal_to_str(produto.menor_valor),
            menor_ano=produto.menor_ano,
            menor_sequencial=produto.menor_sequencial,
            menor_data_publicacao=(
                produto.menor_data_publicacao.isoformat()
                if produto.menor_data_publicacao
                else None
            ),
            ultimo_valor=_decimal_to_str(produto.ultimo_valor),
            ultimo_ano=produto.ultimo_ano,
            ultimo_sequencial=produto.ultimo_sequencial,
            ultimo_data_publicacao=(
                produto.ultimo_data_publicacao.isoformat()
                if produto.ultimo_data_publicacao
                else None
            ),
        )
        for produto in queryset[inicio:fim]
    ]
    return MatrizItemListResponse(
        pagina=pagina_efetiva,
        tamanhoPagina=tamanho_efetivo,
        totalRegistros=total,
        data=registros,
    )


@api.get("/catalogo", response=list[ProdutoCatalogoOut], tags=["catalogo"])
def listar_catalogo(request: HttpRequest) -> list[ProdutoCatalogoOut]:
    """Lista os produtos do catálogo master."""
    return [
        ProdutoCatalogoOut(
            id=produto.id,
            nome_padrao=produto.nome_padrao,
            categoria=produto.categoria,
            data_criacao=produto.data_criacao.isoformat(),
        )
        for produto in ProdutoCatalogo.objects.all().order_by("nome_padrao")
    ]


@api.post("/catalogo", response=ProdutoCatalogoOut, tags=["catalogo"])
def criar_produto_catalogo(
    request: HttpRequest,
    payload: ProdutoCatalogoCreateIn,
) -> ProdutoCatalogoOut:
    """Cria um novo produto no catálogo master."""
    nome = payload.nome_padrao.strip()
    if not nome:
        raise HttpError(400, "nome_padrao é obrigatório.")
    try:
        produto = ProdutoCatalogo.objects.create(
            nome_padrao=nome,
            categoria=(payload.categoria.strip() if payload.categoria else None),
        )
    except IntegrityError as exc:
        raise HttpError(409, "Produto com nome_padrao já existe.") from exc
    return ProdutoCatalogoOut(
        id=produto.id,
        nome_padrao=produto.nome_padrao,
        categoria=produto.categoria,
        data_criacao=produto.data_criacao.isoformat(),
    )


@api.post("/itens/{item_id}/vincular", response=VinculoResponse, tags=["catalogo"])
def vincular_item_catalogo(
    request: HttpRequest,
    item_id: int,
    payload: VincularCatalogoIn,
) -> VinculoResponse:
    """Vincula um item licitado a um produto do catálogo master."""
    try:
        item = ItemCompra.objects.get(id=item_id)
    except ItemCompra.DoesNotExist as exc:
        raise HttpError(404, "ItemCompra não encontrado.") from exc

    try:
        catalogo = ProdutoCatalogo.objects.get(id=payload.catalogo_id)
    except ProdutoCatalogo.DoesNotExist as exc:
        raise HttpError(404, "ProdutoCatalogo não encontrado.") from exc

    item.produto_master = catalogo
    item.save(update_fields=["produto_master"])
    return VinculoResponse(
        item_id=item.id,
        catalogo_id=catalogo.id,
        catalogo_nome=catalogo.nome_padrao,
        status="vinculado",
    )


@api.get(
    "/catalogo/{catalogo_id}/historico-precos",
    response=list[HistoricoPrecoOut],
    tags=["catalogo"],
)
def historico_precos_catalogo(
    request: HttpRequest,
    catalogo_id: int,
) -> list[HistoricoPrecoOut]:
    """Retorna histórico de preços homologados dos itens vinculados ao catálogo."""
    if not ProdutoCatalogo.objects.filter(id=catalogo_id).exists():
        raise HttpError(404, "ProdutoCatalogo não encontrado.")

    queryset = (
        ItemCompra.objects.filter(
            produto_master_id=catalogo_id,
            valor_unitario_homologado__isnull=False,
        )
        .select_related("compra")
        .order_by("compra__data_publicacao", "compra__ano", "compra__sequencial", "numero_item")
    )
    return [
        HistoricoPrecoOut(
            ano=item.compra.ano,
            sequencial=item.compra.sequencial,
            valor_estimado=_decimal_to_str(item.valor_unitario_estimado),
            valor_homologado=str(item.valor_unitario_homologado),
            fornecedor_vencedor=item.nome_vencedor,
            data_publicacao=item.compra.data_publicacao.isoformat()
            if item.compra.data_publicacao
            else None,
        )
        for item in queryset
    ]
