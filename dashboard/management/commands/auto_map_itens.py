"""Mapeia itens órfãos ao catálogo master via embeddings e similaridade coseno (pgvector)."""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import CharField, Value
from django.db.models.functions import Coalesce, Trim
from pgvector.django import CosineDistance

from dashboard.models import ItemCompra, ProdutoCatalogo
from dashboard.services.ai_client import SharedAIClient, SharedAIClientError

logger = logging.getLogger(__name__)

DISTANCIA_MAXIMA = 0.15
NOME_PADRAO_MAX_LEN = 250


def _servico_ia_indisponivel(mensagem: str) -> bool:
    """True quando não adianta insistir item a item (serviço inacessível)."""
    m = mensagem.lower()
    return any(
        frag in m
        for frag in (
            "connection refused",
            "failed to establish",
            "name or service not known",
            "getaddrinfo failed",
            "network is unreachable",
            "no route to host",
        )
    )


class Command(BaseCommand):
    help = (
        "Agrupa itens sem produto_master usando embeddings e vizinho mais próximo no catálogo. "
        "Use --continuo para lotes até não restarem itens com descrição (ideal para cron)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Tamanho de cada lote: máximo de itens órfãos por rodada.",
        )
        parser.add_argument(
            "--continuo",
            action="store_true",
            help=(
                "Repete lotes de --limit até não haver mais itens mapeáveis "
                "(com descrição não vazia) ou até --max-rodadas."
            ),
        )
        parser.add_argument(
            "--max-rodadas",
            type=int,
            default=None,
            help="Com --continuo: para após N rodadas (omita para ilimitado).",
        )
        parser.add_argument(
            "--pausa-segundos",
            type=float,
            default=0.0,
            help="Com --continuo: espera entre rodadas (ex.: 0.5 para não saturar a IA).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        limit = max(1, options["limit"])
        continuo = options["continuo"]
        max_rodadas = options["max_rodadas"]
        pausa = max(0.0, float(options["pausa_segundos"]))
        ai_client = SharedAIClient()

        rodada = 0
        while True:
            rodada += 1
            if continuo and max_rodadas is not None and rodada > max_rodadas:
                self.stdout.write(
                    self.style.WARNING(
                        f"[auto_map_itens] Parado: --max-rodadas={max_rodadas} atingido."
                    )
                )
                break

            itens = list(
                self._queryset_orfaos_com_descricao().order_by("id")[:limit]
            )
            if not itens:
                if rodada == 1:
                    self.stdout.write(
                        "Nenhum item pendente de mapeamento (com descrição utilizável)."
                    )
                elif continuo:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "[auto_map_itens] Fila esvaziada: nenhum órfão com descrição."
                        )
                    )
                break

            modo = f"rodada {rodada}" if continuo else "execução única"
            self.stdout.write(
                f"[auto_map_itens] {modo}: até {len(itens)} item(ns)..."
            )
            self.stdout.flush()

            self._processar_lote(itens, ai_client)

            if not continuo:
                break
            if pausa > 0:
                time.sleep(pausa)

        self.stdout.write(self.style.SUCCESS("[auto_map_itens] Concluído."))

    @staticmethod
    def _queryset_orfaos_com_descricao():
        """Órfãos cuja descrição, após trim, não é vazia (evita fila infinita inútil)."""
        return (
            ItemCompra.objects.filter(produto_master__isnull=True)
            .annotate(
                _desc_limpa=Coalesce(
                    Trim("descricao"),
                    Value("", output_field=CharField()),
                    output_field=CharField(),
                )
            )
            .exclude(_desc_limpa="")
        )

    def _processar_lote(self, itens: list[ItemCompra], ai_client: SharedAIClient) -> None:
        for item in itens:
            descricao = (item.descricao or "").strip()
            if not descricao:
                logger.warning("Item id=%s sem descrição; ignorando.", item.id)
                continue

            try:
                vetor_desc = ai_client.gerar_embedding(descricao)
            except SharedAIClientError as exc:
                msg = str(exc)
                if _servico_ia_indisponivel(msg):
                    raise CommandError(
                        "[auto_map_itens] Serviço de embeddings inacessível em "
                        f"{ai_client.base_url}. Suba o Shared AI Service ou defina "
                        f"AI_SERVICE_URL no .env.\nDetalhe: {msg}"
                    ) from exc
                logger.warning("Falha de IA no item id=%s: %s", item.id, exc)
                continue
            except Exception as exc:
                logger.exception("Erro inesperado na IA para item id=%s: %s", item.id, exc)
                continue

            if not vetor_desc:
                logger.warning("Embedding vazio para item id=%s.", item.id)
                continue

            try:
                self._processar_item(item, vetor_desc, descricao)
            except Exception as exc:
                logger.exception("Falha ao persistir mapeamento item id=%s: %s", item.id, exc)

    def _processar_item(
        self,
        item: ItemCompra,
        vetor_desc: list[float],
        descricao: str,
    ) -> None:
        with transaction.atomic():
            item_locked = ItemCompra.objects.select_for_update().get(pk=item.pk)
            if item_locked.produto_master_id is not None:
                return

            cat_proximo = (
                ProdutoCatalogo.objects.filter(embedding__isnull=False)
                .annotate(distance=CosineDistance("embedding", vetor_desc))
                .order_by("distance")
                .first()
            )

            if cat_proximo is not None and cat_proximo.distance is not None:
                dist = float(cat_proximo.distance)
                if dist <= DISTANCIA_MAXIMA:
                    item_locked.produto_master = cat_proximo
                    item_locked.save(update_fields=["produto_master"])
                    preview = descricao[:30] + ("..." if len(descricao) > 30 else "")
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"VINCULADO: '{preview}' -> '{cat_proximo.nome_padrao}' "
                            f"(Distância: {dist:.3f})"
                        )
                    )
                    return

            nome = descricao[:NOME_PADRAO_MAX_LEN]
            novo_cat = self._criar_ou_recuperar_catalogo(nome, vetor_desc)
            item_locked.produto_master = novo_cat
            item_locked.save(update_fields=["produto_master"])
            preview_cat = novo_cat.nome_padrao[:30] + (
                "..." if len(novo_cat.nome_padrao) > 30 else ""
            )
            self.stdout.write(
                self.style.WARNING(f"NOVO CATÁLOGO CRIADO: '{preview_cat}'")
            )

    def _criar_ou_recuperar_catalogo(
        self,
        nome_padrao: str,
        vetor_desc: list[float],
    ) -> ProdutoCatalogo:
        try:
            return ProdutoCatalogo.objects.create(
                nome_padrao=nome_padrao,
                embedding=vetor_desc,
            )
        except IntegrityError:
            existente = ProdutoCatalogo.objects.get(nome_padrao=nome_padrao)
            if existente.embedding is None:
                existente.embedding = vetor_desc
                existente.save(update_fields=["embedding"])
            return existente
