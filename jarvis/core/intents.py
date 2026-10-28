"""Interpretación local de órdenes en español.

Se usa un analizador de reglas (sin llamadas externas) para reconocer las
acciones de la consola. Si el texto no coincide con ninguna acción, se
trata como una pregunta sobre el documento.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Nombres de acción
HELP = "ayuda"
EXIT = "salir"
SELECT_DOCUMENT = "seleccionar_documento"
OPEN_DOCUMENT = "abrir_documento"
GREETING = "saludo"
PAUSE_MIC = "pausar_microfono"
RESUME_MIC = "reanudar_microfono"
STOP_SPEECH = "detener_voz"
CANCEL = "cancelar"
MODE_VOICE = "modo_voz"
MODE_TEXT = "modo_texto"
SUMMARY = "resumen"
SUMMARY_SECTION = "resumen_seccion"
EXPLAIN = "explicar"
EXTRACT_DATES = "extraer_fechas"
EXTRACT_ACTIONS = "extraer_acciones"
EXTRACT_RESPONSIBILITIES = "extraer_responsabilidades"
EXTRACT_CONCLUSIONS = "extraer_conclusiones"
QUESTION = "pregunta"

ORDINALS = {
    "primer": 1,
    "primero": 1,
    "primera": 1,
    "1": 1,
    "segundo": 2,
    "segunda": 2,
    "2": 2,
    "tercer": 3,
    "tercero": 3,
    "tercera": 3,
    "3": 3,
    "cuarto": 4,
    "cuarta": 4,
    "4": 4,
    "quinto": 5,
    "quinta": 5,
    "5": 5,
    "sexto": 6,
    "sexta": 6,
    "6": 6,
    "septimo": 7,
    "septima": 7,
    "7": 7,
    "octavo": 8,
    "octava": 8,
    "8": 8,
    "noveno": 9,
    "novena": 9,
    "9": 9,
    "decimo": 10,
    "decima": 10,
    "10": 10,
}

_SECTION_WORD = r"(?:seccion|apartado|capitulo|punto|parte)"
_SECTION_NUMBER_RE = re.compile(
    rf"\b{_SECTION_WORD}\s+(?:numero\s+)?(?:n[o°]\s*)?(\d{{1,2}})\b"
)
_SECTION_ORDINAL_RE = re.compile(
    rf"\b(primer|primero|primera|segundo|segunda|tercer|tercero|tercera|cuarto|"
    rf"cuarta|quinto|quinta|sexto|sexta|septimo|septima|octavo|octava|noveno|"
    rf"novena|decimo|decima)\s+{_SECTION_WORD}\b"
)
_SECTION_NAMED_RE = re.compile(
    rf"\b{_SECTION_WORD}\s+(?:de\s+|sobre\s+|llamad[oa]\s+|titulad[oa]\s+)([^?.!,]+)"
)

_EXIT_RE = re.compile(r"^(salir|salgo|adios|chau|hasta luego|terminar|cerrar|exit|quit)\b")
_HELP_RE = re.compile(
    r"\b(ayuda|que puedes hacer|que sabes hacer|opciones|comandos|"
    r"como te uso|como funcionas)\b"
)
_SELECT_RE = re.compile(
    r"\b(cambiar|seleccionar|selecciona|cargar|abrir|otro|otra)\b.*\b(documento|archivo|docx)\b"
    r"|\b(documento|archivo)\s+(nuevo|diferente|distinto)\b"
    r"|\b(lee|leer|abre|abrir)\b.*\b(documento|manual|archivo|docx)\b"
)
_MODE_VOICE_RE = re.compile(
    r"\b(modo voz|activar (la )?voz|usar (el )?microfono|quiero hablar|"
    r"por (el )?microfono|voz activada)\b"
)
_MODE_TEXT_RE = re.compile(
    r"\b(modo texto|desactivar (la )?voz|sin voz|por teclado|usar texto|"
    r"modo escrito)\b"
)

_GREETING_RE = re.compile(
    r"^[¿¡\s]*(?:hola|buenas|buenos dias|buenas tardes|buenas noches|hey|"
    r"que tal|saludos)\b[ ,.!?¿¡]*(?:jarvis\b)?[ ,.!?¿¡]*$"
)
_OPEN_DOC_RE = re.compile(
    r"\b(abre|abrir|abreme|abrirme|busca|buscar|buscame|encuentra|encontrar|"
    r"localiza|localizar)\b[^?.!]*\b(documento|documentos|archivo|archivos|"
    r"manual|docx|word)\b"
    r"|\b(busca|buscar|buscame|encuentra|encontrar|localiza|localizar)\b"
    r"[^?.!]*\bdescargas\b"
)
_STOP_SPEECH_RE = re.compile(
    r"\b(detente|deten la voz|detener la voz|deten el audio|para el audio|"
    r"para de hablar|deja de hablar|callate|silencio|basta|stop)\b"
)
_PAUSE_MIC_RE = re.compile(
    r"\b(pausa|pausar|pausa el microfono|pausar el microfono|deja de escuchar|"
    r"para de escuchar|desactiva el microfono|microfono en pausa|no escuches)\b"
)
_RESUME_MIC_RE = re.compile(
    r"\b(reanuda|reanudar|continua escuchando|vuelve a escuchar|activa el microfono|"
    r"escucha otra vez|sigue escuchando|reanuda la escucha)\b"
)
_CANCEL_RE = re.compile(r"^(cancela|cancelar|olvidalo|dejalo|nada|nada mas|no importa)\b")

_SUMMARY_RE = re.compile(
    r"\b(resumen|resume|resumir|resumelo|resumamelo|resumenes|sintesis|"
    r"sintetiza|de que trata|de que se trata|idea general|puntos clave)\b"
)
_EXPLAIN_RE = re.compile(
    r"\b(explica|explicame|explicar|explicacion|me explicas|"
    r"como funciona|que significa|en palabras sencillas|"
    r"como si fuera|de forma sencilla|en simple)\b"
)
_DETAIL_RE = re.compile(r"\b(detalle|detallado|detallada|a fondo|en profundidad|mas extenso)\b")

_DATES_RE = re.compile(r"\b(fechas|fecha|plazos|plazo|vencimientos|vencimiento|calendario)\b")
_ACTIONS_RE = re.compile(
    r"\b(acciones|tareas|pendientes|proximos pasos|siguientes pasos)\b"
)
_RESPONSIBILITIES_RE = re.compile(
    r"\b(responsabilidades|responsabilidad|responsables|responsable|a cargo|encargad[oa]s?)\b"
)
_CONCLUSIONS_RE = re.compile(r"\b(conclusiones|conclusion|cierre)\b")

_EXTRACT_VERBS_RE = re.compile(
    r"\b(extrae|extraer|extraig|lista|listar|listame|enumera|enumerar|"
    r"muestra|muestrame|dime|que fechas|que acciones)\b"
)

_SHORT_COMMANDS: dict[str, str] = {
    "documento": SELECT_DOCUMENT,
    "otro documento": SELECT_DOCUMENT,
    "cambiar documento": SELECT_DOCUMENT,
    "seleccionar documento": SELECT_DOCUMENT,
    "resumen": SUMMARY,
    "resumen general": SUMMARY,
    "fechas": EXTRACT_DATES,
    "plazos": EXTRACT_DATES,
    "acciones": EXTRACT_ACTIONS,
    "tareas": EXTRACT_ACTIONS,
    "pendientes": EXTRACT_ACTIONS,
    "responsabilidades": EXTRACT_RESPONSIBILITIES,
    "conclusiones": EXTRACT_CONCLUSIONS,
    "voz": MODE_VOICE,
    "microfono": MODE_VOICE,
    "texto": MODE_TEXT,
    "pausa": PAUSE_MIC,
    "pausar": PAUSE_MIC,
    "reanuda": RESUME_MIC,
    "reanudar": RESUME_MIC,
    "detente": STOP_SPEECH,
    "detener voz": STOP_SPEECH,
    "cancela": CANCEL,
    "cancela eso": CANCEL,
    "ayuda": HELP,
    "salir": EXIT,
    "exit": EXIT,
}


def normalize(text: str) -> str:
    """Minúsculas, sin acentos y con espacios normalizados."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def strip_wake_word(text: str) -> str:
    normalized = normalize(text)
    normalized = re.sub(
        r"^(?:(?:oye|hola|hey)\s+)?jarvis\b[\s,.:;\-]*",
        "",
        normalized,
    )
    return normalized.strip()


@dataclass(frozen=True)
class Intent:
    name: str
    text: str
    section: str | None = None
    topic: str | None = None
    detail: bool = False
    document_query: str | None = None


def find_section_reference(normalized_text: str) -> str | None:
    """Devuelve una referencia de sección: número ordinal o nombre."""
    match = _SECTION_NUMBER_RE.search(normalized_text)
    if match:
        return match.group(1)
    match = _SECTION_ORDINAL_RE.search(normalized_text)
    if match:
        return str(ORDINALS.get(match.group(1), match.group(1)))
    match = _SECTION_NAMED_RE.search(normalized_text)
    if match:
        candidate = match.group(1).strip(" .")
        if candidate:
            return candidate
    return None


def _extract_topic(normalized_text: str) -> str | None:
    topic = normalized_text
    for prefix in (
        "me puedes ",
        "puedes ",
        "podrias ",
        "por favor ",
        "quiero que ",
        "quisiera que ",
        "necesito que ",
    ):
        if topic.startswith(prefix):
            topic = topic[len(prefix) :]
    for verb in (
        "explicame",
        "explica",
        "explicar",
        "explicacion de",
        "explicacion",
        "que significa",
        "como funciona",
        "en palabras sencillas",
        "de forma sencilla",
        "como si fuera",
    ):
        if topic.startswith(verb):
            topic = topic[len(verb) :].strip(" ,.:;")
            break
        marker = f" {verb} "
        if marker in topic:
            topic = topic.split(marker, 1)[1].strip(" ,.:;")
            break
    topic = topic.strip(" ?!.,;:")
    return topic or None


def _extract_document_query(normalized_text: str) -> str | None:
    """Aísla el nombre del documento en una orden de apertura."""
    text = normalized_text
    text = re.sub(r"^(?:por favor[ ,]+)+", "", text)
    text = re.sub(
        r"^(?:abre|abrir|abreme|abrirme|busca|buscar|buscame|encuentra|"
        r"encontrar|localiza|localizar)\s+",
        "",
        text,
    )
    # "en/de Descargas" o "de la carpeta de Descargas" no forma parte del nombre.
    text = re.sub(
        r"\b(?:de|en|dentro\s+de)\s+(?:la\s+)?(?:carpeta\s+de\s+)?descargas\b",
        " ",
        text,
    )
    text = re.sub(r"^(?:el|la|los|las|un|una)\s+", "", text)
    text = re.sub(
        r"^(?:documento|documentos|archivo|archivos|docx|word)(?:\s+|$)", "", text
    )
    text = re.sub(r"^(?:de|del)\s+", "", text)
    text = re.sub(r"^descargas\s+", "", text)
    text = re.sub(
        r"\b(?:que\s+se\s+llama|que\s+se\s+llamaba|llamado|llamada|"
        r"titulado|titulada)\b",
        " ",
        text,
    )
    text = re.sub(r"\s+y\s+(?:abrelo|abrela|abrir|abre|muestralo|muestrala)\b.*$", "", text)
    text = re.sub(
        r"\s+y\s+(?:resumelo|resumela|resume|explicamelo|explica|dime)\b.*$",
        "",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,.;:?!")
    return text or None


def _is_short_command(normalized_text: str, max_words: int = 7) -> bool:
    return len(normalized_text.split()) <= max_words


def parse(text: str) -> Intent:
    """Convierte una orden escrita o transcrita en una intención."""
    raw = normalize(text)
    if _GREETING_RE.match(raw):
        return Intent(GREETING, text.strip())

    normalized = strip_wake_word(text)
    if not normalized:
        return Intent(QUESTION, text.strip())

    if _GREETING_RE.match(normalized):
        return Intent(GREETING, text.strip())

    short = _SHORT_COMMANDS.get(normalized)
    if short is not None:
        return Intent(short, text.strip())

    if _EXIT_RE.search(normalized):
        return Intent(EXIT, text.strip())

    if _GREETING_RE.match(normalized):
        return Intent(GREETING, text.strip())

    if _is_short_command(normalized):
        if _STOP_SPEECH_RE.search(normalized):
            return Intent(STOP_SPEECH, text.strip())
        if _PAUSE_MIC_RE.search(normalized):
            return Intent(PAUSE_MIC, text.strip())
        if _RESUME_MIC_RE.search(normalized):
            return Intent(RESUME_MIC, text.strip())
        if _CANCEL_RE.search(normalized):
            return Intent(CANCEL, text.strip())

    if _HELP_RE.search(normalized) and len(normalized.split()) <= 8:
        return Intent(HELP, text.strip())

    if _OPEN_DOC_RE.search(normalized):
        return Intent(
            OPEN_DOCUMENT,
            text.strip(),
            document_query=_extract_document_query(normalized),
        )

    if _SELECT_RE.search(normalized):
        return Intent(SELECT_DOCUMENT, text.strip())

    if _MODE_VOICE_RE.search(normalized):
        return Intent(MODE_VOICE, text.strip())

    if _MODE_TEXT_RE.search(normalized):
        return Intent(MODE_TEXT, text.strip())

    section = find_section_reference(normalized)
    wants_extraction = bool(_EXTRACT_VERBS_RE.search(normalized))

    if _DATES_RE.search(normalized) and wants_extraction:
        return Intent(EXTRACT_DATES, text.strip(), section=section)

    if _ACTIONS_RE.search(normalized) and wants_extraction:
        return Intent(EXTRACT_ACTIONS, text.strip(), section=section)

    if _RESPONSIBILITIES_RE.search(normalized) and wants_extraction:
        return Intent(EXTRACT_RESPONSIBILITIES, text.strip(), section=section)

    if _CONCLUSIONS_RE.search(normalized) and wants_extraction:
        return Intent(EXTRACT_CONCLUSIONS, text.strip(), section=section)

    if _SUMMARY_RE.search(normalized):
        if section:
            return Intent(SUMMARY_SECTION, text.strip(), section=section)
        return Intent(SUMMARY, text.strip())

    if _EXPLAIN_RE.search(normalized):
        return Intent(
            EXPLAIN,
            text.strip(),
            section=section,
            topic=_extract_topic(normalized),
            detail=bool(_DETAIL_RE.search(normalized)),
        )

    return Intent(QUESTION, text.strip())
