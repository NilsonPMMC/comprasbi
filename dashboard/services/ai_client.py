"""Cliente HTTP para o microsserviço local de embeddings (Shared AI Service)."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("AI_SERVICE_URL", "http://127.0.0.1:8004").rstrip("/")
EMBEDDINGS_PATH = "/v1/embeddings"
TIMEOUT = (5.0, 60.0)


class SharedAIClientError(Exception):
    """Erro ao comunicar com o serviço de IA ou ao interpretar a resposta."""


class SharedAIClient:
    """Consome o endpoint de embeddings do Shared AI Service."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or BASE_URL).rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base_url

    def gerar_embedding(self, texto: str) -> list[float]:
        """
        Gera embedding para um único texto via POST /v1/embeddings.

        Body: {"texts": [texto]}
        Resposta esperada: {"embeddings": [[...], ...]}
        """
        if not texto or not texto.strip():
            raise SharedAIClientError("texto não pode ser vazio.")

        url = f"{self._base_url}{EMBEDDINGS_PATH}"
        payload: dict[str, Any] = {"texts": [texto]}

        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
        except RequestException as exc:
            # Detalhe em debug: o comando chamador trata e evita log duplicado por item.
            logger.debug("Falha de rede ao serviço de IA (%s): %s", url, exc, exc_info=True)
            raise SharedAIClientError(f"Falha ao contatar serviço de IA: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("Resposta não-JSON do serviço de IA: %s", response.text[:500])
            raise SharedAIClientError("Resposta inválida (não é JSON).") from exc

        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise SharedAIClientError("Resposta sem chave 'embeddings' ou lista vazia.")

        first = embeddings[0]
        if not isinstance(first, list):
            raise SharedAIClientError("Primeiro embedding não é uma lista de floats.")

        return [float(x) for x in first]
