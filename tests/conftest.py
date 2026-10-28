"""Fixtures comunes de las pruebas de Mi Jarvis.

Todas las pruebas son locales: no usan claves reales ni permiten conexiones
de red (se bloquean explícitamente para detectar dependencias accidentales).
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from docx import Document

from jarvis.config import Settings


@pytest.fixture(autouse=True)
def block_network(request, monkeypatch):
    """Impide conexiones externas durante las pruebas unitarias.

    Se permite el bucle local: asyncio crea un ``socketpair`` interno en
    Windows para sus bucles de eventos y eso no es tráfico de red.
    """
    if request.node.get_closest_marker("integration"):
        yield
        return

    def is_loopback(address) -> bool:
        return (
            isinstance(address, tuple)
            and bool(address)
            and str(address[0]).lower() in {"127.0.0.1", "::1", "localhost"}
        )

    def guarded(original, index: int):
        def wrapper(*args, **kwargs):
            address = args[index] if len(args) > index else kwargs.get("address")
            if is_loopback(address):
                return original(*args, **kwargs)
            raise AssertionError(
                "Una prueba unitaria intentó abrir una conexión de red. "
                "Usa un proveedor simulado."
            )

        return wrapper

    monkeypatch.setattr(
        socket.socket, "connect", guarded(socket.socket.connect, 1)
    )
    monkeypatch.setattr(
        socket.socket, "connect_ex", guarded(socket.socket.connect_ex, 1)
    )
    monkeypatch.setattr(
        socket, "create_connection", guarded(socket.create_connection, 0)
    )
    yield


def create_sample_docx(path: Path) -> Path:
    """Crea un manual de ejemplo con títulos, párrafos y una tabla."""
    document = Document()
    document.core_properties.title = "Manual de Ejemplo"
    document.add_heading("Manual de Ejemplo", level=1)
    document.add_paragraph("Guía interna para el equipo de proyectos.")

    document.add_heading("Objetivo", level=2)
    document.add_paragraph(
        "El objetivo principal del manual es organizar el trabajo del equipo "
        "y reducir los errores en la entrega de informes."
    )

    document.add_heading("Responsabilidades", level=2)
    document.add_paragraph(
        "El coordinador debe revisar los plazos y asignar las tareas al equipo."
    )
    document.add_paragraph(
        "Los analistas preparan los informes mensuales y validan los datos."
    )

    document.add_heading("Fechas y plazos", level=2)
    document.add_paragraph(
        "La entrega final será el 15 de marzo de 2026."
    )
    document.add_paragraph(
        "El plazo de revisión vence el 28 de febrero de 2026."
    )

    document.add_heading("Tabla de tareas", level=2)
    table = document.add_table(rows=3, cols=3)
    headers = ("Tarea", "Responsable", "Fecha")
    for index, value in enumerate(headers):
        table.rows[0].cells[index].text = value
    table.rows[1].cells[0].text = "Preparar informe"
    table.rows[1].cells[1].text = "Ana"
    table.rows[1].cells[2].text = "10 de marzo de 2026"
    table.rows[2].cells[0].text = "Revisar informe"
    table.rows[2].cells[1].text = "Luis"
    table.rows[2].cells[2].text = "12 de marzo de 2026"

    document.add_heading("Conclusiones", level=2)
    document.add_paragraph(
        "El éxito del proyecto depende del seguimiento semanal y de la "
        "comunicación entre los responsables."
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    return path


def create_long_docx(path: Path, sections: int = 12) -> Path:
    """Crea un documento extenso para probar fragmentación y resúmenes."""
    document = Document()
    document.core_properties.title = "Documento extenso"
    document.add_heading("Documento extenso", level=1)
    for section in range(1, sections + 1):
        document.add_heading(f"Sección {section}", level=2)
        for paragraph in range(1, 5):
            document.add_paragraph(
                f"En la sección {section}, párrafo {paragraph}, se describe el "
                "procedimiento de trabajo con suficiente detalle para que el "
                "texto supere el tamaño de un fragmento y permita comprobar la "
                "fragmentación controlada del documento. También se mencionan "
                "responsables, fechas y acciones de seguimiento."
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    return path


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    return create_sample_docx(tmp_path / "manual.docx")


@pytest.fixture
def second_docx(tmp_path: Path) -> Path:
    document = Document()
    document.add_heading("Otro documento", level=1)
    document.add_paragraph("Este es un documento distinto para cambiar de archivo.")
    path = tmp_path / "otro.docx"
    document.save(str(path))
    return path


@pytest.fixture
def long_docx(tmp_path: Path) -> Path:
    return create_long_docx(tmp_path / "extenso.docx")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gemini_api_key="clave-simulada-de-prueba",
        gemini_model="modelo-simulado",
        elevenlabs_api_key="",
        elevenlabs_voice_id="",
        max_context_chars=3_000,
        max_batch_chars=1_500,
        chunk_size_chars=400,
        env_file=None,
    )


@pytest.fixture
def settings_with_voice() -> Settings:
    return Settings(
        gemini_api_key="clave-simulada-de-prueba",
        gemini_model="modelo-simulado",
        elevenlabs_api_key="clave-voz-simulada",
        elevenlabs_voice_id="voz-simulada",
        max_context_chars=3_000,
        max_batch_chars=1_500,
        chunk_size_chars=400,
        env_file=None,
    )


class FakeProvider:
    """Proveedor simulado: registra las llamadas y devuelve respuestas fijas."""

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses) or ["Respuesta simulada [P4]."]
        self.calls: list[dict] = []

    @property
    def model_name(self) -> str:
        return "modelo-simulado"

    def complete(
        self,
        *,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.2,
        max_output_tokens: int = 1500,
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "system_instruction": system_instruction,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            }
        )
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]

    @property
    def call_count(self) -> int:
        return len(self.calls)


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider("El objetivo del documento es organizar el trabajo [P4].")


@pytest.fixture
def make_fake_provider():
    return FakeProvider


class ScriptedInput:
    """Sustituye a input() con una lista de respuestas."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str = "") -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise EOFError
        return self.responses.pop(0)


@pytest.fixture
def scripted_input():
    return ScriptedInput
