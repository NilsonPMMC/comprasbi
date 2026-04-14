from __future__ import annotations

from django.contrib import admin
from django.contrib.admin import EmptyFieldListFilter, SimpleListFilter
from django.db.models import CharField, Count, Value
from django.db.models.functions import Coalesce, Trim

from dashboard.models import Compra, ItemCompra, ItemMapping, ProdutoCatalogo, SyncCheckpoint


class ItemCompraMapeamentoFilter(SimpleListFilter):
    """Relatório rápido: órfãos sem descrição (não entram no auto_map_itens)."""

    title = "situação no catálogo"
    parameter_name = "mapeamento"

    def lookups(self, request, model_admin):
        return (
            ("vinculado", "Vinculado ao catálogo"),
            ("orfao_mapeavel", "Órfão — com descrição (mapeável)"),
            ("orfao_sem_desc", "Órfão — sem descrição"),
        )

    def queryset(self, request, queryset):
        v = self.value()
        if v == "vinculado":
            return queryset.filter(produto_master__isnull=False)
        if v == "orfao_mapeavel":
            return (
                queryset.filter(produto_master__isnull=True)
                .annotate(
                    _desc_limpa=Coalesce(
                        Trim("descricao"),
                        Value("", output_field=CharField()),
                        output_field=CharField(),
                    )
                )
                .exclude(_desc_limpa="")
            )
        if v == "orfao_sem_desc":
            return (
                queryset.filter(produto_master__isnull=True)
                .annotate(
                    _desc_limpa=Coalesce(
                        Trim("descricao"),
                        Value("", output_field=CharField()),
                        output_field=CharField(),
                    )
                )
                .filter(_desc_limpa="")
            )
        return queryset


@admin.register(ItemMapping)
class ItemMappingAdmin(admin.ModelAdmin):
    list_display = (
        "ano_origem",
        "codigo_origem",
        "descricao_origem",
        "ano_destino",
        "codigo_destino",
    )
    list_filter = ("ano_origem", "ano_destino")
    search_fields = ("codigo_origem", "codigo_destino", "descricao_origem")


@admin.register(SyncCheckpoint)
class SyncCheckpointAdmin(admin.ModelAdmin):
    list_display = ("orgao_cnpj", "ano", "ultimo_sequencial_completo", "updated_at")
    list_filter = ("ano",)
    search_fields = ("orgao_cnpj",)


@admin.register(ProdutoCatalogo)
class ProdutoCatalogoAdmin(admin.ModelAdmin):
    """Catálogo master — mesma fonte do GET /api/catalogo."""

    list_display = (
        "id",
        "nome_padrao",
        "categoria",
        "data_criacao",
        "qtd_itens_vinculados",
        "embedding_resumo",
    )
    list_filter = (
        "categoria",
        ("embedding", EmptyFieldListFilter),
    )
    search_fields = ("nome_padrao", "categoria")
    fields = ("nome_padrao", "categoria", "data_criacao", "embedding_formatado")
    readonly_fields = ("data_criacao", "embedding_formatado")
    ordering = ("nome_padrao",)

    @admin.display(description="itens vinculados", ordering="_qtd_itens")
    def qtd_itens_vinculados(self, obj: ProdutoCatalogo) -> int:
        return getattr(obj, "_qtd_itens", 0)

    @admin.display(description="embedding (lista)")
    def embedding_resumo(self, obj: ProdutoCatalogo) -> str:
        if obj.embedding is None:
            return "—"
        try:
            vetor = list(obj.embedding)
        except TypeError:
            return "sim"
        n = len(vetor)
        if n == 0:
            return "vazio"
        amostra = ", ".join(f"{x:.4g}" for x in vetor[:4])
        sufixo = f" … (+{n - 4})" if n > 4 else ""
        return f"{n} dims · [{amostra}{sufixo}]"

    @admin.display(description="embedding (vetor completo, abreviado no meio)")
    def embedding_formatado(self, obj: ProdutoCatalogo | None) -> str:
        if obj is None or obj.pk is None:
            return "— (salve o registro para ver o vetor)"
        if obj.embedding is None:
            return "— (sem embedding)"
        try:
            vetor = list(obj.embedding)
        except TypeError:
            return str(obj.embedding)
        n = len(vetor)
        if n <= 24:
            return "[" + ", ".join(f"{x:.6g}" for x in vetor) + "]"
        head = ", ".join(f"{x:.6g}" for x in vetor[:12])
        tail = ", ".join(f"{x:.6g}" for x in vetor[-8:])
        return (
            f"[{head}, … ({n - 20} valores omitidos no meio) …, {tail}]"
        )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_qtd_itens=Count("itens_vinculados"))
        )


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = (
        "pncp_id",
        "orgao_cnpj",
        "ano",
        "sequencial",
        "data_publicacao",
        "modalidade_nome",
        "valor_total_estimado",
    )
    list_filter = ("ano", "modalidade_id")
    search_fields = ("pncp_id", "orgao_cnpj", "objeto")
    ordering = ("-ano", "-sequencial")
    date_hierarchy = "data_publicacao"


@admin.register(ItemCompra)
class ItemCompraAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "compra",
        "numero_item",
        "produto_master",
        "descricao_resumo",
        "situacao_mapeamento",
        "valor_unitario_homologado",
        "nome_vencedor",
    )
    list_filter = (
        ItemCompraMapeamentoFilter,
        "produto_master",
        "compra__ano",
    )
    search_fields = (
        "descricao",
        "nome_vencedor",
        "compra__pncp_id",
        "compra__orgao_cnpj",
    )
    autocomplete_fields = ("produto_master",)
    raw_id_fields = ("compra",)  # muitas linhas; evita dropdown pesado

    @admin.display(description="descrição")
    def descricao_resumo(self, obj: ItemCompra) -> str:
        t = (obj.descricao or "").strip()
        if not t:
            return "—"
        return t[:80] + ("…" if len(t) > 80 else "")

    @admin.display(description="mapeamento")
    def situacao_mapeamento(self, obj: ItemCompra) -> str:
        if obj.produto_master_id:
            return "Vinculado"
        if not (obj.descricao or "").strip():
            return "Órfão — sem descrição"
        return "Órfão — mapeável"
