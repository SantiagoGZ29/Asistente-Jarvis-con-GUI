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

# Google: Gmail y Google Calendar (solo lectura)
MAIL_REVIEW = "correos_revisar"
MAIL_COUNT = "correos_contar"
MAIL_READ = "correos_leer"
MAIL_FOLLOWUP = "correos_seguimiento"
CALENDAR_AGENDA = "agenda_consultar"
CALENDAR_NEXT = "agenda_proxima"
CALENDAR_FOLLOWUP = "agenda_seguimiento"
GOOGLE_STATUS = "google_estado"

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
    r"manual|docx|word|excel|libro|libros|xlsx|xlsm|planilla|hoja|hojas)\b"
    r"|\b(busca|buscar|buscame|encuentra|encontrar|localiza|localizar)\b"
    r"[^?.!]*\bdescargas\b"
)

_SPREADSHEET_WORDS = (
    "excel",
    "xlsx",
    "xlsm",
    "libro",
    "planilla",
    "hoja de calculo",
    "hoja de cálculo",
    "calculos",
)
_DOCUMENT_WORDS = ("docx", "word", "documento", "texto")
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

# ----------------------------------------------------------------------
# Google: Gmail y Google Calendar (solo lectura)
# ----------------------------------------------------------------------
_MAIL_WORD = (
    r"(?:correo|correos|mensaje|mensajes|email|emails|mail|mails|gmail|"
    r"bandeja(?:\s+de\s+entrada)?|inbox)"
)
_CAL_WORD = (
    r"(?:agenda|calendario|reunion|reuniones|evento|eventos|junta|juntas|"
    r"cita|citas|calendar)"
)
_WEEKDAY_WORDS = (
    "lunes",
    "martes",
    "miercoles",
    "jueves",
    "viernes",
    "sabado",
    "domingo",
)

_GOOGLE_STATUS_RE = re.compile(
    r"\b(estado|estatus|situacion)\b[^?.!]{0,20}\b(google|gmail|calendar|calendario)\b"
    r"|\b(google|gmail|calendar|calendario)\b[^?.!]{0,20}\b(conectado|desconectado|estado)\b"
    r"|\b(conecta|conectar|desconecta|desconectar)\b[^?.!]{0,15}\b"
    r"(google|gmail|calendar|calendario)\b"
)

_MAIL_COUNT_RE = re.compile(
    rf"\b(cuant[oa]s?)\b[^?.!]{{0,40}}\b{_MAIL_WORD}\b"
    rf"|\b{_MAIL_WORD}\b[^?.!]{{0,25}}\b(nuevos|sin leer|no leidos)\b"
)

_MAIL_LAST_RE = re.compile(
    rf"\b(ultimo|ultima|mas reciente|reciente)\b[^?.!]{{0,25}}\b{_MAIL_WORD}\b"
    rf"|\b{_MAIL_WORD}\b[^?.!]{{0,25}}\b(ultimo|ultima|mas reciente|reciente)\b"
)

_MAIL_READ_RE = re.compile(
    rf"\b(lee|leer|leelo|leerlo|abre|abrir|abreme|muestra|muestrame|busca|"
    rf"buscar|buscame|encuentra|encontrar)\b[^?.!]{{0,90}}\b{_MAIL_WORD}\b"
)

_MAIL_REVIEW_RE = re.compile(
    rf"\b(revisa|revisar|consulta|consultar|mira|mirar|lista|listar|"
    rf"muestra|muestrame|lee|leer)\b[^?.!]{{0,70}}\b{_MAIL_WORD}\b"
    r"|\b(mis|los|todos los)\s+correos\b"
    r"|\bbandeja de entrada\b"
)

_MAIL_FOLLOWUP_RE = re.compile(
    r"\b(de quien (es|se trata)|quien (lo |la )?(envio|mando|escribio)|"
    r"quien es el remitente|que dice( el| ese| este)? (correo|mensaje)|"
    r"de que trata (el|ese|este) (correo|mensaje)|tiene adjuntos|"
    r"esta leido|sin leer|importancia del correo|destinatario del correo)\b"
    r"|\b(asunto|fecha|remitente|contenido|resumen|resumeme|resumelo|resume|"
    r"adjuntos|importancia)\b"
    rf"[^?.!]{{0,20}}\b{_MAIL_WORD}\b"
    rf"|\b{_MAIL_WORD}\b[^?.!]{{0,25}}\b(asunto|fecha|remitente|contenido|"
    rf"resumen|resumeme|resumelo|resume|adjuntos|importancia|dice|trata)\b"
)

_CAL_NEXT_RE = re.compile(
    r"\b(proxima|proximo|siguiente)\b[^?.!]{0,25}\b(reunion|evento|cita|junta)\b"
    r"|\b(reunion|evento|cita|junta)\b[^?.!]{0,20}\b(proxima|proximo|siguiente)\b"
    r"|\ba que hora (es|sera)\b[^?.!]{0,25}\b(reunion|evento|cita|junta)\b"
)

_CAL_AGENDA_RE = re.compile(
    r"\b(que tengo|que hay)\b"
    r"(?![^?.!]{0,25}\b(abierto|cargado|documento|manual|informe|libro|"
    r"excel|word|hoja|archivo)\b)"
    r"|\b(que reuniones|que eventos|mis reuniones|mis eventos|mi agenda|"
    r"mi calendario|tengo (algo|reuniones|eventos))\b"
    r"|\b(proximas?|siguientes?)\s+(reuniones|eventos)\b"
    r"|\b(cuales son|cual es)\b[^?.!]{0,20}\b(reuniones|eventos)\b"
    rf"|\b(lee|leer|consulta|consultar|revisa|revisar|muestra|muestrame)\b"
    rf"[^?.!]{{0,40}}\b{_CAL_WORD}\b"
    rf"|\b{_CAL_WORD}\b[^?.!]{{0,30}}\b(hoy|manana|semana|proximos|"
    r"lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b"
)

_CAL_FOLLOWUP_RE = re.compile(
    r"\b(donde (es|sera|se realizara|se realiza|queda)|quien (organiza|convoca)|"
    r"participantes|asistentes|invitados|a que hora (empieza|termina|es)|"
    r"detalles (del|de la) (evento|reunion|cita)|primera (reunion|evento)|"
    r"ultima (reunion|evento))\b"
    rf"|\b(reunion|evento|cita|junta)\b[^?.!]{{0,25}}\b(donde|quien|hora|"
    r"participantes|organiza|asistentes)\b"
)

_SUBJECT_QUERY_RE = re.compile(
    r"\b(?:con\s+)?asunto\s+(?:de\s+|sobre\s+|llamado\s+|titulado\s+)?(.+)$"
)
_SENDER_QUERY_RE = re.compile(
    r"\b(?:enviado\s+por|remitente|de|del)\s+(.+)$"
)

_MAIL_TAIL_RE = re.compile(
    r"\s+(?:en|de)\s+(?:la\s+|mi\s+)?(?:bandeja(?:\s+de\s+entrada)?|inbox)\b.*$"
    r"|\s+que\s+(?:me\s+)?(?:envio|mando|escribio|recibi)\b.*$"
    r"|\s+y\s+(?:resumelo|resumela|resume|leelo|leela|dime)\b.*$"
    r"|\s+por\s+favor\b.*$"
)

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
    "correos": MAIL_REVIEW,
    "mis correos": MAIL_REVIEW,
    "agenda": CALENDAR_AGENDA,
    "mi agenda": CALENDAR_AGENDA,
    "calendario": CALENDAR_AGENDA,
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
    file_kind: str = ""
    query: str | None = None
    mode: str = ""
    period: str = ""


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
    """Aísla el nombre del documento o libro en una orden de apertura."""
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
        r"\b(?:que\s+)?(?:tengo|hay|esta|está|se\s+encuentra)\s+"
        r"(?:de|en|dentro\s+de)\s+(?:la\s+)?(?:carpeta\s+de\s+)?descargas\b",
        " ",
        text,
    )
    text = re.sub(
        r"\b(?:de|en|dentro\s+de)\s+(?:la\s+)?(?:carpeta\s+de\s+)?descargas\b",
        " ",
        text,
    )
    text = re.sub(r"^(?:el|la|los|las|un|una|mi|mis)\s+", "", text)
    text = re.sub(
        r"^(?:documento|documentos|archivo|archivos|docx|word|excel|libro|"
        r"libros|planilla|hoja|hojas|xlsx|xlsm)(?:\s+|$)",
        "",
        text,
    )
    text = re.sub(r"^(?:de|del)\s+", "", text)
    text = re.sub(r"^(?:el|la|los|las|un|una|mi|mis)\s+", "", text)
    text = re.sub(r"^descargas\s+", "", text)
    text = re.sub(
        r"\b(?:que\s+se\s+llama|que\s+se\s+llamaba|llamado|llamada|"
        r"titulado|titulada)\b",
        " ",
        text,
    )
    text = re.sub(r"\.(docx|xlsx|xlsm|xls|xlsb)\b", "", text)
    text = re.sub(r"\s+y\s+(?:abrelo|abrela|abrir|abre|muestralo|muestrala)\b.*$", "", text)
    text = re.sub(
        r"\s+y\s+(?:resumelo|resumela|resume|explicamelo|explica|dime)\b.*$",
        "",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,.;:?!")
    return text or None


def detect_file_kind(normalized_text: str) -> str:
    """Distingue una orden sobre Excel de una orden sobre Word."""
    text = normalized_text
    spreadsheet = any(word in text for word in _SPREADSHEET_WORDS)
    document = any(word in text for word in _DOCUMENT_WORDS)
    if spreadsheet and not document:
        return "spreadsheet"
    if document and not spreadsheet:
        return "document"
    if ".xls" in text:
        return "spreadsheet"
    if ".docx" in text:
        return "document"
    return ""


def _is_short_command(normalized_text: str, max_words: int = 7) -> bool:
    return len(normalized_text.split()) <= max_words


def _clean_mail_query(value: str) -> str:
    text = value or ""
    text = _MAIL_TAIL_RE.sub("", text)
    text = re.sub(r"^(?:el|la|los|las|un|una|mi|mis|tu|sus)\s+", "", text)
    text = re.sub(
        r"\b(?:que\s+se\s+llama|llamado|llamada|titulado|titulada)\b", " ", text
    )
    text = re.sub(r"[«»\"“”']", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;:?!")
    return text


def extract_mail_query(normalized_text: str) -> tuple[str, str]:
    """Devuelve el modo (asunto/remitente) y el texto buscado."""
    text = re.sub(r"^(?:por favor[ ,]+)+", "", normalized_text)
    subject = _SUBJECT_QUERY_RE.search(text)
    if subject:
        return "subject", _clean_mail_query(subject.group(1))
    sender = _SENDER_QUERY_RE.search(text)
    if sender:
        query = _clean_mail_query(sender.group(1))
        if query:
            return "sender", query
    rest = re.sub(
        rf"^.*\b{_MAIL_WORD}\b\s*", "", text
    )
    return "", _clean_mail_query(rest)


def extract_calendar_period(normalized_text: str) -> str:
    """Traduce hoy/mañana/semana/día de la semana a un período interno."""
    text = normalized_text
    if "pasado manana" in text:
        return "tomorrow"
    for name in _WEEKDAY_WORDS:
        if re.search(rf"\b(?:el|este|para el)\s+{name}\b", text) or re.search(
            rf"\b{name}\b", text
        ):
            return f"weekday:{_WEEKDAY_WORDS.index(name)}"
    if re.search(r"\b(proximos?\s+(siete|7)\s+dias|siguiente semana|proxima semana)\b", text):
        return "next7"
    if re.search(r"\b(esta semana|la semana|toda la semana)\b", text):
        return "week"
    if re.search(r"\bmanana\b", text):
        return "tomorrow"
    if re.search(r"\bhoy\b", text):
        return "today"
    if re.search(r"\b(proximas?|siguientes?)\s+(reuniones|eventos)\b", text):
        return "next7"
    return ""


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

    # ------------------------------------------------------------------
    # Google (solo lectura). Se evalúa antes de documentos y resúmenes.
    # ------------------------------------------------------------------
    if _GOOGLE_STATUS_RE.search(normalized):
        if re.search(r"\b(desconecta|desconectar)\b", normalized):
            mode = "disconnect"
        elif re.search(r"\b(conecta|conectar)\b", normalized):
            mode = "connect"
        else:
            mode = "status"
        return Intent(GOOGLE_STATUS, text.strip(), mode=mode)

    if _MAIL_COUNT_RE.search(normalized):
        return Intent(MAIL_COUNT, text.strip())

    if _MAIL_LAST_RE.search(normalized) and (
        _MAIL_READ_RE.search(normalized)
        or re.search(r"\b(lee|leer|leelo|muestra|muestrame|abre|dime|resume)\b", normalized)
        or len(normalized.split()) <= 6
    ):
        return Intent(MAIL_READ, text.strip(), mode="last")

    if _MAIL_FOLLOWUP_RE.search(normalized):
        return Intent(MAIL_FOLLOWUP, text.strip())

    if _MAIL_READ_RE.search(normalized):
        mode, query = extract_mail_query(normalized)
        return Intent(MAIL_READ, text.strip(), query=query or None, mode=mode or "any")

    if _MAIL_REVIEW_RE.search(normalized):
        return Intent(MAIL_REVIEW, text.strip())

    if _CAL_NEXT_RE.search(normalized) and not re.search(
        r"\b(proximas|siguientes)\s+(reuniones|eventos)\b", normalized
    ):
        return Intent(CALENDAR_NEXT, text.strip())

    if _CAL_AGENDA_RE.search(normalized):
        return Intent(
            CALENDAR_AGENDA,
            text.strip(),
            period=extract_calendar_period(normalized) or "today",
        )

    if _CAL_FOLLOWUP_RE.search(normalized):
        return Intent(CALENDAR_FOLLOWUP, text.strip())

    if _OPEN_DOC_RE.search(normalized):
        return Intent(
            OPEN_DOCUMENT,
            text.strip(),
            document_query=_extract_document_query(normalized),
            file_kind=detect_file_kind(normalized),
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
