"""EL COVERAGE GATE: decide si hay evidencia para intentar responder ANTES
de gastar un solo token de LLM.

Es la primera y más barata capa del patrón "defensa en profundidad" que la
charla nombra (ver también `agent.guards`, las capas de salida que corren
DESPUÉS de la síntesis): correr determinista y gratis ANTES del LLM es lo
que le permite a este gate ahorrar la invocación entera, no solo recortar
su resultado.

Es la capa que ahorra tokens Y alucinación al mismo tiempo: sin evidencia,
no hay nada que el modelo pueda decir que no sea inventado, así que ni se lo
invoca (`Coverage.NO_EVIDENCE`, fail-closed — es la ÚNICA función de este
paquete con esa política; todo lo demás es fail-open). Con evidencia parcial,
se contesta lo que hay y se declara el vacío en vez de forzar una respuesta
completa que no está sostenida.

Determinista, sin LLM, en dos pasos:

1. `RELEVANT_SCORE_THRESHOLD` separa la evidencia genuinamente relevante del
   ruido de solapamiento de palabras comunes que cualquier score de
   similitud arrastra incluso para una pregunta sin documento que la
   responda (ver el docstring de la constante para los números reales).
2. Sobre la evidencia relevante, se mide CUÁNTAS FACETAS de la pregunta
   quedan cubiertas (una pregunta con "y" puede pedir dos cosas, como la P4
   de la demo: quién es la CTO Y cuánto gana). Todas las facetas cubiertas
   es `SUFFICIENT`; alguna sin cobertura es `PARTIAL`; ninguna es
   `NO_EVIDENCE`, aunque haya pasado el umbral de score.

El tercer factor de la consigna — "si el grafo conoce las entidades
nombradas" — no es un chequeo aparte: entra por la puerta del paso 1, porque
`agent.tools.traverse_graph` le pone a cada salto de grafo un score fijo
(`_GRAPH_EVIDENCE_SCORE`) por encima del umbral. Una relación que el grafo
confirma siempre cuenta como evidencia relevante para su faceta.
"""

from __future__ import annotations

from enum import StrEnum

from second_brain.adapters.local.tokenization import tokenize
from second_brain.agent.facets import split_into_facets
from second_brain.agent.tools import Evidence

RELEVANT_SCORE_THRESHOLD = 0.55
"""Calibrado contra el corpus real de la demo con los adapters locales
(`FakeEmbeddings` + `FakeRerank`, ver `tests/test_agent.py::test_gate_*`):
las preguntas con documento real que las responde traen su mejor score
por encima de 0.68; la única sin documento ("¿Cuál fue la facturación del
Q4 2025?") no supera 0.54 ni buscando en todo el corpus ni en el
documento que el resolver de objetivos erróneamente le asigna. 0.55
separa limpio ambos grupos. Re-verificado al ampliar el corpus de 10 a
~50 documentos (ver `agent.tools.search_documents`, que también
recalibró su recall junto con este número): el techo de ruido subió de
~0.53 a ~0.54 con más documentos compitiendo por palabras comunes, pero
sigue por debajo de 0.55. Si el corpus vuelve a crecer, este número se
vuelve a calibrar con el mismo método: no es una constante universal de
FakeRerank.
"""

_COVERAGE_STOPWORDS = {
    "que", "qué", "quien", "quién", "quienes", "quiénes", "cual", "cuál",
    "cuales", "cuáles", "cuanto", "cuánto", "cuanta", "cuánta", "como",
    "cómo", "cuando", "cuándo", "donde", "dónde", "por", "para", "de", "del",
    "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "u",
    "es", "son", "fue", "fueron", "ser", "esta", "está", "se", "no", "si",
    "sí", "en", "con", "a", "al", "su", "sus", "le", "les", "lo", "mi", "tu",
}
"""Palabras funcionales del español que no aportan señal de cobertura: sin
esto, casi cualquier evidencia "cubriría" cualquier faceta solo por
compartir artículos y preposiciones.
"""


class Coverage(StrEnum):
    """Los tres veredictos del gate, en orden de qué tanto se puede decir."""

    NO_EVIDENCE = "sin_evidencia"
    PARTIAL = "parcial"
    SUFFICIENT = "suficiente"


ABSTENTION_MESSAGE = (
    "No encontré evidencia suficiente en la base de conocimiento indexada "
    "para responder esta pregunta. No voy a inventar una respuesta."
)
"""Vive acá (no en `agent.orchestrator`) porque los DOS caminos del agente
—el pipeline fijo y el loop agéntico de `agent.strands_agent`— la usan: es
el texto que produce el gate, sin importar si lo evalúa `orchestrator.answer`
antes de la única llamada al LLM o `agent.gate_hook.CoverageGateHook` sobre
`AfterToolsEvent`, después de que las tools ya corrieron.
"""


def evaluate_coverage(question: str, evidence: list[Evidence]) -> Coverage:
    """Clasifica la evidencia de un turno sin invocar ningún LLM.

    Ver el docstring del módulo para el porqué de los dos pasos (umbral de
    score, después cobertura por faceta).
    """
    relevant = [item for item in evidence if item.score >= RELEVANT_SCORE_THRESHOLD]
    if not relevant:
        return Coverage.NO_EVIDENCE

    words_in_evidence = set(tokenize(" ".join(item.text for item in relevant)))
    facets = split_into_facets(question) or [question]
    covered = sum(1 for facet in facets if _facet_covered(facet, words_in_evidence))

    if covered == 0:
        return Coverage.NO_EVIDENCE
    if covered == len(facets):
        return Coverage.SUFFICIENT
    return Coverage.PARTIAL


def _facet_covered(facet: str, words_in_evidence: set[str]) -> bool:
    keywords = [t for t in tokenize(facet) if t not in _COVERAGE_STOPWORDS]
    if not keywords:
        return True
    return any(palabra in words_in_evidence for palabra in keywords)
