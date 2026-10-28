"""Búsqueda y apertura de documentos en la carpeta real de Descargas.

Solo se consideran archivos ``.docx`` dentro de Descargas (o sus
subcarpetas, con límites). Nunca se aceptan rutas inventadas por el modelo
ni se ejecutan comandos: la apertura es una capacidad concreta y acotada.
"""

from __future__ import annotations

import ctypes
import os
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Iterable

from jarvis.core.errors import DocumentError
from jarvis.core.logging_setup import get_logger

logger = get_logger("downloads")

MATCH = "match"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"
NO_FOLDER = "no_folder"

# {374DE290-123F-4565-9164-39C4925E467B}
_DOWNLOADS_FOLDER_ID = uuid.UUID("374DE290-123F-4565-9164-39C4925E467B")

_MAX_CANDIDATES = 6
_STOPWORDS = frozenset(
    {
        "abre",
        "abrir",
        "abreme",
        "abrirme",
        "busca",
        "buscar",
        "buscame",
        "encuentra",
        "encontrar",
        "localiza",
        "localizar",
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "de",
        "del",
        "en",
        "que",
        "se",
        "llama",
        "llamado",
        "llamada",
        "titulado",
        "titulada",
        "documento",
        "documentos",
        "archivo",
        "archivos",
        "docx",
        "word",
        "por",
        "favor",
        "descargas",
        "descarga",
        "carpeta",
        "mi",
        "mis",
        "y",
    }
)


class _Guid(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def windows_downloads_folder() -> Path | None:
    """Carpeta de Descargas según Windows (``FOLDERID_Downloads``)."""
    if sys.platform != "win32":
        return None
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        ole32 = ctypes.WinDLL("ole32", use_last_error=True)
        guid = _Guid.from_buffer_copy(_DOWNLOADS_FOLDER_ID.bytes_le)
        path_ptr = ctypes.c_wchar_p()
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_Guid),
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

        result = shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(path_ptr)
        )
        if result != 0 or not path_ptr.value:
            logger.warning("SHGetKnownFolderPath devolvió el código %s", result)
            return None
        try:
            return Path(path_ptr.value)
        finally:
            ole32.CoTaskMemFree(path_ptr)
    except Exception as exc:  # pragma: no cover - depende de Windows
        logger.warning("No se pudo obtener la carpeta Descargas: %s", type(exc).__name__)
        return None


def _fallback_folders() -> list[Path]:
    folders: list[Path] = []
    home = Path.home()
    folders.extend([home / "Downloads", home / "Descargas"])
    profile = os.environ.get("USERPROFILE")
    if profile:
        folders.extend([Path(profile) / "Downloads", Path(profile) / "Descargas"])
    unique: list[Path] = []
    for folder in folders:
        if folder not in unique:
            unique.append(folder)
    return unique


def normalize_name(text: str) -> str:
    """Minúsculas, sin acentos, sin extensión y con separadores unificados."""
    value = Path(text).stem if text.lower().endswith(".docx") else text
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    value = without_accents.casefold()
    value = re.sub(r"[_\-]+", " ", value)
    value = re.sub(r"[^a-z0-9ñ ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _keywords(normalized: str) -> str:
    tokens = [token for token in normalized.split() if token not in _STOPWORDS]
    return " ".join(tokens)


def score_name(query: str, filename: str) -> float:
    """Puntuación 0..1 entre una orden hablada y un nombre de archivo."""
    query_norm = normalize_name(query)
    name_norm = normalize_name(filename)
    if not query_norm or not name_norm:
        return 0.0

    query_key = _keywords(query_norm) or query_norm
    name_key = _keywords(name_norm) or name_norm
    if query_norm == name_norm:
        return 1.0

    ratio = SequenceMatcher(None, query_key, name_key).ratio()
    query_tokens = set(query_key.split())
    name_tokens = set(name_key.split())
    if not query_tokens:
        return 0.0
    recall = len(query_tokens & name_tokens) / len(query_tokens)
    score = 0.6 * ratio + 0.4 * recall

    if query_key in name_key or name_key in query_key:
        score = max(score, 0.93)
    elif query_tokens <= name_tokens:
        score = max(score, 0.90)
    return round(min(1.0, score), 4)


@dataclass(frozen=True)
class DocumentMatch:
    path: Path
    score: float
    relative: str

    @property
    def display(self) -> str:
        return f"{self.path.stem} ({self.score:.2f})"


@dataclass(frozen=True)
class SearchResult:
    query: str
    root: Path | None
    matches: tuple[DocumentMatch, ...] = ()
    decision: str = NOT_FOUND
    warning: str | None = None
    truncated: bool = False

    @property
    def best(self) -> DocumentMatch | None:
        return self.matches[0] if self.matches else None

    @property
    def selected(self) -> DocumentMatch | None:
        """Coincidencia segura; ``None`` si hay que preguntar."""
        return self.best if self.decision == MATCH else None

    @property
    def candidates(self) -> tuple[DocumentMatch, ...]:
        return self.matches[:_MAX_CANDIDATES]

    @property
    def is_confident(self) -> bool:
        return self.decision == MATCH

    def describe(self) -> str:
        if self.decision == NO_FOLDER:
            return self.warning or "No se encontró la carpeta de Descargas."
        if self.decision == NOT_FOUND:
            return (
                self.warning
                or "No encontré ningún documento .docx con ese nombre en Descargas."
            )
        if self.decision == AMBIGUOUS:
            options = ", ".join(match.path.stem for match in self.candidates)
            return f"Encontré varios documentos parecidos: {options}. ¿Cuál quieres?"
        return f"Documento encontrado: {self.best.path.name if self.best else ''}."


class DownloadsLibrary:
    """Busca y abre documentos autorizados de Descargas."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        max_depth: int = 3,
        max_files: int = 2_000,
        min_score: float = 0.50,
        auto_score: float = 0.86,
        margin: float = 0.08,
        known_folder: Callable[[], Path | None] | None = None,
        opener: Callable[[Path], None] | None = None,
    ) -> None:
        self._explicit_root = Path(root) if root is not None else None
        self.max_depth = max(0, int(max_depth))
        self.max_files = max(1, int(max_files))
        self.min_score = float(min_score)
        self.auto_score = float(auto_score)
        self.margin = float(margin)
        self._known_folder = known_folder or windows_downloads_folder
        self._opener = opener
        self._resolved: Path | None = None
        self._resolved_once = False
        self.root_warning: str | None = None

    # ------------------------------------------------------------------
    # Carpeta raíz
    # ------------------------------------------------------------------
    @property
    def root(self) -> Path | None:
        if not self._resolved_once:
            self._resolved = self._resolve_root()
            self._resolved_once = True
        return self._resolved

    def _resolve_root(self) -> Path | None:
        if self._explicit_root is not None:
            if self._explicit_root.is_dir():
                return self._explicit_root
            self.root_warning = (
                f"La carpeta indicada no existe o no es accesible: "
                f"{self._explicit_root}"
            )
            return None

        candidates: list[Path] = []
        try:
            known = self._known_folder()
        except Exception:  # pragma: no cover - API del sistema
            known = None
        if known is not None:
            candidates.append(known)
        candidates.extend(_fallback_folders())

        for folder in candidates:
            try:
                if folder.is_dir():
                    return folder
            except OSError:
                continue

        self.root_warning = (
            "No se encontró la carpeta de Descargas. Se buscó en: "
            + ", ".join(str(folder) for folder in candidates[:4])
        )
        return None

    def refresh_root(self) -> Path | None:
        self._resolved_once = False
        return self.root

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------
    def search(self, query: str | None) -> SearchResult:
        clean_query = (query or "").strip()
        root = self.root
        if root is None:
            return SearchResult(
                query=clean_query,
                root=None,
                decision=NO_FOLDER,
                warning=self.root_warning,
            )
        if not clean_query:
            return SearchResult(
                query=clean_query,
                root=root,
                decision=NOT_FOUND,
                warning="Dime el nombre del documento que quieres abrir.",
            )

        files, truncated = self._collect(root)
        scored: list[DocumentMatch] = []
        for path in files:
            value = score_name(clean_query, path.name)
            if value < self.min_score:
                continue
            try:
                relative = str(path.relative_to(root))
            except ValueError:  # pragma: no cover - defensivo
                relative = path.name
            scored.append(DocumentMatch(path=path, score=value, relative=relative))

        scored.sort(key=lambda match: (-match.score, match.path.name.casefold()))
        matches = tuple(scored[:_MAX_CANDIDATES])
        warning = None
        if truncated:
            warning = (
                f"Se alcanzó el límite de {self.max_files} archivos revisados; "
                "la búsqueda puede estar incompleta."
            )

        if not matches:
            return SearchResult(
                query=clean_query,
                root=root,
                decision=NOT_FOUND,
                warning=warning,
                truncated=truncated,
            )

        best = matches[0]
        second = matches[1] if len(matches) > 1 else None
        clear = best.score >= self.auto_score and (
            second is None or best.score - second.score >= self.margin
        )
        return SearchResult(
            query=clean_query,
            root=root,
            matches=matches,
            decision=MATCH if clear else AMBIGUOUS,
            warning=warning,
            truncated=truncated,
        )

    def _collect(self, root: Path) -> tuple[list[Path], bool]:
        found: list[Path] = []
        pending: list[tuple[Path, int]] = [(root, 0)]
        while pending:
            folder, depth = pending.pop()
            try:
                entries: Iterable[os.DirEntry] = os.scandir(folder)
            except OSError:
                continue
            with entries as iterator:
                for entry in iterator:
                    name = entry.name
                    if name.startswith(("~$", ".")):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < self.max_depth:
                                pending.append((Path(entry.path), depth + 1))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    if Path(name).suffix.casefold() != ".docx":
                        continue
                    if len(found) >= self.max_files:
                        return found, True
                    found.append(Path(entry.path))
        return found, False

    # ------------------------------------------------------------------
    # Apertura controlada
    # ------------------------------------------------------------------
    def is_allowed(self, path: Path | str) -> bool:
        root = self.root
        if root is None:
            return False
        try:
            candidate = Path(path).resolve(strict=True)
            base = root.resolve(strict=True)
        except (OSError, RuntimeError):
            return False
        if candidate.suffix.casefold() != ".docx":
            return False
        if not candidate.is_file():
            return False
        try:
            candidate.relative_to(base)
        except ValueError:
            return False
        return True

    def open_document(self, path: Path | str) -> Path:
        """Abre el documento con su aplicación predeterminada de Windows."""
        candidate = Path(path)
        if not self.is_allowed(candidate):
            raise DocumentError(
                "Por seguridad, Jarvis solo abre archivos .docx que estén "
                "dentro de la carpeta de Descargas."
            )
        opener = self._opener or _system_opener
        try:
            opener(candidate)
        except DocumentError:
            raise
        except OSError as exc:
            raise DocumentError(
                "El documento está cargado, pero Windows no pudo abrirlo con "
                "su aplicación predeterminada. Ábrelo manualmente desde Descargas.",
                detail=type(exc).__name__,
            ) from exc
        logger.info("Documento abierto desde Descargas: %s", candidate.name)
        return candidate


def _system_opener(path: Path) -> None:
    if sys.platform != "win32":
        raise DocumentError(
            "Abrir archivos con la aplicación predeterminada solo está "
            "disponible en Windows."
        )
    os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
