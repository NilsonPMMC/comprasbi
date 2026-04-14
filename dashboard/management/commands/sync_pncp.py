from __future__ import annotations

import logging
import os
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dashboard.models import Compra, ItemCompra, SyncCheckpoint

logger = logging.getLogger(__name__)

COMPRA_BASE_URL = "https://pncp.gov.br/api/consulta/v1"
ITENS_BASE_URL = "https://pncp.gov.br/api/pncp/v1"
CNPJ_MOGI = os.environ.get("PNCP_CNPJ_ORGAO", "46523270000188")
TIMEOUT = (5.0, 20.0)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
MAX_RETRIES = 3
ITEMS_PAGE_SIZE = 100
MAX_ITEM_PAGES = 200


class Command(BaseCommand):
    help = "Sincroniza compras via varredura sequencial na API oficial do PNCP."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--ano", type=int, required=True)
        parser.add_argument("--inicio", type=int, default=1)
        parser.add_argument("--fim", type=int, default=1000)
        parser.add_argument(
            "--resume",
            action="store_true",
            help=(
                "Retoma a partir do último sequencial completo gravado em SyncCheckpoint "
                "(max entre --inicio e checkpoint+1)."
            ),
        )
        parser.add_argument(
            "--reset-checkpoint",
            action="store_true",
            help="Zera o checkpoint deste órgão/ano antes de executar (útil para varredura do zero).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        ano = options["ano"]
        inicio = options["inicio"]
        fim = options["fim"]
        usar_resume = options["resume"]
        reset_checkpoint = options["reset_checkpoint"]
        if ano < 2000 or ano > 2100:
            raise CommandError("Valor de --ano inválido.")
        if inicio < 1:
            raise CommandError("Valor de --inicio inválido.")
        if fim < inicio:
            raise CommandError("Valor de --fim deve ser maior ou igual a --inicio.")

        if reset_checkpoint:
            SyncCheckpoint.objects.filter(orgao_cnpj=CNPJ_MOGI, ano=ano).delete()
            self.stdout.write(
                self.style.WARNING(
                    f"[sync_pncp] Checkpoint resetado para CNPJ={CNPJ_MOGI} ano={ano}."
                )
            )

        loop_start = inicio
        if usar_resume:
            ultimo = self._ler_ultimo_checkpoint(ano)
            loop_start = max(inicio, ultimo + 1)
            self.stdout.write(
                f"[sync_pncp] --resume: último sequencial completo={ultimo}; "
                f"iniciando em {loop_start}."
            )

        salvas = 0
        sequenciais_vazios = 0
        falhas_rede = 0
        falhas_http = 0
        sequenciais_falhos: list[int] = []

        self.stdout.write(
            f"[sync_pncp] Varredura ano={ano}, cnpj={CNPJ_MOGI}, faixa efetiva {loop_start}-{fim}."
        )

        for sequencial in range(loop_start, fim + 1):
            compra_url = f"{COMPRA_BASE_URL}/orgaos/{CNPJ_MOGI}/compras/{ano}/{sequencial}"
            response, erro = self._request_with_retry(compra_url)
            if response is None:
                falhas_rede += 1
                if erro is not None:
                    logger.warning("Erro de rede compra seq=%s: %s", sequencial, erro)
                sequenciais_falhos.append(sequencial)
                time.sleep(0.2)
                continue

            avancar_checkpoint = False

            if response.status_code == 404:
                self.stdout.write(f"Sequencial {sequencial} vazio.")
                sequenciais_vazios += 1
                avancar_checkpoint = True
            elif response.status_code == 200:
                try:
                    compra_payload = response.json()
                except ValueError:
                    logger.warning("JSON inválido para compra seq=%s", sequencial)
                    falhas_http += 1
                    sequenciais_falhos.append(sequencial)
                    time.sleep(0.2)
                    continue

                compra = self._upsert_compra(compra_payload, ano=ano, sequencial=sequencial)
                itens_ok = self._sync_itens(compra=compra, ano=ano, sequencial=sequencial)
                if not itens_ok:
                    falhas_rede += 1
                    sequenciais_falhos.append(sequencial)
                else:
                    avancar_checkpoint = True
                salvas += 1
                if salvas % 20 == 0:
                    self.stdout.write(
                        f"[sync_pncp] {salvas} compras processadas; último sequencial={sequencial}."
                    )
            else:
                logger.warning(
                    "Status inesperado compra seq=%s: %s",
                    sequencial,
                    response.status_code,
                )
                falhas_http += 1
                sequenciais_falhos.append(sequencial)

            if avancar_checkpoint:
                self._persist_checkpoint(ano, sequencial)

            time.sleep(0.2)

        if sequenciais_falhos:
            unicos = sorted(set(sequenciais_falhos))
            self.stdout.write(f"[sync_pncp] Sequenciais com falha: {unicos}")
        self.stdout.write(
            self.style.SUCCESS(
                "[sync_pncp] Concluído. "
                f"Compras processadas com sucesso: {salvas}. "
                f"Vazios: {sequenciais_vazios}. "
                f"Falhas de rede: {falhas_rede}. "
                f"Falhas HTTP/JSON: {falhas_http}. "
                f"Sequenciais com falha: {len(set(sequenciais_falhos))}."
            )
        )

    def _ler_ultimo_checkpoint(self, ano: int) -> int:
        row = SyncCheckpoint.objects.filter(orgao_cnpj=CNPJ_MOGI, ano=ano).first()
        return int(row.ultimo_sequencial_completo) if row else 0

    def _persist_checkpoint(self, ano: int, sequencial: int) -> None:
        SyncCheckpoint.objects.update_or_create(
            orgao_cnpj=CNPJ_MOGI,
            ano=ano,
            defaults={"ultimo_sequencial_completo": sequencial},
        )

    @transaction.atomic
    def _upsert_compra(self, payload: dict[str, Any], *, ano: int, sequencial: int) -> Compra:
        orgao = payload.get("orgaoEntidade") if isinstance(payload.get("orgaoEntidade"), dict) else {}
        cnpj = self._digits(str(orgao.get("cnpj") or CNPJ_MOGI))
        pncp_id = str(payload.get("numeroControlePNCP") or f"{cnpj}-{ano}-{sequencial}")

        compra, _ = Compra.objects.update_or_create(
            pncp_id=pncp_id,
            defaults={
                "orgao_cnpj": cnpj,
                "ano": int(payload.get("anoCompra") or ano),
                "sequencial": int(payload.get("sequencialCompra") or sequencial),
                "numero_compra": str(payload.get("numeroCompra") or "").strip(),
                "modalidade_id": int(payload.get("modalidadeId") or 0),
                "modalidade_nome": str(payload.get("modalidadeNome") or ""),
                "data_publicacao": self._to_date(payload.get("dataPublicacaoPncp")),
                "objeto": str(payload.get("objetoCompra") or ""),
                "valor_total_estimado": self._to_decimal(payload.get("valorTotalEstimado")),
            },
        )
        return compra

    @transaction.atomic
    def _sync_itens(self, *, compra: Compra, ano: int, sequencial: int) -> bool:
        pagina_itens = 1
        assinatura_anterior: tuple[int, int, int] | None = None
        while True:
            if pagina_itens > MAX_ITEM_PAGES:
                logger.warning(
                    "Interrompendo paginação de itens por limite de segurança compra %s.",
                    compra.pncp_id,
                )
                break
            itens_url = (
                f"{ITENS_BASE_URL}/orgaos/{CNPJ_MOGI}/compras/{ano}/{sequencial}/itens"
                f"?pagina={pagina_itens}&tamanhoPagina={ITEMS_PAGE_SIZE}"
            )
            response, erro = self._request_with_retry(itens_url)
            if response is None:
                logger.warning(
                    "Falha ao sincronizar itens compra %s (pagina=%s): %s",
                    compra.pncp_id,
                    pagina_itens,
                    erro,
                )
                return False
            try:
                response.raise_for_status()
                itens_payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                logger.warning(
                    "Falha ao sincronizar itens compra %s (pagina=%s): %s",
                    compra.pncp_id,
                    pagina_itens,
                    exc,
                )
                return False

            if isinstance(itens_payload, list):
                itens = itens_payload
            elif isinstance(itens_payload, dict):
                itens = itens_payload.get("data", [])
            else:
                itens = []

            if not isinstance(itens, list) or len(itens) == 0:
                break

            numeros_pagina = [
                int(item.get("numeroItem") or 0)
                for item in itens
                if isinstance(item, dict)
            ]
            if numeros_pagina:
                assinatura_atual = (len(itens), numeros_pagina[0], numeros_pagina[-1])
                if assinatura_atual == assinatura_anterior:
                    logger.warning(
                        "Pagina de itens repetida detectada compra %s (pagina=%s). Interrompendo.",
                        compra.pncp_id,
                        pagina_itens,
                    )
                    break
                assinatura_anterior = assinatura_atual

            for item in itens:
                if not isinstance(item, dict):
                    continue
                numero_item = int(item.get("numeroItem") or 0)
                if numero_item <= 0:
                    continue
                valor_unitario_homologado = None
                cnpj_vencedor = ""
                nome_vencedor = ""
                marca_vencedor = ""
                if item.get("temResultado") is True:
                    resultado = self._buscar_resultado_item(
                        ano=ano,
                        sequencial=sequencial,
                        numero_item=numero_item,
                        cnpj=compra.orgao_cnpj or CNPJ_MOGI,
                    )
                    if isinstance(resultado, dict):
                        valor_unitario_homologado = self._to_decimal(
                            resultado.get("valorUnitarioHomologado")
                        )
                        cnpj_vencedor = self._digits(str(resultado.get("niFornecedor") or ""))
                        nome_vencedor = str(resultado.get("nomeRazaoSocialFornecedor") or "")
                        marca_vencedor = str(resultado.get("marcaProduto") or "")
                    time.sleep(0.1)

                ItemCompra.objects.update_or_create(
                    compra=compra,
                    numero_item=numero_item,
                    defaults={
                        "descricao": str(item.get("descricao") or ""),
                        "valor_unitario_estimado": self._to_decimal(item.get("valorUnitarioEstimado")),
                        "valor_total": self._to_decimal(item.get("valorTotal")),
                        "valor_unitario_homologado": valor_unitario_homologado,
                        "cnpj_vencedor": cnpj_vencedor,
                        "nome_vencedor": nome_vencedor,
                        "marca_vencedor": marca_vencedor,
                    },
                )

            pagina_itens += 1
            if len(itens) < ITEMS_PAGE_SIZE:
                break
            time.sleep(0.2)
        return True

    def _buscar_resultado_item(
        self,
        *,
        ano: int,
        sequencial: int,
        numero_item: int,
        cnpj: str,
    ) -> dict[str, Any] | None:
        resultados_url = (
            f"{ITENS_BASE_URL}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/{numero_item}/resultados"
            "?pagina=1&tamanhoPagina=10"
        )
        response, erro = self._request_with_retry(resultados_url)
        if response is None:
            logger.warning(
                "Falha ao buscar resultado do item seq=%s item=%s: %s",
                sequencial,
                numero_item,
                erro,
            )
            return None
        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning(
                "Falha ao buscar resultado do item seq=%s item=%s: %s",
                sequencial,
                numero_item,
                exc,
            )
            return None

        if isinstance(payload, dict):
            data = payload.get("data", [])
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0]
            if isinstance(data, dict):
                return data
        elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]
        return None

    def _request_with_retry(self, url: str) -> tuple[requests.Response | None, Exception | None]:
        last_error: Exception | None = None
        for tentativa in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                return response, None
            except requests.RequestException as exc:
                last_error = exc
                if tentativa < MAX_RETRIES:
                    time.sleep(float(2 ** (tentativa - 1)))
        return None, last_error

    @staticmethod
    def _digits(value: str) -> str:
        return "".join(ch for ch in value if ch.isdigit())

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if not value:
            return None
        text = str(value)
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
