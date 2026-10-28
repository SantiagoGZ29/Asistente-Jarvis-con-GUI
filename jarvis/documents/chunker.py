"""Fragmentación del documento y agrupación para resúmenes."""

from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis.documents.models import DocumentModel, Paragraph, TableBlock

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;:])\s+")


@dataclass(frozen=True)
class Chunk:
    """Fragmento manejable del documento con su fuente original."""

    chunk_id: str
    block_ids: tuple[str, ...]
    heading_path: tuple[str, ...]
    text: str
    kind: str = "texto"

    @property
    def heading_label(self) -> str:
        return " > ".join(self.heading_path) if self.heading_path else "Sin encabezado"

    @property
    def prompt_text(self) -> str:
        if self.heading_path:
            return f"Encabezado: {self.heading_label}\n{self.text}"
        return self.text

    @property
    def char_count(self) -> int:
        return len(self.text)


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Divide un párrafo demasiado largo respetando frases cuando se puede."""
    if len(text) <= max_chars:
        return [text]

    pieces: list[str] = []
    sentences = _SENTENCE_SPLIT_RE.split(text)
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                pieces.append(current.strip())
                current = ""
            for start in range(0, len(sentence), max_chars):
                pieces.append(sentence[start : start + max_chars].strip())
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current.strip())
    return [piece for piece in pieces if piece]


def _chunk_id(number: int) -> str:
    return f"C{number}"


def chunk_document(document: DocumentModel, max_chars: int = 1200) -> tuple[Chunk, ...]:
    """Convierte el documento en fragmentos que conservan su encabezado y fuente."""
    if max_chars <= 0:
        raise ValueError("max_chars debe ser mayor que cero")

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_blocks: list[str] = []
    buffer_heading: tuple[str, ...] = ()

    def flush() -> None:
        nonlocal buffer, buffer_blocks, buffer_heading
        text = "\n".join(part for part in buffer if part).strip()
        if not text:
            buffer = []
            buffer_blocks = []
            return
        chunks.append(
            Chunk(
                chunk_id=_chunk_id(len(chunks) + 1),
                block_ids=tuple(dict.fromkeys(buffer_blocks)),
                heading_path=buffer_heading,
                text=text,
                kind="texto",
            )
        )
        buffer = []
        buffer_blocks = []

    for block in document.blocks:
        if isinstance(block, Paragraph):
            if block.heading_level is not None:
                # Los títulos se usan como contexto del fragmento, no como
                # contenido independiente.
                if buffer:
                    flush()
                buffer_heading = block.heading_path
                continue

            if buffer_heading != block.heading_path and buffer:
                flush()
            buffer_heading = block.heading_path

            if len(block.text) > max_chars:
                if buffer:
                    flush()
                for piece in _split_long_text(block.text, max_chars):
                    chunks.append(
                        Chunk(
                            chunk_id=_chunk_id(len(chunks) + 1),
                            block_ids=(block.id,),
                            heading_path=block.heading_path,
                            text=piece,
                            kind="texto",
                        )
                    )
                continue

            current_size = sum(len(part) + 1 for part in buffer)
            if buffer and current_size + len(block.text) > max_chars:
                flush()
            buffer.append(block.text)
            buffer_blocks.append(block.id)
        elif isinstance(block, TableBlock):
            if buffer:
                flush()
            rows = block.rows
            if not rows:
                continue
            start = 0
            while start < len(rows):
                end = start + 1
                while end < len(rows):
                    candidate = block.rows_as_text(start, end + 1)
                    if len(candidate) > max_chars:
                        break
                    end += 1
                text = block.rows_as_text(start, end)
                if not text:
                    start = end
                    continue
                chunks.append(
                    Chunk(
                        chunk_id=_chunk_id(len(chunks) + 1),
                        block_ids=(block.id,),
                        heading_path=block.heading_path,
                        text=text,
                        kind="tabla",
                    )
                )
                start = end

    flush()
    for chunk in chunks:
        if not chunk.block_ids:  # pragma: no cover - salvaguarda
            raise ValueError("Se generó un fragmento sin fuente asociada")
    return tuple(chunks)


def batch_chunks(chunks: tuple[Chunk, ...] | list[Chunk], max_chars: int) -> list[list[Chunk]]:
    """Agrupa fragmentos sin superar el límite de caracteres por lote."""
    if max_chars <= 0:
        raise ValueError("max_chars debe ser mayor que cero")
    batches: list[list[Chunk]] = []
    current: list[Chunk] = []
    current_size = 0
    for chunk in chunks:
        size = chunk.char_count + 2
        if current and current_size + size > max_chars:
            batches.append(current)
            current = []
            current_size = 0
        current.append(chunk)
        current_size += size
    if current:
        batches.append(current)
    return batches


def chunks_for_heading(
    chunks: tuple[Chunk, ...] | list[Chunk], heading_path: tuple[str, ...]
) -> list[Chunk]:
    """Fragmentos que pertenecen a una sección (mismo prefijo de encabezados)."""
    if not heading_path:
        return []
    depth = len(heading_path)
    selected = [
        chunk
        for chunk in chunks
        if chunk.heading_path[:depth] == heading_path
    ]
    return selected
