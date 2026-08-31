"""Retrieval híbrido: semántico + léxico → fusión por rango (RRF) → rerank.

Es el patrón 1 de la charla ("retrieve-then-rerank"): ningún recuperador
individual alcanza. El semántico generaliza sobre significado pero diluye
identificadores exactos (siglas, endpoints, IDs) entre vecinos parecidos;
el léxico (BM25) encuentra esos identificadores exactos pero no entiende
paráfrasis ni sinónimos. La fusión por PUESTO (no por puntaje, las escalas
no son comparables entre métodos) los combina sin que ninguno domine, y el
rerank arbitra al final con el texto completo de cada candidato en la
mano — no solo con el solapamiento de palabras que usó el paso léxico.

`resolve_targets` es la pieza que se demuestra en el incidente 1 de la
charla: ver su docstring para el porqué de nunca desambiguar a la fuerza.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from second_brain.adapters.local.tokenization import tokenize
from second_brain.config import Stack
from second_brain.ports import Chunk, Hit, ScoredDoc

_BM25_K1 = 1.5
_BM25_B = 0.75
_TARGETS_CAP_DEFAULT = 3
_TOP_K_TARGET_CANDIDATES = 20


def search_semantic(question: str, stack: Stack, top_k: int) -> list[Hit]:
    """Recupera por similitud coseno en el vector store ya indexado del stack."""
    (question_vector,) = stack.embeddings.embed([question])
    return stack.vector_store.search(question_vector, top_k=top_k)


@dataclass
class LexicalIndex:
    """Estadísticas BM25 precalculadas sobre un conjunto fijo de chunks.

    Se precalcula una vez (no en cada `search_lexical`) porque el IDF depende
    de la frecuencia documental sobre TODO el corpus indexado, no solo de
    la pregunta de turno.
    """

    chunks: list[Chunk]
    frequencies: list[Counter[str]]
    lengths: list[int]
    idf: dict[str, float]
    average_length: float


def build_lexical_index(chunks: list[Chunk]) -> LexicalIndex:
    frequencies = [Counter(tokenize(chunk.text)) for chunk in chunks]
    lengths = [sum(frequency.values()) for frequency in frequencies]
    average_length = sum(lengths) / len(lengths) if lengths else 0.0
    documentos_con_termino: Counter[str] = Counter()
    for frequency in frequencies:
        documentos_con_termino.update(frequency.keys())
    n = len(chunks)
    idf = {
        termino: math.log((n - df + 0.5) / (df + 0.5) + 1)
        for termino, df in documentos_con_termino.items()
    }
    return LexicalIndex(chunks, frequencies, lengths, idf, average_length)


def search_lexical(question: str, lexical_index: LexicalIndex, top_k: int) -> list[Hit]:
    """BM25 propio y honesto: sin librerías, ~40 líneas, encuentra coincidencias
    léxicas exactas (IDs, siglas, nombres de endpoint) que la búsqueda
    semántica puede diluir entre vecinos de significado parecido.
    """
    question_tokens = tokenize(question)
    scored = [
        (i, _score_bm25(question_tokens, lexical_index, i))
        for i in range(len(lexical_index.chunks))
    ]
    scored.sort(key=lambda par: par[1], reverse=True)
    return [
        Hit(
            chunk_id=lexical_index.chunks[i].id,
            text=lexical_index.chunks[i].text,
            score=score,
            metadata=lexical_index.chunks[i].metadata,
        )
        for i, score in scored[:top_k]
        if score > 0
    ]


def _score_bm25(question_tokens: list[str], index: LexicalIndex, i: int) -> float:
    frequency = index.frequencies[i]
    length = index.lengths[i]
    average = index.average_length or 1.0
    score = 0.0
    for token in question_tokens:
        f = frequency.get(token, 0)
        if f == 0:
            continue
        idf = index.idf.get(token, 0.0)
        denominador = f + _BM25_K1 * (1 - _BM25_B + _BM25_B * length / average)
        score += idf * (f * (_BM25_K1 + 1)) / denominador
    return score


def fuse_rrf(rankings: list[list[Hit]], k: int = 60) -> list[Hit]:
    """Reciprocal Rank Fusion: funde varios rankings por PUESTO, no por puntaje.

    El score de BM25 y la similitud coseno no viven en la misma escala —
    uno no es una magnitud del otro — así que sumarlos o promediarlos
    crudos sesgaría la fusión hacia el método con números más grandes. El
    puesto (1º, 2º, 3º...) sí es comparable entre métodos: RRF puntúa cada
    documento por `1 / (k + puesto)` y suma esa contribución en cada
    ranking donde aparece, premiando la concordancia entre métodos por
    sobre ganar por paliza en uno solo.
    """
    puntaje_total: dict[str, float] = {}
    hit_por_id: dict[str, Hit] = {}
    for ranking in rankings:
        for puesto, hit in enumerate(ranking, start=1):
            puntaje_total[hit.chunk_id] = puntaje_total.get(hit.chunk_id, 0.0) + 1.0 / (k + puesto)
            hit_por_id.setdefault(hit.chunk_id, hit)
    ids_ordenados = sorted(hit_por_id, key=lambda chunk_id: puntaje_total[chunk_id], reverse=True)
    return [
        Hit(
            chunk_id=chunk_id,
            text=hit_por_id[chunk_id].text,
            score=puntaje_total[chunk_id],
            metadata=hit_por_id[chunk_id].metadata,
        )
        for chunk_id in ids_ordenados
    ]


def retrieve(
    question: str,
    stack: Stack,
    lexical_index: LexicalIndex,
    top_k_per_method: int = 10,
    top_n_final: int = 5,
    rrf_k: int = 60,
) -> list[ScoredDoc]:
    """Pipeline híbrido completo: semántico + léxico → RRF → rerank.

    Devuelve evidencia con su provenance intacto (`chunk_id` y `metadata`,
    con `doc_id`/`titulo_seccion`/`offset` heredados del chunk) para que
    quien consuma el resultado pueda citar la fuente exacta, no solo un
    texto suelto.
    """
    ranking_semantico = search_semantic(question, stack, top_k_per_method)
    ranking_lexico = search_lexical(question, lexical_index, top_k_per_method)
    fusionados = fuse_rrf([ranking_semantico, ranking_lexico], k=rrf_k)
    candidatos = fusionados[: max(top_k_per_method, top_n_final)]
    if not candidatos:
        return []

    documentos = [hit.text for hit in candidatos]
    resultados = stack.rerank.rerank(question, documentos, top_n=top_n_final)
    hit_por_texto = {hit.text: hit for hit in candidatos}
    for resultado in resultados:
        original = hit_por_texto.get(resultado.text)
        if original is not None:
            resultado.chunk_id = original.chunk_id
            resultado.metadata = original.metadata
    return resultados


def resolve_targets(mention: str, stack: Stack, cap: int = _TARGETS_CAP_DEFAULT) -> list[str]:
    """Resuelve una mención en lenguaje natural a uno o más `doc_id` candidatos.

    Esta es la función que sostiene el patrón "retrieve-then-rerank" del
    incidente 1 de la charla, no un accesorio de `retrieve`. La cascada:

    1. Slug exacto (`"core-billing"` == nombre corto de `servicios/core-billing.md`)
       → un único objetivo, sin ambigüedad que resolver.
    2. Match léxico fuerte: la mención contiene TODAS las palabras del
       nombre corto de un único candidato → un único objetivo.
    3. Candidatos semánticos ambiguos (ninguno de los anteriores aplicó,
       pero la búsqueda semántica trajo evidencia) → se devuelven TODOS
       los candidatos (hasta `cap`), para que el rerank arbitre con el
       texto completo en la mano.
    4. Sin evidencia semántica alguna → recién ahí, lista vacía.

    El paso 3 es deliberado y es el punto central del incidente: bajar el
    umbral de similitud hasta que un único candidato "gane" es peor que
    devolver varios, porque un candidato equivocado también puede ganar
    por margen amplio — un margen grande no es lo mismo que certeza. Por
    eso esta función JAMÁS reporta "no existe" ni le pide al llamador que
    desambigüe cuando hay al menos un candidato: eso lo hace el rerank,
    que tiene más evidencia que la sola cercanía vectorial de la mención.
    """
    candidatos = _candidates_by_doc_id(mention, stack)
    if not candidatos:
        return []

    slug_mencion = _slug(mention)
    for doc_id in candidatos:
        if _slug(_short_name(doc_id)) == slug_mencion:
            return [doc_id]

    fuertes = _strong_lexical_matches(mention, candidatos)
    if len(fuertes) == 1:
        return fuertes

    return candidatos[:cap]


def _candidates_by_doc_id(mention: str, stack: Stack) -> list[str]:
    (vector,) = stack.embeddings.embed([mention])
    hits = stack.vector_store.search(vector, top_k=_TOP_K_TARGET_CANDIDATES)
    vistos: list[str] = []
    for hit in hits:
        doc_id = hit.metadata.get("doc_id")
        if doc_id and doc_id not in vistos:
            vistos.append(doc_id)
    return vistos


def _short_name(doc_id: str) -> str:
    return Path(doc_id).stem


def _slug(text: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")


def _strong_lexical_matches(mention: str, candidatos: list[str]) -> list[str]:
    tokens_mencion = set(tokenize(mention))
    return [
        doc_id
        for doc_id in candidatos
        if (tokens_nombre := set(tokenize(_short_name(doc_id).replace("-", " "))))
        and tokens_nombre.issubset(tokens_mencion)
    ]
