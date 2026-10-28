"""Interfaz de consola de Mi Jarvis."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from jarvis import __app_name__, __version__
from jarvis.assistants.document_assistant import AssistantAnswer, DocumentAssistant
from jarvis.audio.recorder import AudioRecorder
from jarvis.config import Settings
from jarvis.core import intents
from jarvis.core.consent import (
    ELEVENLABS_STT,
    ELEVENLABS_TTS,
    ConsentManager,
    ConsentRequest,
)
from jarvis.core.errors import (
    AudioError,
    DocumentError,
    JarvisError,
)
from jarvis.core.logging_setup import get_logger
from jarvis.documents.chunker import Chunk, chunk_document
from jarvis.documents.docx_loader import load_document
from jarvis.documents.models import DocumentModel
from jarvis.providers.elevenlabs_provider import ElevenLabsProvider
from jarvis.providers.gemini_provider import GeminiProvider

logger = get_logger("console")

_SEPARATOR = "=" * 64
_EXTRACT_LABELS = {
    intents.EXTRACT_DATES: "Fechas y plazos",
    intents.EXTRACT_ACTIONS: "Acciones y tareas pendientes",
    intents.EXTRACT_RESPONSIBILITIES: "Responsabilidades",
    intents.EXTRACT_CONCLUSIONS: "Conclusiones",
}
_EXTRACT_KINDS = {
    intents.EXTRACT_DATES: "fechas",
    intents.EXTRACT_ACTIONS: "acciones",
    intents.EXTRACT_RESPONSIBILITIES: "responsabilidades",
    intents.EXTRACT_CONCLUSIONS: "conclusiones",
}
_CITATION_FOR_SPEECH_RE = re.compile(r"\[(?:P|T)\d+\]")
_MARKDOWN_FOR_SPEECH_RE = re.compile(r"[*_#>`]")

WELCOME = f"""{_SEPARATOR}
  {__app_name__} - version {__version__}
  Asistente documental en espanol (voz y texto)
{_SEPARATOR}

Puedo leer un documento de Microsoft Word (.docx) y responder preguntas
sobre su contenido, resumirlo, explicarte un apartado y extraer datos.

Aviso de privacidad:
  - El texto del documento se envia a Google Gemini solo cuando haces una
    pregunta o pides un analisis. Te pedire permiso la primera vez.
  - El audio del microfono se envia a ElevenLabs solo cuando grabas. Tambien
    te pedire permiso antes del primer envio.
  - Con el nivel gratuito de Gemini, Google puede usar el contenido enviado
    para mejorar sus productos: no uses documentos confidenciales.
  - Las claves se leen del archivo .env y nunca se muestran en pantalla.

Escribe 'ayuda' para ver las opciones o 'salir' para terminar.
"""

HELP_TEXT = """Opciones disponibles (puedes escribirlas o decirlas con naturalidad):

  - documento                  Cambiar o seleccionar un archivo .docx
  - resumen                    Resumen general del documento
  - resumen de la seccion 2    Resumen de una seccion concreta
  - explica el objetivo        Explicacion breve en lenguaje sencillo
  - fechas                     Extraer fechas y plazos
  - acciones                   Extraer tareas y acciones pendientes
  - responsabilidades          Extraer responsabilidades
  - conclusiones               Extraer conclusiones
  - modo voz                   Activar el microfono (pulsa Enter para hablar)
  - modo texto                 Desactivar el microfono y escribir siempre
  - ayuda                      Mostrar esta ayuda
  - salir                      Cerrar Jarvis

Tambien puedes preguntar libremente, por ejemplo:
  "Que debo hacer primero segun este manual?"
  "En que seccion aparece la informacion sobre plazos?"
  "Explicame este apartado como si estuviera aprendiendo."
"""


class ConsoleApp:
    """Bucle de consola con modos de voz y texto."""

    def __init__(
        self,
        settings: Settings,
        *,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
        provider=None,
        voice=None,
        recorder: AudioRecorder | None = None,
        file_picker: Callable[[], Path | None] | None = None,
        consent: ConsentManager | None = None,
        document: DocumentModel | None = None,
    ) -> None:
        self.settings = settings
        self._input: Callable[[str], str] = input_fn or input
        self._output: Callable[[str], None] = output_fn or print
        self._provider = provider
        self._voice = voice
        self._recorder = recorder
        self._file_picker = file_picker

        self._consent = consent or ConsentManager(self._ask_consent)
        self._mode = "texto"
        self._exit = False
        self._warned_no_tts = False

        self._document: DocumentModel | None = None
        self._chunks: tuple[Chunk, ...] = ()
        self._assistant: DocumentAssistant | None = None
        if document is not None:
            self._set_document(document)

    # ------------------------------------------------------------------
    # Salida y entrada
    # ------------------------------------------------------------------
    def _out(self, message: str = "") -> None:
        self._output(message)

    def _ask_consent(self, request: ConsentRequest) -> bool:
        self._out("")
        self._out(_SEPARATOR)
        self._out(f"Consentimiento para {request.provider}")
        self._out(_SEPARATOR)
        for line in request.description.splitlines():
            self._out(line)
        self._out("")
        try:
            answer = self._input("¿Aceptas el envio de estos datos? [s/N]: ").strip().lower()
        except EOFError:
            answer = ""
        accepted = answer in {"s", "si", "sí", "y", "yes"}
        self._out(
            "Consentimiento aceptado."
            if accepted
            else "Consentimiento rechazado: no se enviaran datos."
        )
        if not accepted:
            self._out(
                "Puedes seguir usando el modo texto y las funciones locales. "
                "Si cambias de opinion, reinicia Jarvis."
            )
        return accepted

    # ------------------------------------------------------------------
    # Documento
    # ------------------------------------------------------------------
    @property
    def document(self) -> DocumentModel | None:
        return self._document

    @property
    def mode(self) -> str:
        return self._mode

    def _set_document(self, document: DocumentModel) -> None:
        self._document = document
        self._chunks = chunk_document(
            document, max_chars=self.settings.chunk_size_chars
        )
        self._assistant = None

    def load_document_file(self, path: str | Path) -> bool:
        """Carga un .docx y muestra un resumen de su estructura."""
        try:
            document = load_document(path)
        except DocumentError as exc:
            self._out(f"\n[Jarvis] {exc.user_message}")
            return False

        self._set_document(document)
        self._out("")
        self._out(f"Documento cargado: {document.path.name}")
        self._out(f"  Titulo: {document.title}")
        self._out(
            f"  Parrafos: {len(document.paragraphs)} | "
            f"Tablas: {len(document.tables)} | "
            f"Encabezados: {len(document.sections)} | "
            f"Caracteres: {document.char_count}"
        )
        if document.tables:
            rows = sum(table.row_count for table in document.tables)
            self._out(f"  Filas de tabla extraidas: {rows}")
        for warning in document.warnings:
            self._out(f"  Aviso: {warning}")
        if document.sections:
            self._out("  Secciones detectadas:")
            for section in document.sections[:10]:
                self._out(f"    {section.number}. {section.label}")
            if len(document.sections) > 10:
                self._out(f"    ... y {len(document.sections) - 10} mas")
        if not self.settings.gemini_configured:
            self._out(
                "  Nota: falta GEMINI_API_KEY, asi que las preguntas con IA no "
                "estaran disponibles hasta que configures el archivo .env."
            )
        self._out("")
        self._out("Ya puedes preguntar sobre el documento.")
        logger.info(
            "Documento activo: %s (%d fragmentos)",
            document.path.name,
            len(self._chunks),
        )
        return True

    def _pick_document(self) -> Path | None:
        if self._file_picker is not None:
            return self._file_picker()

        dialog_worked = False
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:  # pragma: no cover - segun el gestor de ventanas
                pass
            selected = filedialog.askopenfilename(
                title="Selecciona un documento de Word",
                filetypes=[("Documentos de Word", "*.docx")],
            )
            root.destroy()
            dialog_worked = True
            return Path(selected) if selected else None
        except Exception:
            logger.warning(
                "El selector grafico no esta disponible; se pedira la ruta por teclado"
            )

        if dialog_worked:  # pragma: no cover - cubierto por la rama anterior
            return None

        manual = self._input(
            "Escribe la ruta completa del archivo .docx "
            "(o pulsa Enter para cancelar): "
        ).strip().strip('"').strip("'")
        return Path(manual) if manual else None

    def select_document(self, path: str | Path | None = None) -> bool:
        target = Path(path) if path is not None else self._pick_document()
        if target is None:
            self._out("Seleccion cancelada. Puedes escribir 'documento' cuando quieras.")
            return False
        return self.load_document_file(target)

    # ------------------------------------------------------------------
    # Proveedores y asistente
    # ------------------------------------------------------------------
    def _ensure_provider(self):
        if self._provider is None:
            self._provider = GeminiProvider(
                api_key=self.settings.gemini_api_key,
                model=self.settings.gemini_model,
            )
        return self._provider

    def _voice_provider(self) -> ElevenLabsProvider | None:
        if self._voice is not None:
            return self._voice
        if not self.settings.elevenlabs_configured:
            return None
        self._voice = ElevenLabsProvider(
            api_key=self.settings.elevenlabs_api_key,
            voice_id=self.settings.elevenlabs_voice_id,
            stt_model=self.settings.elevenlabs_stt_model,
            tts_model=self.settings.elevenlabs_tts_model,
            language_code=self.settings.elevenlabs_language,
        )
        return self._voice

    def _ensure_assistant(self) -> DocumentAssistant:
        if self._document is None:
            raise DocumentError(
                "Todavia no hay un documento seleccionado. Escribe 'documento' "
                "para elegir un archivo .docx."
            )
        if self._assistant is None:
            self._assistant = DocumentAssistant(
                provider=self._ensure_provider(),
                document=self._document,
                chunks=self._chunks,
                consent=self._consent,
                max_context_chars=self.settings.max_context_chars,
                max_batch_chars=self.settings.max_batch_chars,
                chunk_size_chars=self.settings.chunk_size_chars,
            )
        return self._assistant

    # ------------------------------------------------------------------
    # Voz
    # ------------------------------------------------------------------
    def _listen(self) -> str | None:
        if not self.settings.elevenlabs_configured:
            self._out(
                "\n[Jarvis] El microfono no esta configurado (falta "
                "ELEVENLABS_API_KEY). Escribe tu orden por teclado."
            )
            return None
        if not self._consent.request(ELEVENLABS_STT):
            return None

        recorder = self._recorder
        if recorder is None:
            recorder = AudioRecorder(
                sample_rate=self.settings.sample_rate,
                max_seconds=self.settings.max_record_seconds,
            )
            self._recorder = recorder

        if not recorder.is_available():
            self._out(
                "\n[Jarvis] No se detecto un microfono disponible. "
                "Puedes escribir tu orden por teclado."
            )
            return None

        self._out(
            "\nEscuchando... Pulsa Enter cuando termines de hablar "
            f"(maximo {int(self.settings.max_record_seconds)} segundos)."
        )
        audio_path: Path | None = None
        try:
            recorder.start()
            self._input("")
            audio_path = recorder.stop()
        except AudioError as exc:
            self._out(f"[Jarvis] {exc.user_message}")
            return None
        except KeyboardInterrupt:
            recorder.cancel()
            self._out("\nGrabacion cancelada.")
            return None

        try:
            voice = self._voice_provider()
            if voice is None:  # pragma: no cover - ya se comprobo arriba
                return None
            transcript = voice.transcribe(audio_path)
        except JarvisError as exc:
            self._out(f"[Jarvis] {exc.user_message}")
            return None
        finally:
            AudioRecorder.delete_file(audio_path)

        if not transcript:
            self._out("[Jarvis] No se pudo entender el audio. Intentalo de nuevo.")
            return None

        self._out("")
        self._out(f'Transcripcion: "{transcript}"')
        try:
            correction = self._input(
                "Pulsa Enter para usarla o escribe la correccion: "
            ).strip()
        except EOFError:
            correction = ""
        final_text = correction or transcript
        if correction:
            self._out(f'Usando: "{final_text}"')
        return final_text

    def _speak(self, answer: AssistantAnswer) -> None:
        if self._mode != "voz" or not self.settings.speak_responses:
            return
        if not self.settings.elevenlabs_tts_configured:
            if not self._warned_no_tts:
                self._out(
                    "  (Para escuchar las respuestas configura ELEVENLABS_VOICE_ID "
                    "en el archivo .env.)"
                )
                self._warned_no_tts = True
            return
        if not self._consent.request(ELEVENLABS_TTS):
            return
        speech = self._clean_for_speech(answer.text)
        if len(speech) < 3:
            return
        try:
            voice = self._voice_provider()
            if voice is not None:
                voice.speak(speech[:4000])
        except JarvisError as exc:
            self._out(f"  (No se pudo leer en voz alta: {exc.user_message})")

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        cleaned = _CITATION_FOR_SPEECH_RE.sub("", text)
        cleaned = _MARKDOWN_FOR_SPEECH_RE.sub("", cleaned)
        return " ".join(cleaned.split())

    # ------------------------------------------------------------------
    # Presentación de respuestas
    # ------------------------------------------------------------------
    def _present(self, answer: AssistantAnswer, *, title: str | None = None) -> None:
        self._out("")
        if title:
            self._out(title)
        self._out(f"[Jarvis] {answer.text.strip()}")
        if answer.notice:
            self._out(f"  {answer.notice.strip()}")
        if answer.sources:
            self._out("")
            self._out("Fuentes consultadas:")
            for source in answer.sources:
                heading = source.heading or "Sin encabezado"
                self._out(f"  - {heading} ({source.ref})")
        self._speak(answer)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def handle(self, text: str, *, from_voice: bool = False) -> None:
        intent = intents.parse(text)
        logger.info("Intencion reconocida: %s", intent.name)

        try:
            if intent.name == intents.EXIT:
                self._exit = True
                self._out("\nHasta luego. Jarvis queda cerrado.")
                return
            if intent.name == intents.HELP:
                self._out("")
                self._out(HELP_TEXT)
                return
            if intent.name == intents.SELECT_DOCUMENT:
                self.select_document()
                return
            if intent.name == intents.MODE_TEXT:
                self._mode = "texto"
                self._out("Modo texto activado. Escribe tus ordenes por teclado.")
                return
            if intent.name == intents.MODE_VOICE:
                self._activate_voice_mode()
                return

            if self._document is None:
                self._out(
                    "\n[Jarvis] Todavia no hay un documento. Escribe 'documento' "
                    "para seleccionar un archivo .docx."
                )
                return

            self._run_query(intent)

        except JarvisError as exc:
            logger.warning("Error controlado: %s", type(exc).__name__)
            self._out(f"\n[Jarvis] {exc.user_message}")
        except Exception:
            logger.exception("Error no controlado al procesar la orden")
            self._out(
                "\n[Jarvis] Ocurrio un error inesperado. La sesion continua; "
                "si el problema se repite, revisa el registro tecnico en logs/jarvis.log."
            )

    def _activate_voice_mode(self) -> None:
        if not self.settings.elevenlabs_configured:
            self._out(
                "\n[Jarvis] El modo voz requiere ELEVENLABS_API_KEY en el archivo .env. "
                "El modo texto sigue disponible (escribe 'modo texto')."
            )
            return
        self._mode = "voz"
        extra = (
            " Las respuestas se leeran en voz alta."
            if self.settings.elevenlabs_tts_configured and self.settings.speak_responses
            else " (No hay ELEVENLABS_VOICE_ID: recibiras las respuestas solo por escrito)."
        )
        self._out(
            "\nModo voz activado. Pulsa Enter sin escribir nada para grabar; "
            "puedes seguir escribiendo cuando quieras." + extra
        )

    def _run_query(self, intent: intents.Intent) -> None:
        assistant = self._ensure_assistant()

        if intent.name == intents.QUESTION:
            self._out("\nConsultando el documento...")
            answer = assistant.ask(intent.text)
            self._present(answer)
            return

        if intent.name == intents.SUMMARY:
            self._out("\nPreparando el resumen del documento...")
            answer = assistant.summarize()
            self._present(answer, title="Resumen general:")
            return

        if intent.name == intents.SUMMARY_SECTION:
            reference = intent.section
            if not reference:
                sections = assistant.available_sections()
                if not sections:
                    self._out(
                        "\n[Jarvis] El documento no tiene encabezados que permitan "
                        "identificar secciones."
                    )
                    return
                self._out("\nSecciones disponibles:")
                for item in sections[:20]:
                    self._out(f"  {item}")
                reference = self._input(
                    "Numero o titulo de la seccion (Enter para cancelar): "
                ).strip()
                if not reference:
                    self._out("Resumen cancelado.")
                    return
            self._out(f"\nPreparando el resumen de la seccion '{reference}'...")
            answer = assistant.summarize_section(reference)
            self._present(answer, title="Resumen de la seccion:")
            return

        if intent.name == intents.EXPLAIN:
            focus = intent.section or intent.topic or intent.text
            self._out(f"\nExplicando '{focus}'...")
            answer = assistant.explain(focus, detail=intent.detail)
            self._present(answer, title="Explicacion:")
            return

        kind = _EXTRACT_KINDS.get(intent.name)
        if kind is not None:
            label = _EXTRACT_LABELS[intent.name]
            self._out(f"\nBuscando {label.lower()} en el documento...")
            answer = assistant.extract(kind)
            self._present(answer, title=f"{label}:")
            return

        # Salvaguarda: cualquier intencion no cubierta se trata como pregunta.
        answer = assistant.ask(intent.text)
        self._present(answer)

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------
    def _read(self) -> tuple[str | None, bool]:
        if self._mode == "voz":
            prompt = "\nTú (Enter para hablar, o escribe una orden): "
        else:
            prompt = "\nTú: "
        raw = self._input(prompt)
        if raw is None:
            raise EOFError
        text = raw.strip()

        if not text:
            if self._mode == "voz":
                transcript = self._listen()
                return (transcript, True) if transcript else (None, False)
            self._out("Escribe una orden, una pregunta o 'ayuda' para ver las opciones.")
            return None, False
        return text, False

    def run(self, *, select_on_start: bool = True) -> None:
        self._out(WELCOME)
        if self.settings.validation_issues():
            self._out("")
            for issue in self.settings.validation_issues():
                self._out(f"Aviso: {issue}")
        for warning in self.settings.warnings:
            self._out(f"Aviso de configuracion: {warning}")

        if select_on_start and self._document is None:
            self._out("")
            self._out("Selecciona el documento con el que quieres trabajar.")
            self.select_document()

        while not self._exit:
            try:
                text, _from_voice = self._read()
            except (EOFError, KeyboardInterrupt):
                self._out("\nHasta luego.")
                break
            if text is None:
                continue
            self.handle(text)
