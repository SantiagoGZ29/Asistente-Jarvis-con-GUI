"""Consentimiento explícito antes de enviar datos a servicios externos.

Jarvis pide permiso la primera vez por sesión y por tipo de dato. Si el
usuario rechaza, no se envía nada y la aplicación sigue funcionando con
las funciones locales o en modo texto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

GEMINI_DOCUMENT_CONSENT = (
    "Para responder preguntas y generar resúmenes, Jarvis enviará el texto "
    "seleccionado de tu documento a Google Gemini (servicio externo de IA).\n"
    "  - Qué se envía: únicamente los fragmentos del documento relacionados con "
    "tu consulta (no se envían archivos completos ni rutas locales).\n"
    "  - A quién: Google (API de Gemini, https://ai.google.dev).\n"
    "  - Aviso de privacidad: en el nivel gratuito, Google puede usar el "
    "contenido enviado para mejorar sus productos. Por eso no se recomienda "
    "usar documentos laborales confidenciales con esta configuración.\n"
    "  - Jarvis no habilita facturación ni planes de pago automáticamente."
)

GEMINI_SPREADSHEET_CONSENT = (
    "Para interpretar tus preguntas sobre el libro de Excel y redactar las "
    "respuestas, Jarvis enviará a Google Gemini (servicio externo de IA) el "
    "perfil del libro y los resultados ya calculados.\n"
    "  - Qué se envía: nombres de hojas y columnas, tipos de datos, una muestra "
    "mínima de filas y los resultados numéricos calculados por Jarvis. Nunca "
    "se envía el archivo completo ni rutas locales.\n"
    "  - Qué NO se envía: los cálculos se hacen en tu equipo; Gemini no recibe "
    "el libro entero ni ejecuta fórmulas.\n"
    "  - A quién: Google (API de Gemini, https://ai.google.dev).\n"
    "  - Aviso de privacidad: en el nivel gratuito, Google puede usar el "
    "contenido enviado para mejorar sus productos. Los libros con datos "
    "confidenciales requieren una configuración de pago y tu propia revisión.\n"
    "  - Puedes rechazarlo: Jarvis seguirá analizando el libro localmente y "
    "respondiendo con sus propios cálculos, sin redactado externo.\n"
    "  - Jarvis no habilita facturación ni planes de pago automáticamente."
)

GEMINI_CHAT_CONSENT = (
    "Para conversar contigo cuando no hay un documento abierto, Jarvis enviará "
    "tu mensaje y los últimos mensajes de la conversación a Google Gemini "
    "(servicio externo de IA).\n"
    "  - Qué se envía: tu mensaje y un historial breve y acotado de la charla "
    "(no se envían archivos ni rutas locales).\n"
    "  - A quién: Google (API de Gemini, https://ai.google.dev).\n"
    "  - Aviso de privacidad: en el nivel gratuito, Google puede usar el "
    "contenido enviado para mejorar sus productos.\n"
    "  - Puedes rechazarlo: Jarvis seguirá funcionando en modo local (abrir "
    "documentos, resúmenes ya cargados y controles por texto).\n"
    "  - Jarvis no habilita facturación ni planes de pago automáticamente."
)

ELEVENLABS_STT_CONSENT = (
    "Para transcribir tu voz, Jarvis enviará audio del micrófono a ElevenLabs "
    "(servicio externo de voz).\n"
    "  - Qué se envía: el audio capturado mientras la escucha está activa. En "
    "tiempo real se envían fragmentos de forma continua; en modo por lotes, la "
    "frase completa al terminar.\n"
    "  - Cuándo: solo con el micrófono activo y autorizado. Al pausar, la "
    "captura se suspende; mientras Jarvis habla, el micrófono se silencia para "
    "evitar eco.\n"
    "  - A quién: ElevenLabs (API de voz, https://elevenlabs.io).\n"
    "  - En tiempo real el audio no se guarda en disco para transcribir. En "
    "modo por lotes, el archivo temporal se borra en cuanto se usa."
)

ELEVENLABS_TTS_CONSENT = (
    "Para leer las respuestas en voz alta, Jarvis enviará el texto de la "
    "respuesta a ElevenLabs (servicio externo de voz).\n"
    "  - Qué se envía: el texto de la respuesta que Jarvis generó para ti.\n"
    "  - A quién: ElevenLabs (API de voz, https://elevenlabs.io)."
)


@dataclass(frozen=True)
class ConsentRequest:
    key: str
    provider: str
    purpose: str
    description: str


GEMINI_DOCUMENT = ConsentRequest(
    key="gemini_document",
    provider="Google Gemini",
    purpose="analizar el documento y responder preguntas",
    description=GEMINI_DOCUMENT_CONSENT,
)

GEMINI_CHAT = ConsentRequest(
    key="gemini_chat",
    provider="Google Gemini",
    purpose="conversar contigo",
    description=GEMINI_CHAT_CONSENT,
)

GEMINI_SPREADSHEET = ConsentRequest(
    key="gemini_spreadsheet",
    provider="Google Gemini",
    purpose="interpretar preguntas sobre el libro de Excel",
    description=GEMINI_SPREADSHEET_CONSENT,
)

ELEVENLABS_STT = ConsentRequest(
    key="elevenlabs_stt",
    provider="ElevenLabs",
    purpose="transcribir tu voz",
    description=ELEVENLABS_STT_CONSENT,
)

ELEVENLABS_TTS = ConsentRequest(
    key="elevenlabs_tts",
    provider="ElevenLabs",
    purpose="leer la respuesta en voz alta",
    description=ELEVENLABS_TTS_CONSENT,
)

ALL_REQUESTS: dict[str, ConsentRequest] = {
    request.key: request
    for request in (
        GEMINI_DOCUMENT,
        GEMINI_CHAT,
        GEMINI_SPREADSHEET,
        ELEVENLABS_STT,
        ELEVENLABS_TTS,
    )
}


class ConsentManager:
    """Gestiona los consentimientos de una sesión.

    ``ask`` recibe la petición y debe devolver True (acepta) o False (rechaza).
    """

    def __init__(
        self,
        ask: Callable[[ConsentRequest], bool],
        *,
        enabled: bool = True,
    ) -> None:
        self._ask = ask
        self._enabled = enabled
        self._granted: set[str] = set()
        self._denied: set[str] = set()

    @property
    def granted(self) -> frozenset[str]:
        return frozenset(self._granted)

    @property
    def denied(self) -> frozenset[str]:
        return frozenset(self._denied)

    @staticmethod
    def _key(request: ConsentRequest | str) -> str:
        return request.key if isinstance(request, ConsentRequest) else str(request)

    def grant(self, request: ConsentRequest | str) -> None:
        """Registra una aceptación sin volver a preguntar."""
        key = self._key(request)
        self._granted.add(key)
        self._denied.discard(key)

    def deny(self, request: ConsentRequest | str) -> None:
        """Registra un rechazo sin volver a preguntar."""
        key = self._key(request)
        self._denied.add(key)
        self._granted.discard(key)

    def status(self, request: ConsentRequest | str) -> str:
        key = self._key(request)
        if key in self._granted:
            return "granted"
        if key in self._denied:
            return "denied"
        return "unknown"

    def is_granted(self, request: ConsentRequest | str) -> bool:
        return self._key(request) in self._granted

    def request(self, request: ConsentRequest) -> bool:
        """Devuelve True si ya se aceptó o si el usuario acepta ahora."""
        if not self._enabled:
            return True
        if request.key in self._granted:
            return True
        if request.key in self._denied:
            return False
        try:
            accepted = bool(self._ask(request))
        except (EOFError, KeyboardInterrupt):
            accepted = False
        if accepted:
            self._granted.add(request.key)
        else:
            self._denied.add(request.key)
        return accepted
