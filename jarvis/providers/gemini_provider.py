"""Integración con la API de Google Gemini mediante el SDK oficial google-genai."""

from __future__ import annotations

import time
from typing import Any

from jarvis.core.errors import (
    ProviderNotConfiguredError,
    ProviderResponseError,
    classify_provider_error,
)
from jarvis.core.logging_setup import get_logger

logger = get_logger("gemini")

PROVIDER_NAME = "Google Gemini"

# Códigos transitorios del servidor: merece la pena reintentar antes de fallar.
_TRANSIENT_STATUS = {500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_RETRY_DELAYS = (2.0, 5.0)


def _status_code(exc: BaseException) -> int | None:
    for attribute in ("status_code", "code", "http_status"):
        value = getattr(exc, attribute, None)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _is_transient(exc: BaseException) -> bool:
    return _status_code(exc) in _TRANSIENT_STATUS


class GeminiProvider:
    """Cliente mínimo de Gemini para generar respuestas basadas en contexto.

    Se usa ``client.models.generate_content`` del SDK oficial ``google-genai``.
    El cliente se crea de forma diferida para que Jarvis pueda arrancar en
    modo texto aunque no haya clave configurada.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ProviderNotConfiguredError(
                "No hay clave de Gemini configurada (GEMINI_API_KEY). "
                "Añádela al archivo .env para poder preguntar y resumir."
            )
        if not model:
            raise ProviderNotConfiguredError(
                "No hay modelo de Gemini configurado (GEMINI_MODEL)."
            )
        self._api_key = api_key
        self._model = model
        self._client = client

    @property
    def model_name(self) -> str:
        return self._model

    def _ensure_client(self) -> Any:
        if self._client is None:
            from google import genai  # importación diferida

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def complete(
        self,
        *,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.2,
        max_output_tokens: int = 1500,
    ) -> str:
        client = self._ensure_client()
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        response = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=config,
                )
                break
            except Exception as exc:
                if _is_transient(exc) and attempt < _MAX_ATTEMPTS:
                    delay = _RETRY_DELAYS[min(attempt - 1, len(_RETRY_DELAYS) - 1)]
                    logger.warning(
                        "Servicio de Gemini no disponible (intento %d de %d); "
                        "reintentando en %.0f s",
                        attempt,
                        _MAX_ATTEMPTS,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                logger.warning(
                    "Error de Gemini con el modelo %s: %s",
                    self._model,
                    type(exc).__name__,
                )
                raise classify_provider_error(exc, PROVIDER_NAME) from exc

        if response is None:  # pragma: no cover - salvaguarda
            raise ProviderResponseError(
                "Gemini no devolvió respuesta. Inténtalo de nuevo."
            )

        text = self._extract_text(response)
        logger.info(
            "Respuesta de Gemini generada (modelo=%s, caracteres=%d)",
            self._model,
            len(text),
        )
        return text

    @staticmethod
    def _extract_text(response: Any) -> str:
        text = ""
        try:
            text = response.text or ""
        except (ValueError, AttributeError):
            text = ""

        if not text.strip():
            candidates = getattr(response, "candidates", None) or []
            parts: list[str] = []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", None) or []:
                    piece = getattr(part, "text", None)
                    if piece:
                        parts.append(piece)
            text = "".join(parts)

        if not text.strip():
            raise ProviderResponseError(
                "Gemini no devolvió texto. Puede que la solicitud haya sido "
                "bloqueada por los filtros de seguridad o que el modelo no esté disponible. "
                "Inténtalo de nuevo con otra pregunta."
            )
        return text.strip()
