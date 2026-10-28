"""Pruebas del controlador: turnos, micrófono, documentos y cierre."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from pathlib import Path

import pytest

from jarvis.assistants.document_assistant import AssistantAnswer, Source
from jarvis.audio.devices import InputDevice
from jarvis.config import Settings
from jarvis.core.consent import ConsentManager, ELEVENLABS_STT, GEMINI_CHAT
from jarvis.core.controller import (
    ChatMessage,
    Controller,
    ControllerCallbacks,
    DocumentInfo,
)
from jarvis.core.errors import AudioError
from jarvis.core.states import AssistantState, MicState
from jarvis.documents.downloads import (
    AMBIGUOUS,
    MATCH,
    DocumentMatch,
    DownloadsLibrary,
    SearchResult,
)


def wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def voice_settings(**overrides) -> Settings:
    base = Settings(
        gemini_api_key="clave-gemini-de-prueba",
        gemini_model="modelo-simulado",
        elevenlabs_api_key="clave-elevenlabs-de-prueba",
        elevenlabs_voice_id="voz-simulada",
        speak_responses=False,
        greeting_text="Hola, soy Jarvis de prueba.",
        env_file=None,
    )
    return replace(base, **overrides)


class FakeGemini:
    def __init__(self, reply: str = "Estoy bien, gracias por preguntar.") -> None:
        self.reply = reply
        self.calls: list[dict] = []

    def complete(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.reply


class FakeAssistant:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def _answer(self, text: str = "Respuesta fundamentada [P1].") -> AssistantAnswer:
        return AssistantAnswer(
            text=text,
            sources=(Source(ref="P1", heading="Objetivo"),),
        )

    def ask(self, question: str, *, top_k: int = 5) -> AssistantAnswer:
        self.calls.append(("ask", question))
        return self._answer()

    def summarize(self) -> AssistantAnswer:
        self.calls.append(("summarize",))
        return self._answer("Resumen del documento [P1].")

    def summarize_section(self, reference: str) -> AssistantAnswer:
        self.calls.append(("summarize_section", reference))
        return self._answer("Resumen de la sección [P2].")

    def explain(self, topic: str, *, detail: bool = False) -> AssistantAnswer:
        self.calls.append(("explain", topic, detail))
        return self._answer("Explicación sencilla [P3].")

    def extract(self, kind: str) -> AssistantAnswer:
        self.calls.append(("extract", kind))
        return self._answer(f"Extracción de {kind} [P4].")


class FakeCapture:
    def __init__(self, device: InputDevice, *, fail: Exception | None = None) -> None:
        self.device = device
        self.fail = fail
        self.is_running = False
        self.is_streaming = False
        self.suspended = False
        self.started = 0
        self.stopped = 0
        self.resets = 0
        self.on_level = None
        self.on_speech_start = None
        self.on_speech_end = None
        self.on_discard = None
        self.on_streaming = None
        self.on_error = None
        self.on_audio = None

    def start(self) -> None:
        if self.fail is not None:
            raise self.fail
        self.started += 1
        self.is_running = True
        self.is_streaming = True
        if self.on_streaming is not None:
            self.on_streaming()

    def stop(self) -> None:
        self.stopped += 1
        self.is_running = False
        self.is_streaming = False

    def suspend(self) -> None:
        self.suspended = True

    def resume(self) -> None:
        self.suspended = False

    def reset_utterance(self) -> None:
        self.resets += 1

    # -- ayudantes de prueba -------------------------------------------
    def begin_speech(self) -> None:
        if self.on_speech_start is not None:
            self.on_speech_start()

    def end_speech(self, segment: bytes = b"\x01\x00" * 320) -> None:
        if self.on_speech_end is not None:
            self.on_speech_end(segment, len(segment) / 2 / 16_000)

    def emit_level(self, level: float, speaking: bool = False) -> None:
        if self.on_level is not None:
            self.on_level(level, speaking)


class FakeTranscriber:
    def __init__(self) -> None:
        self.callbacks = None
        self.started = 0
        self.stopped = 0
        self.cancelled = 0
        self.commits: list[bytes] = []
        self.audio: list[bytes] = []
        self.mode = "realtime"

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def cancel(self) -> None:
        self.cancelled += 1

    def push_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    def commit(self, segment: bytes) -> None:
        self.commits.append(segment)

    # -- ayudantes de prueba -------------------------------------------
    def partial(self, text: str) -> None:
        self.callbacks.on_partial(text, 0)

    def final(self, text: str) -> None:
        self.callbacks.on_final(text, len(self.commits))


class FakeSpeech:
    def __init__(self, *, auto_finish: bool = False) -> None:
        self.callbacks = None
        self.auto_finish = auto_finish
        self.spoken: list[str] = []
        self.stopped = 0
        self.shutdown_called = False
        self._speaking = False

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def speak(self, text: str) -> bool:
        if self._speaking:
            return False
        self._speaking = True
        self.spoken.append(text)
        self.callbacks.on_started()
        self.callbacks.on_level(0.35)
        if self.auto_finish:
            self.finish()
        return True

    def finish(self) -> None:
        if not self._speaking:
            return
        self._speaking = False
        self.callbacks.on_level(0.0)
        self.callbacks.on_done()

    def stop(self) -> None:
        if not self._speaking:
            return
        self.stopped += 1
        self._speaking = False
        self.callbacks.on_done()

    def shutdown(self) -> None:
        self.stop()
        self.shutdown_called = True


class FakeDownloads:
    def __init__(self, result: SearchResult, opened: list[Path]) -> None:
        self.result = result
        self.opened = opened
        self.queries: list[str | None] = []

    def search(self, query: str | None) -> SearchResult:
        self.queries.append(query)
        return self.result

    def open_document(self, path: Path | str) -> Path:
        target = Path(path)
        self.opened.append(target)
        return target


class Recorder:
    def __init__(self) -> None:
        self.states: list[tuple[AssistantState, AssistantState, str]] = []
        self.mics: list[tuple[MicState, str]] = []
        self.messages: list[ChatMessage] = []
        self.notices: list[str] = []
        self.errors: list[str] = []
        self.partials: list[str] = []
        self.user_levels: list[float] = []
        self.jarvis_levels: list[float] = []
        self.health: list[dict] = []
        self.documents: list[DocumentInfo | None] = []
        self.choices: list[tuple[str, ...]] = []
        self.mic_tests: list[dict] = []
        self.picked = 0
        self.exits = 0

    def callbacks(self) -> ControllerCallbacks:
        return ControllerCallbacks(
            on_state=lambda old, new, reason: self.states.append((old, new, reason)),
            on_mic=lambda state, detail: self.mics.append((state, detail)),
            on_message=self.messages.append,
            on_notice=self.notices.append,
            on_error=self.errors.append,
            on_partial=self.partials.append,
            on_user_level=self.user_levels.append,
            on_jarvis_level=self.jarvis_levels.append,
            on_health=self.health.append,
            on_document=self.documents.append,
            on_choices=self.choices.append,
            on_pick_document=self._count_pick,
            on_exit=self._count_exit,
            on_mic_test=self.mic_tests.append,
        )

    def _count_pick(self) -> None:
        self.picked += 1

    def _count_exit(self) -> None:
        self.exits += 1

    @property
    def jarvis_texts(self) -> list[str]:
        return [message.text for message in self.messages if message.role == "jarvis"]

    @property
    def user_texts(self) -> list[str]:
        return [message.text for message in self.messages if message.role == "user"]


class Harness:
    """Controlador con todos los dobles conectados."""

    def __init__(
        self,
        settings: Settings,
        tmp_path: Path,
        *,
        downloads=None,
        capture: FakeCapture | None = None,
        auto_finish_speech: bool = False,
        consent: ConsentManager | None = None,
        provider=None,
    ) -> None:
        self.settings = settings
        self.rec = Recorder()
        self.device = InputDevice(
            index=1,
            name="Micrófono de prueba",
            hostapi="MME",
            channels=1,
            default_samplerate=48_000,
            is_default=True,
        )
        self.capture = capture or FakeCapture(self.device)
        self.transcriber = FakeTranscriber()
        self.speech = FakeSpeech(auto_finish=auto_finish_speech)
        self.assistant = FakeAssistant()
        self.provider = provider or FakeGemini()
        self.opened: list[Path] = []
        self.downloads = downloads or DownloadsLibrary(
            root=tmp_path, opener=self.opened.append
        )
        self.consent = consent or ConsentManager(lambda request: True, enabled=False)

        def make_transcriber(callbacks):
            self.transcriber.callbacks = callbacks
            return self.transcriber

        def make_speech(callbacks):
            self.speech.callbacks = callbacks
            return self.speech

        self.controller = Controller(
            settings,
            callbacks=self.rec.callbacks(),
            consent=self.consent,
            provider=self.provider,
            capture_factory=lambda device: self.capture,
            transcriber_factory=make_transcriber,
            speech_factory=make_speech,
            assistant_factory=lambda document, chunks: self.assistant,
            downloads=self.downloads,
            devices_provider=lambda: (self.device,),
            greet_on_start=False,
        )

    def start(self) -> "Harness":
        self.controller.start()
        assert self.controller.wait_for_idle(3.0)
        return self

    def stop(self) -> None:
        self.controller.shutdown()

    def send(self, text: str) -> None:
        self.controller.send_text(text)
        assert self.controller.wait_for_idle(3.0)

    def speak(self, text: str = "hola Jarvis", segment: bytes = b"\x01\x00" * 320):
        self.capture.begin_speech()
        self.capture.end_speech(segment)
        self.transcriber.final(text)
        assert self.controller.wait_for_idle(3.0)

    def last_state(self) -> AssistantState:
        return self.controller.state


@pytest.fixture
def harness(tmp_path: Path):
    created: list[Harness] = []

    def build(settings: Settings | None = None, **kwargs) -> Harness:
        item = Harness(settings or voice_settings(), tmp_path, **kwargs)
        created.append(item)
        return item

    yield build
    for item in created:
        item.stop()


# ======================================================================
# Arranque y estados
# ======================================================================
def test_arranca_sin_claves_y_permite_texto(harness, tmp_path: Path) -> None:
    settings = Settings(env_file=None, speak_responses=False)
    item = harness(settings).start()

    assert item.last_state() is AssistantState.READY
    assert item.controller.mic_state is MicState.UNAVAILABLE
    assert any("ELEVENLABS_API_KEY" in notice for notice in item.rec.notices)

    item.send("hola")
    assert item.rec.user_texts == ["hola"]
    assert item.rec.jarvis_texts
    assert "Hola" in item.rec.jarvis_texts[-1]
    assert item.last_state() is AssistantState.READY

    health = item.controller.attachments()
    assert health["gemini"] == "no configurado"
    assert health["voice"] == "no configurada"


def test_arranque_con_microfono_queda_escuchando(harness) -> None:
    item = harness().start()

    assert item.last_state() is AssistantState.LISTENING
    assert item.controller.mic_state in {MicState.STREAMING, MicState.DETECTED}
    assert item.transcriber.started == 1
    assert item.capture.started == 1
    assert any(mic is MicState.STREAMING for mic, _ in item.rec.mics)


def test_autoescucha_desactivada_no_abre_el_microfono(harness) -> None:
    item = harness(voice_settings(auto_listen=False)).start()

    assert item.last_state() is AssistantState.PAUSED
    assert item.controller.mic_state is MicState.DETECTED
    assert item.capture.started == 0
    assert item.transcriber.started == 0

    item.controller.resume_mic()
    assert item.controller.wait_for_idle(3.0)

    assert item.capture.started == 1
    assert item.last_state() is AssistantState.LISTENING


def test_transiciones_no_contradicen_el_microfono(harness) -> None:
    item = harness().start()
    item.capture.begin_speech()
    assert item.last_state() is AssistantState.USER_SPEAKING
    assert item.controller.mic_state is MicState.SPEECH

    item.capture.end_speech()
    assert item.last_state() is AssistantState.PROCESSING

    item.transcriber.final("hola")
    assert item.controller.wait_for_idle(3.0)
    assert item.last_state() is AssistantState.LISTENING

    previous = None
    for old, new, _reason in item.rec.states:
        assert old is previous or previous is None
        previous = new


def test_saludo_inicial_se_muestra_y_se_habla(harness) -> None:
    settings = voice_settings(speak_responses=True)
    item = harness(settings, auto_finish_speech=False)
    item.controller.callbacks = item.rec.callbacks()
    item.controller._greet_on_start = True
    item.start()

    assert item.rec.jarvis_texts[0] == settings.greeting_text
    assert item.last_state() is AssistantState.JARVIS_SPEAKING
    assert item.speech.spoken == [settings.greeting_text]
    assert item.capture.suspended is True

    item.speech.finish()
    assert item.last_state() is AssistantState.LISTENING
    assert item.capture.suspended is False


def test_fallo_de_microfono_no_impide_escribir(tmp_path: Path, harness) -> None:
    broken = FakeCapture(
        InputDevice(1, "Micrófono roto", "MME", 1, 48_000, True),
        fail=AudioError("Windows no permite acceder al micrófono de prueba."),
    )
    item = harness(capture=broken).start()

    assert item.controller.mic_state is MicState.ERROR
    assert item.last_state() is AssistantState.READY
    assert any("no permite acceder" in error for error in item.rec.errors)

    item.send("hola")
    assert "Hola" in item.rec.jarvis_texts[-1]
    assert item.last_state() is AssistantState.READY


# ======================================================================
# Voz
# ======================================================================
def test_frase_hablada_produce_un_turno(harness) -> None:
    item = harness().start()

    item.capture.begin_speech()
    item.transcriber.partial("ho")
    assert item.rec.partials[-1] == "ho"
    item.capture.end_speech()
    assert len(item.transcriber.commits) == 1

    item.transcriber.final("Hola Jarvis")
    assert item.controller.wait_for_idle(3.0)

    assert item.rec.user_texts == ["Hola Jarvis"]
    assert item.rec.jarvis_texts
    assert item.last_state() is AssistantState.LISTENING


def test_audio_se_reenvia_al_transcriptor_solo_activo(harness) -> None:
    item = harness().start()
    item.capture.on_audio(b"\x01\x02")
    assert item.transcriber.audio == [b"\x01\x02"]

    item.controller.pause_mic()
    assert item.controller.wait_for_idle(2.0)
    item.capture.on_audio(b"\x03\x04")
    assert item.transcriber.audio == [b"\x01\x02"]


def test_pausa_y_reanudacion_explicitas(harness) -> None:
    item = harness().start()

    item.controller.pause_mic()
    assert item.controller.wait_for_idle(2.0)
    assert item.last_state() is AssistantState.PAUSED
    assert item.controller.mic_state is MicState.MUTED
    assert item.capture.suspended is True
    assert item.transcriber.cancelled >= 1

    item.send("hola")
    assert item.last_state() is AssistantState.PAUSED
    assert "Hola" in item.rec.jarvis_texts[-1]

    item.controller.resume_mic()
    assert item.controller.wait_for_idle(2.0)
    assert item.last_state() is AssistantState.LISTENING
    assert item.capture.suspended is False


def test_detener_la_voz_desde_el_texto(harness) -> None:
    settings = voice_settings(speak_responses=True)
    item = harness(settings, auto_finish_speech=False).start()
    item.send("hola")

    assert item.last_state() is AssistantState.JARVIS_SPEAKING
    assert item.speech.is_speaking is True
    assert item.capture.suspended is True
    assert max(item.rec.jarvis_levels) >= 0.3

    item.send("detente")
    assert item.last_state() is AssistantState.LISTENING
    assert item.speech.stopped == 1
    assert item.rec.jarvis_levels[-1] == 0.0
    assert item.capture.suspended is False


def test_boton_detener_voz(harness) -> None:
    settings = voice_settings(speak_responses=True)
    item = harness(settings, auto_finish_speech=False).start()
    item.send("hola")
    assert item.speech.is_speaking

    item.controller.stop_speech()
    assert item.controller.wait_for_idle(2.0)

    assert item.speech.is_speaking is False
    assert item.last_state() is AssistantState.LISTENING


def test_la_respuesta_no_se_escucha_a_si_misma(harness) -> None:
    settings = voice_settings(speak_responses=True)
    item = harness(settings, auto_finish_speech=False).start()
    item.send("hola")
    assert item.last_state() is AssistantState.JARVIS_SPEAKING

    # Mientras habla, el audio del micrófono no se transcribe.
    audio_before = len(item.transcriber.audio)
    item.capture.on_audio(b"\x05\x06")
    assert len(item.transcriber.audio) == audio_before

    item.speech.finish()
    assert item.last_state() is AssistantState.LISTENING
    item.capture.on_audio(b"\x07\x08")
    assert len(item.transcriber.audio) == audio_before + 1


def test_texto_duplicado_no_se_procesa_dos_veces(harness) -> None:
    item = harness().start()

    item.controller.send_text("hola")
    item.controller.send_text("hola")
    assert item.controller.wait_for_idle(3.0)

    assert item.rec.user_texts == ["hola"]


def test_final_de_voz_repetido_se_descarta(harness) -> None:
    item = harness().start()
    item.capture.end_speech()
    item.transcriber.final("Hola Jarvis")
    item.transcriber.final("Hola Jarvis")
    assert item.controller.wait_for_idle(3.0)

    assert item.rec.user_texts == ["Hola Jarvis"]


# ======================================================================
# Documentos
# ======================================================================
def test_abrir_documento_de_descargas_por_voz(
    harness, sample_docx: Path, tmp_path: Path
) -> None:
    item = harness().start()

    item.send("abre el documento manual de descargas")

    assert item.opened == [sample_docx]
    assert item.controller.document is not None
    assert item.controller.document.path.name == "manual.docx"
    assert isinstance(item.rec.documents[-1], DocumentInfo)
    assert item.rec.documents[-1].opened is True
    assert "He abierto y cargado" in item.rec.jarvis_texts[-1]
    assert item.last_state() is AssistantState.LISTENING


def test_coincidencia_clara_no_pregunta(
    harness, sample_docx: Path, tmp_path: Path
) -> None:
    result = SearchResult(
        query="manual",
        root=tmp_path,
        matches=(DocumentMatch(sample_docx, 0.99, "manual.docx"),),
        decision=MATCH,
    )
    item = harness(downloads=FakeDownloads(result, [])).start()

    item.send("abre el manual")

    assert item.rec.choices[-1] == ()
    assert "manual.docx" in item.rec.jarvis_texts[-1]
    assert not any("varios documentos" in text for text in item.rec.jarvis_texts)


def test_ambiguedad_pregunta_y_no_elige_sola(
    harness, sample_docx: Path, second_docx: Path, tmp_path: Path
) -> None:
    matches = (
        DocumentMatch(sample_docx, 0.72, "manual.docx"),
        DocumentMatch(second_docx, 0.70, "otro.docx"),
    )
    result = SearchResult(
        query="documento", root=tmp_path, matches=matches, decision=AMBIGUOUS
    )
    opened: list[Path] = []
    item = harness(downloads=FakeDownloads(result, opened)).start()

    item.send("abre el documento")

    assert opened == []
    assert item.rec.choices[-1] == ("manual", "otro")
    assert "¿Cuál quieres abrir?" in item.rec.jarvis_texts[-1]

    item.controller.choose_candidate(1)
    assert item.controller.wait_for_idle(3.0)

    assert opened == [second_docx]
    assert item.rec.choices[-1] == ()
    assert item.controller.document is not None
    assert item.controller.document.path.name == "otro.docx"


def test_ambiguedad_se_puede_resolver_hablando(
    harness, sample_docx: Path, second_docx: Path, tmp_path: Path
) -> None:
    matches = (
        DocumentMatch(sample_docx, 0.72, "manual.docx"),
        DocumentMatch(second_docx, 0.70, "otro.docx"),
    )
    item = harness(
        downloads=FakeDownloads(
            SearchResult(
                query="documento", root=tmp_path, matches=matches, decision=AMBIGUOUS
            ),
            [],
        )
    ).start()
    item.send("abre el documento")
    assert item.rec.choices[-1]

    item.send("el segundo")

    assert item.controller.document is not None
    assert item.controller.document.path.name == "otro.docx"


def test_documento_cargado_responde_preguntas(
    harness, sample_docx: Path
) -> None:
    item = harness().start()
    item.controller.load_document(sample_docx)
    assert item.controller.wait_for_idle(3.0)
    assert item.rec.documents[-1].name == "manual.docx"

    item.send("¿Qué responsabilidades tiene el equipo?")
    assert ("ask", "¿Qué responsabilidades tiene el equipo?") in item.assistant.calls
    answer = item.rec.messages[-1]
    assert answer.role == "jarvis"
    assert "Respuesta fundamentada" in answer.text
    assert answer.sources == ("Objetivo (P1)",)

    item.send("resume el documento")
    assert ("summarize",) in item.assistant.calls
    assert "Resumen del documento" in item.rec.jarvis_texts[-1]

    item.send("extrae las fechas")
    assert ("extract", "fechas") in item.assistant.calls


def test_conversacion_sin_gemini_explica_el_fallo(harness) -> None:
    settings = Settings(env_file=None, speak_responses=False)
    item = harness(settings).start()

    item.send("cuéntame algo interesante")

    assert "GEMINI_API_KEY" in item.rec.jarvis_texts[-1]
    assert item.provider.calls == []


def test_pregunta_sin_documento_usa_chat(harness) -> None:
    item = harness().start()

    item.send("¿cómo estás?")

    assert item.provider.calls
    assert "Estoy bien" in item.rec.jarvis_texts[-1]
    assert item.last_state() is AssistantState.LISTENING


def test_resumen_sin_documento_avisa(harness) -> None:
    item = harness().start()

    item.send("resume el documento")

    assert "No hay ningún documento cargado" in item.rec.jarvis_texts[-1]
    assert not any(call[0] == "summarize" for call in item.assistant.calls)


def test_historial_de_chat_es_acotado(harness) -> None:
    item = harness().start()
    for index in range(10):
        item.send(f"mensaje número {index}")

    prompt = item.provider.calls[-1]["prompt"]
    history = prompt.split("MENSAJE DEL USUARIO:")[0]
    assert "mensaje número 0" not in history
    assert "mensaje número 3" not in history
    assert "mensaje número 9" in prompt  # mensaje actual
    assert history.count("Usuario:") <= 6
    assert len(prompt) < 5_000


def test_consentimiento_denegado_no_envia_chat(tmp_path: Path) -> None:
    denials: list[str] = []

    def ask(request) -> bool:
        denials.append(request.key)
        return False

    consent = ConsentManager(ask)
    item = Harness(voice_settings(), tmp_path, consent=consent)
    item.start()

    assert item.controller.mic_state is MicState.UNAVAILABLE
    item.send("¿cómo estás?")

    assert item.provider.calls == []
    assert "No diste permiso" in item.rec.jarvis_texts[-1]
    assert GEMINI_CHAT.key in denials
    assert ELEVENLABS_STT.key in denials


# ======================================================================
# Micrófono: prueba y cambio de dispositivo
# ======================================================================
def test_prueba_de_microfono_mide_nivel_real(harness) -> None:
    item = harness().start()

    item.controller.test_microphone(0.15)
    time.sleep(0.03)
    item.capture.emit_level(0.42, True)
    assert item.controller.wait_for_idle(2.0)

    result = item.rec.mic_tests[-1]
    assert result["ok"] is True
    assert result["peak"] == pytest.approx(0.42)
    assert "funciona" in result["message"]


def test_prueba_de_microfono_sin_audio(harness) -> None:
    item = harness().start()
    item.controller.test_microphone(0.05)
    assert item.controller.wait_for_idle(2.0)

    result = item.rec.mic_tests[-1]
    assert result["ok"] is False
    assert "No se detectó voz" in result["message"]


def test_cambio_de_dispositivo_reabre_el_microfono(harness) -> None:
    item = harness().start()
    assert item.capture.started == 1

    item.controller.select_device("MME|Micrófono de prueba|1")
    assert item.controller.wait_for_idle(3.0)

    assert item.capture.started == 2
    assert item.capture.stopped == 1
    assert item.transcriber.started == 2
    assert item.last_state() is AssistantState.LISTENING


# ======================================================================
# Cierre y secretos
# ======================================================================
def test_cierre_deja_todo_el_audio_cerrado(harness) -> None:
    settings = voice_settings(speak_responses=True)
    item = harness(settings, auto_finish_speech=False)
    item.start()
    item.send("hola")
    assert item.speech.is_speaking

    item.controller.shutdown()

    assert item.controller.is_running is False
    assert item.capture.is_running is False
    assert item.capture.stopped >= 1
    assert item.transcriber.stopped >= 1
    assert item.speech.shutdown_called is True
    assert item.speech.is_speaking is False


def test_cierre_es_idempotente(harness) -> None:
    item = harness().start()
    item.controller.shutdown()
    item.controller.shutdown()
    assert item.controller.is_running is False


def test_no_se_registran_claves(harness, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    item = harness().start()
    item.send("hola")
    item.send("¿cómo estás?")
    item.stop()

    assert "clave-gemini-de-prueba" not in caplog.text
    assert "clave-elevenlabs-de-prueba" not in caplog.text
    health = str(item.controller.attachments())
    assert "clave-gemini-de-prueba" not in health
    assert "clave-elevenlabs-de-prueba" not in health


def test_atajo_para_elegir_documento(harness) -> None:
    item = harness().start()
    item.send("quiero otro documento")

    assert item.rec.picked == 1
    assert "ventana" in item.rec.jarvis_texts[-1]


def test_salir_avisa_a_la_interfaz(harness) -> None:
    item = harness().start()
    item.send("salir")

    assert item.rec.exits == 1
    assert item.rec.jarvis_texts[-1] == "Hasta luego."


def test_niveles_de_usuario_llegan_a_la_interfaz(harness) -> None:
    item = harness().start()
    item.capture.emit_level(0.25, False)

    assert 0.25 in item.rec.user_levels
    assert any(report["state"] == "LISTENING" for report in item.rec.health)


def test_orden_desconocida_se_conversa(harness) -> None:
    item = harness().start()
    item.send("xyzzy plugh")

    assert item.provider.calls
    assert item.rec.jarvis_texts[-1] == item.provider.reply
