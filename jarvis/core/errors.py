"""Errores de Mi Jarvis con mensajes claros en español."""

from __future__ import annotations

from typing import Any


class JarvisError(Exception):
    """Error controlado: el mensaje está pensado para mostrarse al usuario."""

    default_message = "Ha ocurrido un error inesperado en Jarvis."

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.user_message = message or self.default_message
        # ``detail`` es para diagnóstico técnico; puede contener datos
        # sensibles, así que no se muestra ni se registra por defecto.
        self.detail = detail
        super().__init__(self.user_message)


class ConfigError(JarvisError):
    default_message = "La configuración de Jarvis no es válida."


class DocumentError(JarvisError):
    default_message = "No se pudo leer el documento seleccionado."


class DocumentNotFoundError(DocumentError):
    default_message = "No se encontró el archivo indicado. Revisa la ruta e inténtalo de nuevo."


class DocumentFormatError(DocumentError):
    default_message = (
        "El archivo no es un documento de Word (.docx) válido o está dañado. "
        "Abre el archivo en Word, guárdalo de nuevo como .docx y vuelve a intentarlo."
    )


class DocumentProtectedError(DocumentError):
    default_message = (
        "El documento parece estar protegido, abierto en Word o sin permisos de "
        "lectura. Ciérralo en Word o comprueba los permisos y vuelve a intentarlo."
    )


class DocumentEmptyError(DocumentError):
    default_message = (
        "El documento no contiene texto que Jarvis pueda leer. "
        "Ten en cuenta que esta versión no lee imágenes, escaneos ni manuscritos."
    )


class SpreadsheetError(DocumentError):
    default_message = "No se pudo leer el libro de Excel seleccionado."


class SpreadsheetFormatError(SpreadsheetError):
    default_message = (
        "El archivo no es un libro de Excel compatible. Esta versión lee .xlsx "
        "y .xlsm. Si tu archivo es .xls o .xlsb, ábrelo en Excel y guárdalo "
        "como .xlsx."
    )


class SpreadsheetProtectedError(SpreadsheetError):
    default_message = (
        "El libro parece estar protegido, abierto en Excel o sin permisos de "
        "lectura. Ciérralo en Excel o comprueba los permisos y vuelve a intentarlo."
    )


class SpreadsheetEmptyError(SpreadsheetError):
    default_message = (
        "El libro no contiene datos legibles en sus hojas visibles. "
        "Comprueba que no esté vacío o que las hojas no estén ocultas."
    )


class SpreadsheetLimitError(SpreadsheetError):
    default_message = (
        "El libro supera el límite configurado para analizarlo con seguridad. "
        "Puedes aumentar JARVIS_SPREADSHEET_MAX_FILE_MB o analizar una copia "
        "más pequeña."
    )


class GoogleError(JarvisError):
    """Fallo de la integración de solo lectura con Gmail y Google Calendar."""

    default_message = "No se pudo completar la operación con Google."


class GoogleNotConfiguredError(GoogleError):
    default_message = (
        "Google no está configurado. Descarga el archivo credentials.json de "
        "una aplicación de escritorio de Google Cloud, colócalo en el proyecto "
        "y define GOOGLE_OAUTH_CLIENT_FILE en el archivo .env. Consulta el "
        "README para crear las credenciales."
    )


class GoogleNotConnectedError(GoogleError):
    default_message = (
        "Google no está conectado. Pulsa «CONECTAR GOOGLE» en la ventana para "
        "autorizar tu cuenta con el navegador. Word, Excel y el resto de "
        "funciones siguen disponibles."
    )


class GoogleAuthCancelledError(GoogleError):
    default_message = (
        "Se canceló la conexión con Google. Puedes volver a intentarlo con "
        "«CONECTAR GOOGLE»."
    )


class GoogleConsentDeniedError(GoogleError):
    default_message = (
        "No se concedieron los permisos de Google, así que la conexión se "
        "canceló. Jarvis solo necesita permiso de lectura de Gmail y de "
        "Google Calendar."
    )


class GoogleAccessBlockedError(GoogleError):
    default_message = (
        "Google bloqueó el acceso de la aplicación. Comprueba que la "
        "aplicación OAuth está publicada o que tu cuenta aparece como usuario "
        "de prueba en Google Cloud. Jarvis no intenta evitar esa política."
    )


class GoogleAuthExpiredError(GoogleError):
    default_message = (
        "La sesión de Google venció, el token ya no es válido o se revocaron "
        "los permisos. Pulsa «CONECTAR GOOGLE» para volver a autorizar la "
        "cuenta."
    )


class GoogleForbiddenError(GoogleError):
    default_message = (
        "Google rechazó la consulta (error 403). Comprueba que la aplicación "
        "tiene los permisos gmail.readonly y calendar.events.readonly "
        "concedidos para tu cuenta."
    )


class GoogleRateLimitError(GoogleError):
    default_message = (
        "Google limitó temporalmente las solicitudes (error 429). Jarvis "
        "respetó el tiempo de espera indicado y no hace reintentos "
        "ilimitados. Inténtalo de nuevo en unos segundos."
    )


class GoogleNetworkError(GoogleError):
    default_message = (
        "No se pudo conectar con Google. Comprueba tu conexión a Internet; el "
        "resto de funciones de Jarvis siguen disponibles."
    )


class GoogleApiError(GoogleError):
    default_message = (
        "Google devolvió una respuesta que Jarvis no pudo procesar. "
        "Inténtalo de nuevo en unos minutos."
    )


class ProviderError(JarvisError):
    default_message = "El proveedor de inteligencia artificial no está disponible."


class ProviderNotConfiguredError(ProviderError):
    default_message = (
        "Falta la clave de API necesaria. Revisa el archivo .env y vuelve a iniciar Jarvis."
    )


class ProviderAuthError(ProviderError):
    default_message = (
        "La clave de API fue rechazada. Comprueba que sea correcta y que siga activa."
    )


class ProviderRateLimitError(ProviderError):
    default_message = (
        "Se alcanzó el límite de uso del servicio (cuota agotada). "
        "Espera a que la cuota se restablezca o revísala en el panel del proveedor. "
        "Jarvis no activa planes de pago automáticamente."
    )


class ProviderPlanError(ProviderError):
    default_message = (
        "El plan actual del servicio no permite usar esta función. "
        "En ElevenLabs, el plan gratuito no admite voces de biblioteca o "
        "profesionales mediante la API: elige una voz predefinida (premade) "
        "de tu cuenta en ELEVENLABS_VOICE_ID o revisa tu plan. "
        "Jarvis no activa planes de pago automáticamente."
    )


class ProviderNetworkError(ProviderError):
    default_message = (
        "No se pudo conectar con el servicio externo. Comprueba tu conexión a "
        "Internet e inténtalo de nuevo."
    )


class ProviderModelError(ProviderError):
    default_message = (
        "El modelo configurado no está disponible en tu cuenta. "
        "Revisa la variable de entorno del modelo en el archivo .env."
    )


class ProviderResponseError(ProviderError):
    default_message = (
        "El servicio devolvió una respuesta vacía o inesperada. Inténtalo de nuevo."
    )


class AudioError(JarvisError):
    default_message = "No se pudo utilizar el micrófono o el audio del sistema."


class AudioNotAvailableError(AudioError):
    default_message = (
        "No se detectó un micrófono disponible. Puedes seguir usando Jarvis "
        "escribiendo tus órdenes por teclado."
    )


class ConsentDeniedError(JarvisError):
    default_message = (
        "No se otorgó el consentimiento para enviar datos al servicio externo, "
        "así que la operación se canceló. Puedes seguir usando las funciones locales."
    )


_NETWORK_HINTS = (
    "timeout",
    "timed out",
    "connection",
    "connecterror",
    "network",
    "dns",
    "ssl",
    "socket",
    "httpx",
    "requests",
    "remotedisconnected",
    "proxy",
)

_RATE_LIMIT_HINTS = (
    "429",
    "rate limit",
    "rate_limit",
    "quota",
    "resource_exhausted",
    "resource exhausted",
    "too many requests",
    "limit exceeded",
)

_AUTH_HINTS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "permission",
)

_MODEL_HINTS = (
    "404",
    "model not found",
    "not_found",
    "not supported",
    "unsupported model",
    "does not exist",
)

_PLAN_HINTS = (
    "paid_plan_required",
    "payment_required",
    "payment required",
    "upgrade your subscription",
    "free users cannot",
    "plan_required",
)


def _status_code(exc: BaseException) -> int | None:
    for attribute in ("status_code", "code", "http_status"):
        value: Any = getattr(exc, attribute, None)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def classify_provider_error(exc: BaseException, provider: str) -> JarvisError:
    """Traduce una excepción del SDK a un error comprensible para el usuario."""
    if isinstance(exc, JarvisError):
        return exc

    status = _status_code(exc)
    text = f"{type(exc).__name__} {exc}".lower()
    module = type(exc).__module__ or ""

    if status == 429 or any(hint in text for hint in _RATE_LIMIT_HINTS):
        return ProviderRateLimitError(detail=f"{provider}: {type(exc).__name__}")

    if status == 402 or any(hint in text for hint in _PLAN_HINTS):
        return ProviderPlanError(detail=f"{provider}: {type(exc).__name__}")

    if status in {401, 403} or any(hint in text for hint in _AUTH_HINTS):
        return ProviderAuthError(
            f"El servicio {provider} rechazó las credenciales. "
            "Comprueba la clave de API en el archivo .env.",
            detail=f"{provider}: {type(exc).__name__}",
        )

    if status == 404 or any(hint in text for hint in _MODEL_HINTS):
        return ProviderModelError(
            f"El modelo configurado no está disponible en {provider} con esta cuenta. "
            "Revisa la variable del modelo en el archivo .env.",
            detail=f"{provider}: {type(exc).__name__}",
        )

    if module.startswith(("httpx", "requests", "urllib3", "httpcore", "socket")) or any(
        hint in text for hint in _NETWORK_HINTS
    ):
        return ProviderNetworkError(
            f"No se pudo conectar con {provider}. Comprueba tu conexión a Internet.",
            detail=f"{provider}: {type(exc).__name__}",
        )

    if status is not None and status >= 500:
        return ProviderError(
            f"{provider} informó de un problema interno (código {status}). "
            "Inténtalo de nuevo en unos minutos.",
            detail=f"{provider}: {type(exc).__name__}",
        )

    return ProviderError(
        f"Ocurrió un error al comunicarse con {provider}. "
        "Inténtalo de nuevo; si el problema continúa, revisa tu configuración.",
        detail=f"{provider}: {type(exc).__name__}",
    )
