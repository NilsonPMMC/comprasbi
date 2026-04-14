from __future__ import annotations

from django.db import models
from pgvector.django import VectorField


class ItemMapping(models.Model):
    """
    Mapeamento entre código/descrição de origem e código de destino
    (ex.: harmonização de itens entre bases ou exercícios).
    """

    ano_origem = models.IntegerField("ano de origem")
    codigo_origem = models.CharField("código de origem", max_length=64)
    descricao_origem = models.CharField("descrição de origem", max_length=512)
    ano_destino = models.IntegerField("ano de destino")
    codigo_destino = models.CharField("código de destino", max_length=64)

    class Meta:
        verbose_name = "mapeamento de item"
        verbose_name_plural = "mapeamentos de itens"
        ordering = ("ano_origem", "codigo_origem")

    def __str__(self) -> str:
        return (
            f"{self.ano_origem}/{self.codigo_origem} → "
            f"{self.ano_destino}/{self.codigo_destino}"
        )


class SyncCheckpoint(models.Model):
    """
    Último sequencial de compra totalmente sincronizado por órgão/ano.
    Usado por `sync_pncp --resume` para retomada após interrupção.
    """

    orgao_cnpj = models.CharField(max_length=14, db_index=True)
    ano = models.IntegerField(db_index=True)
    ultimo_sequencial_completo = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("orgao_cnpj", "ano")
        ordering = ("-ano", "orgao_cnpj")

    def __str__(self) -> str:
        return f"{self.orgao_cnpj} {self.ano} → seq<={self.ultimo_sequencial_completo}"


class Compra(models.Model):
    """Replica local de compras publicadas no PNCP."""

    pncp_id = models.CharField(max_length=64, unique=True)
    orgao_cnpj = models.CharField(max_length=14, db_index=True)
    ano = models.IntegerField(db_index=True)
    sequencial = models.IntegerField()
    numero_compra = models.CharField(max_length=64, blank=True, default="", db_index=True)
    modalidade_id = models.IntegerField()
    modalidade_nome = models.CharField(max_length=120, blank=True, default="")
    data_publicacao = models.DateField(null=True, blank=True)
    objeto = models.TextField(blank=True, default="")
    valor_total_estimado = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-ano", "sequencial")
        unique_together = ("orgao_cnpj", "ano", "sequencial")

    def __str__(self) -> str:
        return f"{self.ano}/{self.sequencial} - {self.orgao_cnpj}"


class ProdutoCatalogo(models.Model):
    """Catálogo master para mapeamento (de/para) dos itens licitados."""

    nome_padrao = models.CharField(max_length=255, unique=True)
    categoria = models.CharField(max_length=120, null=True, blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    embedding = VectorField(dimensions=1024, null=True, blank=True)

    class Meta:
        ordering = ("nome_padrao",)

    def __str__(self) -> str:
        return self.nome_padrao


class ItemCompra(models.Model):
    """Itens vinculados a uma compra local replicada do PNCP."""

    compra = models.ForeignKey(
        Compra,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    produto_master = models.ForeignKey(
        ProdutoCatalogo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itens_vinculados",
    )
    numero_item = models.IntegerField()
    descricao = models.TextField(blank=True, default="")
    valor_unitario_estimado = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    valor_total = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    valor_unitario_homologado = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cnpj_vencedor = models.CharField(max_length=14, blank=True, default="")
    nome_vencedor = models.CharField(max_length=255, blank=True, default="")
    marca_vencedor = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("numero_item",)
        unique_together = ("compra", "numero_item")

    def __str__(self) -> str:
        return f"{self.compra.pncp_id} item {self.numero_item}"
