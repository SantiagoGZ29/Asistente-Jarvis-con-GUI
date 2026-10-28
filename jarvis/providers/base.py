"""Interfaces comunes de los proveedores de IA."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Proveedor de generación de texto."""

    @property
    def model_name(self) -> str:  # pragma: no cover - definición de interfaz
        ...

    def complete(
        self,
        *,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.2,
        max_output_tokens: int = 1500,
    ) -> str:
        """Devuelve el texto generado para el mensaje indicado."""
        ...
