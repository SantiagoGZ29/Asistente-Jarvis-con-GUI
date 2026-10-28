"""Enumeración y selección de micrófonos de Windows.

No se asume nada sobre el dispositivo predeterminado ni sobre su frecuencia
de muestreo: cada dispositivo declara la suya y la capa de captura decide
si puede abrir directamente a 16 kHz o si debe remuestrear.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis.core.logging_setup import get_logger

logger = get_logger("devices")

WINDOWS_PRIVACY_HINT = (
    "Si Windows bloquea el micrófono, abre Configuración > Privacidad y "
    "seguridad > Micrófono, activa «Acceso al micrófono» y «Permitir que las "
    "aplicaciones de escritorio accedan al micrófono», y vuelve a intentarlo."
)


@dataclass(frozen=True)
class InputDevice:
    """Dispositivo de entrada tal como lo describe PortAudio."""

    index: int
    name: str
    hostapi: str
    channels: int
    default_samplerate: int
    is_default: bool = False

    @property
    def key(self) -> str:
        """Identificador estable entre reinicios (el índice no lo es)."""
        return f"{self.hostapi}|{self.name}|{self.index}"

    @property
    def identity(self) -> str:
        """Identificador sin índice: sirve para reencontrar el dispositivo."""
        return f"{self.hostapi}|{self.name}"

    @property
    def label(self) -> str:
        suffix = " · predeterminado" if self.is_default else ""
        return f"{self.name} — {self.hostapi}{suffix}"

    @property
    def short_label(self) -> str:
        return self.name


def _backend(backend: Any | None) -> Any:
    if backend is not None:
        return backend
    import sounddevice  # importación diferida: la GUI debe abrir sin audio

    return sounddevice


def _field(device: Any, name: str, default: Any = None) -> Any:
    if isinstance(device, dict):
        return device.get(name, default)
    return getattr(device, name, default)


def default_input_index(backend: Any | None = None) -> int | None:
    """Índice del dispositivo de entrada predeterminado, si existe."""
    sound = _backend(backend)
    try:
        configured = sound.default.device
    except Exception:  # pragma: no cover - backend incompleto
        return None
    if configured is None:
        return None
    if isinstance(configured, (list, tuple)):
        if not configured:
            return None
        configured = configured[0]
    else:
        # sounddevice 0.5 usa ``_InputOutputPair``: admite ``pair["input"]``
        # pero no es una tupla ni una lista.
        try:
            configured = configured["input"]
        except (TypeError, KeyError, IndexError):
            pass
    try:
        index = int(configured)
    except (TypeError, ValueError):
        return None
    return index if index >= 0 else None


def list_input_devices(backend: Any | None = None) -> tuple[InputDevice, ...]:
    """Lista los dispositivos con canales de entrada.

    Devuelve una tupla vacía si PortAudio no puede enumerar; el llamador
    debe tratar ese caso como «sin dispositivo», no como éxito.
    """
    sound = _backend(backend)
    try:
        raw_devices = sound.query_devices()
        hostapis = sound.query_hostapis()
    except Exception as exc:
        logger.warning("No se pudieron enumerar dispositivos: %s", type(exc).__name__)
        return ()

    default_index = default_input_index(sound)
    hosts = [
        str(_field(api, "name", "Host API")) for api in hostapis
    ]
    devices: list[InputDevice] = []
    for index, raw in enumerate(raw_devices):
        channels = int(_field(raw, "max_input_channels", 0) or 0)
        if channels <= 0:
            continue
        host_index = int(_field(raw, "hostapi", 0) or 0)
        host_name = hosts[host_index] if 0 <= host_index < len(hosts) else "Host API"
        samplerate = float(_field(raw, "default_samplerate", 0) or 0)
        devices.append(
            InputDevice(
                index=index,
                name=str(_field(raw, "name", f"Micrófono {index}")),
                hostapi=host_name,
                channels=channels,
                default_samplerate=int(round(samplerate)) or 16_000,
                is_default=index == default_index,
            )
        )
    return tuple(devices)


def resolve_device(
    devices: tuple[InputDevice, ...] | list[InputDevice],
    saved_key: str | None,
) -> InputDevice | None:
    """Reencuentra el dispositivo guardado, tolerando un índice distinto."""
    if not saved_key:
        return None
    saved_key = saved_key.strip()
    for device in devices:
        if device.key == saved_key:
            return device

    # El índice cambia entre reinicios y al conectar auriculares: se compara
    # por host API + nombre, y si hay duplicados se conserva el primero.
    identity = saved_key
    if "|" in saved_key:
        head, _, tail = saved_key.rpartition("|")
        if tail.isdigit():
            identity = head
    for device in devices:
        if device.identity == identity:
            return device

    name = identity.split("|", 1)[-1].strip()
    if name:
        wanted = name.casefold()
        for device in devices:
            if device.name.casefold() == wanted:
                return device
    return None


def startup_device(
    saved_key: str | None = None,
    *,
    devices: tuple[InputDevice, ...] | None = None,
    backend: Any | None = None,
) -> tuple[InputDevice | None, str | None]:
    """Elige el micrófono del arranque y explica cualquier incidencia.

    Devuelve ``(dispositivo, aviso)``. El aviso nunca impide arrancar: la
    aplicación sigue en modo texto y el usuario puede elegir otro micrófono.
    """
    found = devices if devices is not None else list_input_devices(backend)
    if not found:
        return None, (
            "No se detectó ningún micrófono. Puedes seguir escribiendo tus "
            "órdenes por teclado."
        )

    if saved_key:
        remembered = resolve_device(found, saved_key)
        if remembered is not None:
            return remembered, None
        fallback = next((device for device in found if device.is_default), found[0])
        return fallback, (
            "El micrófono guardado ya no está disponible. Se usará "
            f"«{fallback.short_label}»; puedes cambiarlo en Ajustes."
        )

    preferred = next((device for device in found if device.is_default), found[0])
    return preferred, None


def explain_audio_error(exc: BaseException, device: InputDevice | None = None) -> str:
    """Traduce un fallo de PortAudio a una instrucción útil en español."""
    text = f"{type(exc).__name__} {exc}".lower()
    where = f" en «{device.short_label}»" if device is not None else ""

    if any(
        hint in text
        for hint in (
            "permission",
            "denied",
            "access is denied",
            "eacces",
            "not allowed",
            "privacy",
        )
    ):
        return f"Windows no permite acceder al micrófono{where}. {WINDOWS_PRIVACY_HINT}"

    if "device unavailable" in text or "unavailable" in text or "-9985" in text:
        return (
            f"El micrófono{where} está en uso por otra aplicación o se ha "
            "desconectado. Cierra la otra aplicación, comprueba el cable o "
            "elige otro dispositivo."
        )

    if "invalid device" in text or "-9996" in text:
        return (
            "El micrófono seleccionado ya no existe. Elige otro dispositivo "
            "en la lista de entrada."
        )

    if "unanticipated" in text or "-9999" in text:
        return (
            f"Windows no pudo abrir el micrófono{where}. Puede ser un problema "
            f"de permisos o que otra aplicación lo esté usando. {WINDOWS_PRIVACY_HINT}"
        )

    if "invalid sample rate" in text or "-9997" in text:
        return (
            f"El micrófono{where} no admite la frecuencia solicitada. "
            "Jarvis probará otra frecuencia automáticamente; si persiste, "
            "selecciona otro dispositivo."
        )

    if "invalid number of channels" in text or "-9998" in text:
        return (
            "El micrófono no admite captura mono. Selecciona otro dispositivo "
            "de entrada."
        )

    if "no default input device" in text or "no default" in text:
        return (
            "Windows no tiene un micrófono predeterminado. Conéctalo y "
            "selecciónalo en Configuración > Sistema > Sonido."
        )

    return (
        f"No se pudo abrir el micrófono{where}. Comprueba que esté conectado y "
        "que otra aplicación no lo esté usando. Puedes seguir por teclado."
    )
