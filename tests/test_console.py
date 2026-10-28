"""Pruebas de la interfaz de consola en modo texto y voz."""

from __future__ import annotations

from pathlib import Path

from jarvis.assistants.document_assistant import DocumentAssistant
from jarvis.core.consent import ConsentManager
from jarvis.core.errors import ProviderRateLimitError
from jarvis.documents.docx_loader import load_document
from jarvis.ui.console import ConsoleApp


class RateLimitedProvider:
    @property
    def model_name(self) -> str:
        return "modelo-limitado"

    def complete(self, **kwargs) -> str:
        raise ProviderRateLimitError(
            "Se alcanzó el límite de uso del servicio. Espera a que la cuota "
            "se restablezca."
        )


class FakeRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.started = False
        self.cancelled = False

    def is_available(self) -> bool:
        return True

    def start(self) -> None:
        self.started = True

    def stop(self) -> Path:
        return self.path

    def cancel(self) -> None:
        self.cancelled = True


class FakeVoice:
    def __init__(self, transcript: str = "resumen del documento") -> None:
        self.transcript = transcript
        self.spoken: list[str] = []
        self.transcribed: list[Path] = []

    def transcribe(self, path: Path) -> str:
        self.transcribed.append(path)
        return self.transcript

    def speak(self, text: str) -> None:
        self.spoken.append(text)


def _output() -> tuple[list[str], callable]:
    lines: list[str] = []
    return lines, lines.append


def test_modo_texto_funciona_sin_voz(
    settings, sample_docx, make_fake_provider, scripted_input
) -> None:
    lines, output = _output()
    script = scripted_input(["resumen", "salir"])
    app = ConsoleApp(
        settings,
        input_fn=script,
        output_fn=output,
        provider=make_fake_provider("Resumen simulado del documento [P4]."),
        consent=ConsentManager(lambda request: True),
        document=load_document(sample_docx),
    )

    app.run(select_on_start=False)

    text = "\n".join(lines)
    assert "Resumen general:" in text
    assert "Fuentes consultadas:" in text
    assert "Hasta luego" in text
    assert app.mode == "texto"


def test_pregunta_libre_en_modo_texto(
    settings, sample_docx, make_fake_provider
) -> None:
    lines, output = _output()
    app = ConsoleApp(
        settings,
        input_fn=lambda prompt="": "",
        output_fn=output,
        provider=make_fake_provider("El objetivo es organizar el trabajo [P4]."),
        consent=ConsentManager(lambda request: True),
        document=load_document(sample_docx),
    )

    app.handle("¿Cuál es el objetivo principal?")

    text = "\n".join(lines)
    assert "organizar el trabajo" in text
    assert "Objetivo" in text


def test_modo_voz_sin_clave_muestra_ayuda_y_sigue_en_texto(
    settings, sample_docx, fake_provider
) -> None:
    lines, output = _output()
    app = ConsoleApp(
        settings,
        input_fn=lambda prompt="": "",
        output_fn=output,
        provider=fake_provider,
        document=load_document(sample_docx),
    )

    app.handle("modo voz")

    text = "\n".join(lines)
    assert "ELEVENLABS_API_KEY" in text
    assert app.mode == "texto"


def test_limite_de_uso_se_informa_y_la_sesion_continua(
    settings, sample_docx
) -> None:
    lines, output = _output()
    app = ConsoleApp(
        settings,
        input_fn=lambda prompt="": "",
        output_fn=output,
        provider=RateLimitedProvider(),
        consent=ConsentManager(lambda request: True),
        document=load_document(sample_docx),
    )

    app.handle("resumen")
    app.handle("ayuda")

    text = "\n".join(lines)
    assert "límite de uso" in text.lower()
    assert "Opciones disponibles" in text


def test_sin_documento_pide_seleccionar_uno(settings, fake_provider) -> None:
    lines, output = _output()
    app = ConsoleApp(
        settings,
        input_fn=lambda prompt="": "",
        output_fn=output,
        provider=fake_provider,
    )

    app.handle("resumen")

    text = "\n".join(lines).lower()
    assert "todavia no hay un documento" in text or "todavía no hay un documento" in text


def test_cambiar_de_documento(
    settings, sample_docx, second_docx, fake_provider
) -> None:
    lines, output = _output()
    app = ConsoleApp(
        settings,
        input_fn=lambda prompt="": "",
        output_fn=output,
        provider=fake_provider,
        file_picker=lambda: second_docx,
        document=load_document(sample_docx),
    )

    assert app.select_document() is True
    assert app.document is not None
    assert app.document.path == second_docx
    assert "Otro documento" in "\n".join(lines)


def test_consentimiento_denegado_no_envia_documento(
    settings, sample_docx, make_fake_provider
) -> None:
    lines, output = _output()
    provider = make_fake_provider("No debería usarse.")
    app = ConsoleApp(
        settings,
        input_fn=lambda prompt="": "",
        output_fn=output,
        provider=provider,
        consent=ConsentManager(lambda request: False),
        document=load_document(sample_docx),
    )

    app.handle("resumen")

    text = "\n".join(lines).lower()
    assert "consentimiento" in text
    assert provider.call_count == 0


def test_flujo_de_voz_transcribe_permite_corregir_y_limpia_el_audio(
    settings_with_voice, sample_docx, make_fake_provider, tmp_path, scripted_input
) -> None:
    audio = tmp_path / "grabacion.wav"
    audio.write_bytes(b"RIFF" * 20)
    recorder = FakeRecorder(audio)
    voice = FakeVoice()
    lines, output = _output()
    script = scripted_input(["", "", ""])

    app = ConsoleApp(
        settings_with_voice,
        input_fn=script,
        output_fn=output,
        provider=make_fake_provider("Resumen hablado [P4]."),
        voice=voice,
        recorder=recorder,
        consent=ConsentManager(lambda request: True),
        document=load_document(sample_docx),
    )
    app.handle("modo voz")
    assert app.mode == "voz"

    text, from_voice = app._read()

    assert text == "resumen del documento"
    assert from_voice is True
    assert recorder.started is True
    assert voice.transcribed and not audio.exists()
    body = "\n".join(lines)
    assert "Transcripcion" in body or "Transcripción" in body

    app.handle(text)
    assert voice.spoken
    assert "Resumen" in voice.spoken[0]


def test_la_transcripcion_se_puede_corregir(
    settings_with_voice, sample_docx, make_fake_provider, tmp_path, scripted_input
) -> None:
    audio = tmp_path / "grabacion.wav"
    audio.write_bytes(b"RIFF" * 20)
    voice = FakeVoice("resumen del documento")
    lines, output = _output()
    script = scripted_input(["", "", "resumen de la seccion 2"])

    app = ConsoleApp(
        settings_with_voice,
        input_fn=script,
        output_fn=output,
        provider=make_fake_provider("Resumen [P4]."),
        voice=voice,
        recorder=FakeRecorder(audio),
        consent=ConsentManager(lambda request: True),
        document=load_document(sample_docx),
    )
    app.handle("modo voz")

    text, from_voice = app._read()

    assert text == "resumen de la seccion 2"
    assert from_voice is True


def test_la_respuesta_no_se_lee_en_modo_texto(
    settings_with_voice, sample_docx, make_fake_provider
) -> None:
    voice = FakeVoice()
    app = ConsoleApp(
        settings_with_voice,
        input_fn=lambda prompt="": "",
        output_fn=lambda message="": None,
        provider=make_fake_provider("Resumen [P4]."),
        voice=voice,
        consent=ConsentManager(lambda request: True),
        document=load_document(sample_docx),
    )

    app.handle("resumen")

    assert voice.spoken == []


def test_el_asistente_reutiliza_el_documento_cargado(
    settings, sample_docx, fake_provider
) -> None:
    app = ConsoleApp(
        settings,
        input_fn=lambda prompt="": "",
        output_fn=lambda message="": None,
        provider=fake_provider,
        document=load_document(sample_docx),
    )

    assistant = app._ensure_assistant()
    assert isinstance(assistant, DocumentAssistant)
    assert app._ensure_assistant() is assistant
