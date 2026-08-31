"""Rerank determinista por solapamiento léxico, para el modo 100% local.

Es un proxy honesto de Cohere Rerank 3.5: no entiende semántica más allá de
qué palabras comparten la pregunta y el documento. Alcanza para que el
pipeline y sus gates se puedan testear de punta a punta sin red, pero NO
es una alternativa de calidad al cross-encoder real — no usarlo como tal
fuera de tests/ensayos offline.
"""

from __future__ import annotations

import math
from collections import Counter

from second_brain.adapters.local.tokenization import tokenize
from second_brain.ports import ScoredDoc


class FakeRerank:
    """Puntúa cada documento por solapamiento de tokens con la pregunta.

    El solapamiento (suma de mínimos por token, tipo intersección
    ponderada por frecuencia) se divide por el logaritmo del largo del
    documento para no premiar documentos largos solo por tener más
    palabras en común por pura extensión.
    """

    def rerank(self, question: str, documents: list[str], top_n: int) -> list[ScoredDoc]:
        tokens_pregunta = Counter(tokenize(question))
        puntuados = [self._score(tokens_pregunta, documento) for documento in documents]
        puntuados.sort(key=lambda doc: doc.score, reverse=True)
        return puntuados[:top_n]

    def _score(self, question_tokens: Counter[str], document: str) -> ScoredDoc:
        tokens_documento = Counter(tokenize(document))
        solapamiento = sum(
            min(cantidad, tokens_documento[token]) for token, cantidad in question_tokens.items()
        )
        penalizacion_largo = 1.0 + math.log(1 + len(tokens_documento))
        score = solapamiento / penalizacion_largo
        return ScoredDoc(text=document, score=score)
