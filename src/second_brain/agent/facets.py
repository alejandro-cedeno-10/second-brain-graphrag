"""Partir una pregunta en facetas por la conjunción "y": lo necesitan tanto
el gate (cobertura por faceta) como la síntesis (anclar cada faceta a su
sujeto) — vive acá, separado, para que las dos no arriesguen divergir con
regexes parecidos pero no idénticos.
"""

from __future__ import annotations

import re

_CONJUNCTION_PATTERN = re.compile(r"\by\b", re.IGNORECASE)
_EDGE_PATTERN = re.compile(r"^[¿¡\s]+|[?!.\s]+$")


def split_into_facets(question: str) -> list[str]:
    """Corta `question` en cláusulas por " y ", limpiando signos de apertura/cierre.

    Una pregunta sin " y " devuelve una única faceta (la pregunta entera,
    limpia de `¿?¡!`), que es el caso común (P1, P2, P3, P5 de la demo).
    """
    piezas = _CONJUNCTION_PATTERN.split(question)
    facetas = [_EDGE_PATTERN.sub("", pieza).strip() for pieza in piezas]
    return [faceta for faceta in facetas if faceta]
