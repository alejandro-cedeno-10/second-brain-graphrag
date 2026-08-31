"""Tokenizador compartido por los adapters léxicos locales (embeddings y rerank).

Vive separado para que `fake_embeddings` y `fake_rerank` usen exactamente
la misma noción de "palabra" — si divergieran, el rerank podría desempatar
distinto de como el embedding agrupó, y la demo se volvería inconsistente.
"""

from __future__ import annotations

import re

_TOKEN_PATTERN = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())
