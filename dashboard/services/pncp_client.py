"""
Cliente HTTP para a API pública do Portal Nacional de Contratações Públicas (PNCP),
com escopo fixo na Prefeitura de Mogi das Cruzes (CNPJ configurável na constante).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Mapping
from urllib.parse import urljoin

import requests
from requests import Response
from requests.exceptions import HTTPError, RequestException

logger = logging.getLogger(__name__)

BASE_URL: str = "https://pncp.gov.br/api/pncp/v1"
"""Base da API de **cadastro** (compras, itens, resultados por órgão)."""

CONSULTA_BASE_URL: str = "https://pncp.gov.br/api/consulta/v1"
"""Base da API de **consulta** pública."""

CNPJ_PREFEITURA_MOGI_DAS_CRUZES: str = "46523270000188"

class PNCPClientError(Exception):
    """Falha ao obter ou interpretar resposta da API do PNCP."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class PNCPClient:
    """
    Cliente síncrono para o PNCP.

    - **Listagem por ano:** usa a API de consulta pública
      ``GET /consulta/v1/contratacoes/publicacao``.
    - **Itens e resultados:** permanecem em ``BASE_URL`` (cadastro), com GET.
    """

    DEFAULT_TIMEOUT: tuple[float, float] = (4.0, 12.0)
    MODALIDADES: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
    REQUEST_TIMEOUT: tuple[float, float] = (3.0, 6.0)
    MAX_SECONDS_PER_CALL: float = 12.0
    CACHE_TTL_SECONDS: int = 600
    _CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

    _CNPJ_DIGITS_RE = re.compile(r"\D")

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        cnpj_orgao: str = CNPJ_PREFEITURA_MOGI_DAS_CRUZES,
        timeout: tuple[float, float] | None = None,
    ) -> None:
        self._cnpj = cnpj_orgao
        self._cnpj_digits = self._only_digits(cnpj_orgao)
        self._session = session or requests.Session()
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._session.headers.setdefault("Accept", "application/json")
        self._session.headers.setdefault(
            "User-Agent",
            "MogiComprasBI/1.0 (Django; +https://www.gov.br/pncp)",
        )

    @staticmethod
    def _only_digits(cnpj: str) -> str:
        return PNCPClient._CNPJ_DIGITS_RE.sub("", cnpj)

    def _build_url(self, path: str, *, base: str = BASE_URL) -> str:
        root = base if base.endswith("/") else f"{base}/"
        return urljoin(root, path.lstrip("/"))

    def _parse_error_detail(self, response: Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text or None

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        base_url: str = BASE_URL,
        params: Mapping[str, Any] | None = None,
        timeout: tuple[float, float] | None = None,
    ) -> Any:
        url = self._build_url(path, base=base_url)
        try:
            response = self._session.request(
                method,
                url,
                params=params,
                timeout=timeout or self._timeout,
            )
            response.raise_for_status()
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            detail = (
                self._parse_error_detail(exc.response)
                if exc.response is not None
                else None
            )
            logger.warning(
                "PNCP HTTP %s: %s | status=%s detail=%s",
                method,
                url,
                status,
                detail,
            )
            raise PNCPClientError(
                f"Resposta HTTP inesperada do PNCP ({status}).",
                status_code=status,
                detail=detail,
            ) from exc
        except RequestException as exc:
            logger.warning("Falha de rede ao chamar PNCP: %s %s", method, url)
            raise PNCPClientError(
                "Não foi possível contatar a API do PNCP (rede ou tempo esgotado).",
                detail=str(exc),
            ) from exc

        if not response.content:
            return None

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Corpo da resposta PNCP não é JSON válido: %s", url)
            raise PNCPClientError(
                "Resposta do PNCP não é JSON válido.",
                status_code=response.status_code,
                detail=response.text[:500] if response.text else None,
            ) from exc

    def get_compras_por_ano(
        self,
        ano: int,
        *,
        pagina: int = 1,
        tamanho_pagina: int = 20,
    ) -> Any:
        """
        Lista contratações publicadas no PNCP para o órgão e ano informados.
        """
        if ano < 2000 or ano > 2100:
            raise ValueError("ano fora do intervalo suportado")

        pagina_efetiva = max(1, int(pagina))
        tamanho_efetivo = max(10, min(int(tamanho_pagina), 50))
        cache_key = f"{self._cnpj_digits}:{ano}:{pagina_efetiva}:{tamanho_efetivo}"
        now = time.time()
        cached = self._CACHE.get(cache_key)
        if cached and (now - cached[0]) < self.CACHE_TTL_SECONDS:
            return cached[1]

        inicio = time.monotonic()
        itens_filtrados: list[dict[str, Any]] = []
        vistos: set[str] = set()
        modalidades_ok = 0
        modalidades_tentadas = 0

        url = self._build_url("contratacoes/publicacao", base=CONSULTA_BASE_URL)
        for modalidade in self.MODALIDADES:
            if (time.monotonic() - inicio) >= self.MAX_SECONDS_PER_CALL:
                break

            modalidades_tentadas += 1
            params: dict[str, Any] = {
                "cnpjOrgao": self._cnpj_digits,
                "dataInicial": f"{ano}0101",
                "dataFinal": f"{ano}1231",
                "pagina": pagina_efetiva,
                "tamanhoPagina": tamanho_efetivo,
                "codigoModalidadeContratacao": modalidade,
            }
            try:
                response = self._session.get(
                    url,
                    params=params,
                    timeout=self.REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
            except (RequestException, ValueError) as exc:
                logger.warning("PNCP modalidade %s falhou: %s", modalidade, exc)
                continue

            modalidades_ok += 1
            data = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(data, list):
                continue

            for item in data:
                if not isinstance(item, dict):
                    continue
                orgao = item.get("orgaoEntidade")
                cnpj_item = (
                    self._only_digits(str(orgao.get("cnpj")))
                    if isinstance(orgao, dict)
                    else ""
                )
                if cnpj_item != self._cnpj_digits:
                    continue
                if int(item.get("anoCompra", 0) or 0) != ano:
                    continue
                chave = str(
                    item.get("numeroControlePNCP")
                    or f"{item.get('anoCompra')}:{item.get('sequencialCompra')}"
                )
                if chave in vistos:
                    continue
                vistos.add(chave)
                itens_filtrados.append(item)

        result: dict[str, Any] = {
            "fonte": f"{CONSULTA_BASE_URL.rstrip('/')}/contratacoes/publicacao",
            "cnpjOrgao": self._cnpj_digits,
            "ano": ano,
            "pagina": pagina_efetiva,
            "tamanhoPagina": tamanho_efetivo,
            "data": itens_filtrados,
            "totalRegistros": len(itens_filtrados),
            "modoConsulta": "publicacao_por_modalidade_cache",
            "modalidadesConsultadas": modalidades_tentadas,
            "modalidadesComSucesso": modalidades_ok,
            "parcial": modalidades_tentadas < len(self.MODALIDADES),
        }
        self._CACHE[cache_key] = (now, result)
        return result

    def get_itens_compra(
        self,
        ano: int,
        sequencial_compra: int,
        *,
        pagina: int = 1,
        tamanho_pagina: int = 50,
    ) -> Any:
        """
        Itens de uma compra específica do órgão.

        ``GET /orgaos/{cnpj}/compras/{ano}/{sequencial_compra}/itens``
        """
        path = f"orgaos/{self._cnpj}/compras/{ano}/{sequencial_compra}/itens"
        params: dict[str, Any] = {
            "pagina": max(1, pagina),
            "tamanhoPagina": max(1, min(tamanho_pagina, 100)),
        }
        return self._request_json("GET", path, params=params)

    def get_resultado_item(
        self,
        ano: int,
        sequencial_compra: int,
        numero_item: int,
    ) -> Any:
        """
        Resultados de adjudicação/homologação de um item.

        ``GET .../itens/{numero_item}/resultados``
        """
        path = (
            f"orgaos/{self._cnpj}/compras/{ano}/{sequencial_compra}/itens/"
            f"{numero_item}/resultados"
        )
        return self._request_json("GET", path)
