"""Postprocesamiento de salida COMPARTIDO entre los dos caminos del agente:
el pipeline fijo (`agent.orchestrator`) y el loop agéntico
(`agent.strands_agent`). Extraído de `orchestrator.py` cuando dejó de ser
el único camino: la extracción de citas y la defensa en profundidad de
salida (`agent.guards`) tienen que correr IDÉNTICAS sin importar quién
decidió qué tool llamar y en qué orden — la garantía anti-alucinación no
puede depender de cuál de los dos caminos generó la evidencia.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path as _RutaArchivo

from second_brain.agent.guards import (
    Canary,
    canary,
    guard_urls,
    validate_citations,
    validate_relational_claims,
)
from second_brain.agent.tools import Evidence
from second_brain.ports import Answer, Citation, TraceStep

_CITATION_PATTERN = re.compile(r"\[source:([^\]]+)\]")


def entity_from_doc_id(doc_id: str) -> str:
    return _RutaArchivo(doc_id).stem


def extract_citations(text: str, evidence: list[Evidence]) -> list[Citation]:
    evidencia_por_doc_id = {item.doc_id: item for item in evidence}
    doc_ids_citados = dict.fromkeys(_CITATION_PATTERN.findall(text))
    citas = []
    for doc_id in doc_ids_citados:
        item = evidencia_por_doc_id.get(doc_id.strip())
        if item is None:
            continue
        citas.append(Citation(document=item.doc_id, fragment=item.text, chunk_id=item.chunk_id))
    return citas


def apply_guards(
    answer: Answer,
    evidence: list[Evidence],
    turn_subject: str | None,
    trace: list[TraceStep],
) -> Answer:
    """Fail-open: un guard roto queda en la traza como `guards.error` y la
    respuesta, por lo demás válida, sigue su curso sin esa capa.

    El anclaje al grafo (`validate_relational_claims`) corre DESPUÉS de
    `validate_citations` (que ya garantiza que todo `[source:doc_id]`
    citado existe en la evidencia) porque resuelve un problema distinto:
    una cita puede ser válida y la afirmación que conecta con ella, igual,
    inventada — ver el docstring de `agent.guards` para el caso completo
    (Billing 2.0 / auth-cache / ADR-017 / INC-042).

    `turn_subject` viaja explícito desde el sujeto YA resuelto por quien
    llama (`resolve_targets` en el pipeline fijo, el `target` que el
    modelo pasó a `search_documents` en el loop agéntico) en vez de que
    el guard lo vuelva a inferir de la evidencia: un vecino del blast
    radius puede llegar marcado `is_target=True` a propósito (ver
    `agent.orchestrator._reanchor_graph_neighbors`), así que "la entidad
    `is_target` más frecuente" ya no identifica de forma confiable cuál es
    el sujeto preguntado cuando hay más de un vecino con varios chunks.
    """
    try:
        answer = validate_citations(answer, evidence)
        answer, veredictos = validate_relational_claims(answer, evidence, turn_subject)
        answer = replace(answer, text=guard_urls(answer.text, evidence))
        trace.append(
            TraceStep(
                stage="guards.aplicados",
                detail=(
                    "citas y urls verificadas; "
                    f"{sum(1 for v in veredictos if v.supported)} afirmaciones relacionales "
                    f"validadas, {sum(1 for v in veredictos if not v.supported)} degradadas "
                    "por falta de evidencia"
                ),
                metadata={
                    "afirmaciones": [
                        {
                            "tipo": v.kind,
                            "sujeto": v.subject,
                            "objeto": v.object,
                            "respaldada": v.supported,
                        }
                        for v in veredictos
                    ]
                },
            )
        )
    except Exception as error:
        trace.append(TraceStep(stage="guards.error", detail=str(error)))
    return answer


def measure_canary(answer: Answer, trace: list[TraceStep]) -> Canary:
    """Fail-open: la métrica de observabilidad nunca tumba el turno; si
    falla, se reporta la falla como `abstention_form` en vez de propagar.
    """
    try:
        return canary(answer, trace)
    except Exception as error:
        return Canary(
            tool_calls=0,
            citations=len(answer.citations),
            targets_searched=[],
            targets_cited=[],
            drift=[],
            abstention_form=str(error),
        )
