"""Embeddings deterministas sin modelo ni red, para el modo 100% local.

Nada de esto pretende igualar la calidad semántica de Cohere Embed
Multilingual v3: es un *proxy* honesto para poder ensayar y testear el
pipeline entero (ingesta, búsqueda, rerank, gate) sin depender de AWS.
"""

from __future__ import annotations

import hashlib
import math

from second_brain.adapters.local.tokenization import tokenize


def _bucket_and_sign(token: str, dim: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    indice = int.from_bytes(digest[:4], byteorder="big") % dim
    signo = 1.0 if digest[4] % 2 == 0 else -1.0
    return indice, signo


class FakeEmbeddings:
    """Bag-of-words hasheado (feature hashing) a un vector L2-normalizado.

    Cada palabra del texto se proyecta a un balde de un vector de dimensión
    fija vía SHA-256; el signo del balde también sale del hash, para que las
    colisiones entre palabras distintas no sesguen sistemáticamente la suma
    hacia positivo. El resultado se normaliza a norma 1, así el producto
    punto entre dos vectores es directamente su similitud coseno.

    Esto le da la propiedad que necesita la demo: dos textos que comparten
    muchas palabras (p.ej. "María lidera el Proyecto Beta" vs "¿Quién lidera
    el Proyecto Beta?") quedan cerca en el espacio vectorial, sin entrenar
    ni descargar nada. Es reproducible por construcción: el mismo texto
    produce siempre el mismo vector.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(texto) for texto in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in tokenize(text):
            indice, signo = _bucket_and_sign(token, self.dim)
            vector[indice] += signo
        norma = math.sqrt(sum(componente * componente for componente in vector))
        if norma == 0.0:
            return vector
        return [componente / norma for componente in vector]
