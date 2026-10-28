"""Búsqueda local por palabras clave y relevancia textual.

No usa embeddings ni servicios externos: es suficiente para la primera
versión y permite que las pruebas se ejecuten sin conexión.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from jarvis.documents.chunker import Chunk
from jarvis.documents.models import DocumentModel, Section


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return re.sub(
        r"\s+",
        " ",
        "".join(char for char in decomposed if not unicodedata.combining(char)).lower(),
    ).strip()


_TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    # artículos, preposiciones y conjunciones
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "a", "ante", "bajo", "con", "contra", "en", "entre", "hacia", "hasta",
    "para", "por", "segun", "sin", "sobre", "tras", "y", "e", "o", "u", "ni",
    "que", "como", "cuando", "donde", "porque", "pues", "si", "sino",
    # pronombres y determinantes
    "yo", "tu", "el", "ella", "nosotros", "vosotros", "ellos", "me", "te",
    "se", "nos", "le", "les", "lo", "mi", "mis", "tus", "su", "sus", "este",
    "esta", "esto", "estos", "estas", "ese", "esa", "eso", "esos", "esas",
    "aquel", "aquella", "cual", "cuales", "quien", "quienes", "cuanto",
    "cuanta", "cuantos", "cuantas",
    # verbos auxiliares y comunes en preguntas
    "es", "son", "era", "eran", "fue", "fueron", "ser", "esta", "estan",
    "estar", "hay", "haber", "tiene", "tienen", "tener", "hace", "hacer",
    "puede", "pueden", "puedo", "podrias", "puedes", "debo", "debe", "deben",
    "quiero", "quisiera", "necesito", "dime", "decir", "explica", "explicar",
    "explicame", "resume", "resumir", "resumen", "muestra", "muestrame",
    "segun", "menciona", "mencionan", "mencionado", "dice", "dicen", "habla",
    "trata", "encuentra", "encuentro", "aparece", "figura", "contiene",
    "utiliza", "usar", "hacer", "hazme", "haz",
    # adverbios y cortesía
    "muy", "mas", "menos", "tambien", "solo", "solamente", "ademas",
    "brevemente", "breve", "sencillo", "sencilla", "facil", "claramente",
    "palabras", "favor", "gracias", "jarvis", "documento", "archivo",
    "manual", "texto", "parte", "cosa", "algo", "todo", "todos", "todas",
    "aqui", "ahi", "entonces", "ahora", "luego", "primero", "despues",
    "sobre", "respecto", "acerca", "exactamente", "principalmente",
    "podria", "podrian", "seria", "serian", "modo", "forma", "manera",
    "indica", "indican", "senalar", "senala", "respecta",
}


def tokenize(text: str) -> list[str]:
    """Tokens normalizados, sin acentos, sin palabras vacías y sin duplicados."""
    normalized = normalize_text(text)
    tokens = []
    seen = set()
    for token in _TOKEN_RE.findall(normalized):
        if token in STOPWORDS:
            continue
        if len(token) < 3 and not token.isdigit():
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _all_tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize_text(text))


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float
    matched_terms: frozenset[str]


class Retriever:
    """Índice TF-IDF sencillo sobre los fragmentos del documento."""

    def __init__(self, chunks: tuple[Chunk, ...] | list[Chunk]) -> None:
        self.chunks: tuple[Chunk, ...] = tuple(chunks)
        self._document_frequency: dict[str, int] = {}
        self._term_counts: list[dict[str, int]] = []
        self._heading_terms: list[set[str]] = []
        self._norms: list[float] = []

        for chunk in self.chunks:
            body_tokens = _all_tokens(chunk.text)
            heading_tokens = _all_tokens(chunk.heading_label)
            counts: dict[str, int] = {}
            for token in body_tokens:
                if token in STOPWORDS or (len(token) < 3 and not token.isdigit()):
                    continue
                counts[token] = counts.get(token, 0) + 1
            heading_terms = {
                token
                for token in heading_tokens
                if token not in STOPWORDS and (len(token) >= 3 or token.isdigit())
            }
            # Los encabezados también cuentan para la frecuencia de documento:
            # así una pregunta que coincide con el título de una sección
            # encuentra su contenido aunque el término no se repita en el cuerpo.
            for term in set(counts) | heading_terms:
                self._document_frequency[term] = self._document_frequency.get(term, 0) + 1
            self._term_counts.append(counts)
            self._heading_terms.append(heading_terms)
            self._norms.append(math.log1p(len(body_tokens) / 60.0) + 1.0)

        total = max(len(self.chunks), 1)
        self._idf: dict[str, float] = {
            term: math.log((1 + total) / (1 + frequency)) + 1.0
            for term, frequency in self._document_frequency.items()
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.01,
    ) -> list[SearchHit]:
        query_terms = tokenize(query)
        if not query_terms or not self.chunks:
            return []

        normalized_query = normalize_text(query)
        query_bigrams = {
            (query_terms[i], query_terms[i + 1]) for i in range(len(query_terms) - 1)
        }

        hits: list[SearchHit] = []
        for index, chunk in enumerate(self.chunks):
            counts = self._term_counts[index]
            heading_terms = self._heading_terms[index]
            matched = {
                term
                for term in query_terms
                if term in counts or term in heading_terms
            }
            if not matched:
                continue
            score = 0.0
            for term in matched:
                idf = self._idf.get(term, 0.5)
                occurrences = counts.get(term, 0)
                frequency_bonus = 1.0 + 0.15 * min(max(occurrences - 1, 0), 3)
                heading_bonus = 1.8 if term in heading_terms else 1.0
                score += idf * frequency_bonus * heading_bonus
            score /= self._norms[index]

            text_normalized = normalize_text(chunk.text)
            if len(normalized_query) >= 8 and normalized_query in text_normalized:
                score += 2.0

            if query_bigrams:
                chunk_tokens = _all_tokens(chunk.text)
                chunk_bigrams = {
                    (chunk_tokens[i], chunk_tokens[i + 1])
                    for i in range(len(chunk_tokens) - 1)
                }
                bigram_matches = len(query_bigrams & chunk_bigrams)
                if bigram_matches:
                    score += 0.8 * bigram_matches

            coverage = len(matched) / len(query_terms)
            score *= 0.75 + 0.5 * coverage

            if score >= min_score:
                hits.append(
                    SearchHit(
                        chunk=chunk,
                        score=round(score, 4),
                        matched_terms=frozenset(matched),
                    )
                )

        hits.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
        return hits[:top_k]


def resolve_section(document: DocumentModel, reference: str | None) -> Section | None:
    """Encuentra una sección por número de orden o por su título."""
    if not reference or not document.sections:
        return None

    cleaned = reference.strip()
    if cleaned.isdigit():
        position = int(cleaned)
        if 1 <= position <= len(document.sections):
            return document.sections[position - 1]
        return None

    target = normalize_text(cleaned)
    if not target:
        return None

    for section in document.sections:
        if normalize_text(section.title) == target:
            return section
    for section in document.sections:
        if target in normalize_text(section.title):
            return section
    for section in document.sections:
        if any(target in normalize_text(part) for part in section.path):
            return section
    return None
