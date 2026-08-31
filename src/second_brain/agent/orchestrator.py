"""El loop completo: resolver objetivos → herramientas → gate → (si procede)
síntesis anclada → guards → canario.

`answer` es un pipeline FIJO, no un loop agéntico que deje que el LLM
decida cuándo buscar: el coverage gate necesita correr ANTES de la única
llamada al LLM para poder ahorrarla del todo (`Coverage.NO_EVIDENCE`), así
que la recuperación de evidencia es siempre determinista, nunca delegada a
una decisión del modelo. El `LlmPort` se invoca una sola vez por turno, para
sintetizar — misma firma (`system`, `messages`, `tools`) sirva el adapter
local (`ScriptedLlm`, en los tests) o el de AWS (Bedrock/Strands): este
módulo no bifurca según cuál sea.

Política de fallas explícita: fail-open en los guards (una excepción ahí se
registra en la traza y se sigue con la respuesta sin validar esa capa —
un guard roto no puede tumbar un turno que por lo demás es válido);
fail-closed únicamente en el gate (sin evidencia, abstención, sin excepción
posible porque no hay nada más que evaluar).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path as _RutaArchivo

from second_brain.agent.gate import ABSTENTION_MESSAGE, Coverage, evaluate_coverage
from second_brain.agent.postprocess import apply_guards, extract_citations, measure_canary
from second_brain.agent.synthesis import SYSTEM_SYNTHESIS, build_user_message, decompose
from second_brain.agent.tools import Evidence, search_documents, traverse_graph
from second_brain.agent.trace import ObservableTrace
from second_brain.config import Stack
from second_brain.ports import Answer, TraceStep
from second_brain.retrieval import LexicalIndex, resolve_targets

_EMPTY_LEXICAL_INDEX = LexicalIndex(
    chunks=[], frequencies=[], lengths=[], idf={}, average_length=0.0
)


def answer(
    question: str,
    stack: Stack,
    lexical_index: LexicalIndex | None = None,
    on_paso: Callable[[TraceStep], None] | None = None,
) -> Answer:
    """Responde `question` con el pipeline completo de honestidad de la demo.

    `lexical_index` es opcional (y no forma parte del contrato de `Stack`,
    que no lo incluye): sin él, la recuperación cae a búsqueda semántica
    pura (RRF con un ranking léxico vacío no rompe nada, solo pierde la
    mitad del patrón retrieve-then-rerank). Quien llama con un corpus real
    ya construido — el CLI de la demo, o los tests — lo pasa explícito.

    `on_paso` es opcional y no cambia el comportamiento por defecto: si se
    pasa, se invoca con cada `TraceStep` en el momento en que el pipeline lo
    produce (no al final), para que un consumidor externo pueda mostrar
    progreso incremental (p.ej. eventos AG-UI por SSE en `demo/web/api.py`).
    """
    traza: list[TraceStep] = ObservableTrace(on_paso)
    indice = lexical_index if lexical_index is not None else _EMPTY_LEXICAL_INDEX

    objetivos = resolve_targets(question, stack)
    objetivo_principal = objetivos[0] if objetivos else None
    traza.append(
        TraceStep(
            stage="objetivos.resueltos",
            detail=f"objetivos={objetivos}",
            metadata={"objetivos": objetivos},
        )
    )

    evidencia = _collect_evidence(question, stack, indice, objetivo_principal, traza)

    cobertura = evaluate_coverage(question, evidencia)
    traza.append(
        TraceStep(
            stage="gate.cobertura",
            detail=f"cobertura={cobertura.value} ({len(evidencia)} evidencias)",
            metadata={"cobertura": cobertura.value},
        )
    )

    if cobertura is Coverage.NO_EVIDENCE:
        respuesta = _abstain(traza)
    else:
        respuesta = _synthesize(question, stack, evidencia, cobertura, traza)
        sujeto_turno = _entity_from_doc_id(objetivo_principal) if objetivo_principal else None
        respuesta = apply_guards(respuesta, evidencia, sujeto_turno, traza)

    metrica = measure_canary(respuesta, traza)
    traza.append(
        TraceStep(
            stage="canario",
            detail=(
                f"tool_calls={metrica.tool_calls} citas={metrica.citations} "
                f"drift={metrica.drift} abstencion={metrica.abstention_form}"
            ),
            metadata={
                "tool_calls": metrica.tool_calls,
                "citas": metrica.citations,
                "drift": metrica.drift,
            },
        )
    )
    return replace(respuesta, trace=list(traza))


def _collect_evidence(
    question: str,
    stack: Stack,
    index: LexicalIndex,
    target_doc_id: str | None,
    traza: list[TraceStep],
) -> list[Evidence]:
    documentos = search_documents(question, stack, index, target=target_doc_id)
    traza.append(
        TraceStep(
            stage="herramienta.buscar_documentos",
            detail=f"{len(documentos)} evidencias (objetivo={target_doc_id})",
            metadata={"objetivo": target_doc_id, "resultados": len(documentos)},
        )
    )
    if target_doc_id is None:
        return documentos

    entidad = _entity_from_doc_id(target_doc_id)
    de_grafo = _traverse_graph_fail_open(entidad, stack, traza)
    documentos = _reanchor_graph_neighbors(documentos, de_grafo)
    return [*documentos, *de_grafo]


def _traverse_graph_fail_open(
    entity: str, stack: Stack, traza: list[TraceStep]
) -> list[Evidence]:
    """Fail-open sobre el grafo: si `graph_store` no responde (FalkorDB caído
    en local, o inalcanzable en modo `aws` si el host configurado no
    responde), la pregunta se sigue respondiendo solo con la
    evidencia vectorial/léxica de `search_documents` en vez de un
    stacktrace en plena demo en vivo. Se degrada, nunca se inventa evidencia
    de grafo: el traversal fallido queda registrado en la traza
    (`herramienta.navegar_grafo.error`) para que `--trace` lo muestre, misma
    política que `agent.postprocess.apply_guards` aplica sobre los guards de salida.
    """
    try:
        de_grafo = traverse_graph(entity, stack, kind="blast_radius")
    except Exception as error:
        traza.append(
            TraceStep(
                stage="herramienta.navegar_grafo.error",
                detail=f"grafo no disponible, degradando a solo-vectorial: {error}",
                metadata={"entidad": entity},
            )
        )
        return []
    traza.append(
        TraceStep(
            stage="herramienta.navegar_grafo",
            detail=f"{len(de_grafo)} evidencias (entidad={entity})",
            metadata={"entidad": entity, "resultados": len(de_grafo)},
        )
    )
    return de_grafo


def _entity_from_doc_id(doc_id: str) -> str:
    return _RutaArchivo(doc_id).stem


def _reanchor_graph_neighbors(
    documents: list[Evidence], from_graph: list[Evidence]
) -> list[Evidence]:
    """Re-marca `is_target=True` en la evidencia documental de un vecino
    que el blast radius ya confirmó relacionado con el sujeto.

    `search_documents` solo marca `is_target` para el documento del
    sujeto preguntado: un chunk propio de `pagos` que describe en prosa su
    integración con `core-billing` (la misma relación que el grafo reporta
    como arista) llega con `is_target=False` por salir de la búsqueda
    general, no de la anclada. Sin esta corrección, esa evidencia cae en el
    bloque de COMPARACIÓN del mensaje de síntesis aunque documente
    exactamente lo que la excepción relacional (`agent.synthesis`) pide
    presentar como respuesta directa — el riesgo de que el LLM termine
    marcando un vecino del blast radius con "a diferencia de..." solo
    porque su propio documento cayó del lado equivocado.
    """
    entidades_del_grafo = {item.doc_id for item in from_graph}
    return [
        replace(item, is_target=True)
        if _entity_from_doc_id(item.doc_id) in entidades_del_grafo
        else item
        for item in documents
    ]


def _abstain(traza: list[TraceStep]) -> Answer:
    traza.append(
        TraceStep(stage="gate.abstencion", detail="sin evidencia: el LLM no fue invocado")
    )
    return Answer(text=ABSTENTION_MESSAGE, citations=[], abstained=True, trace=list(traza))


def _synthesize(
    question: str,
    stack: Stack,
    evidence: list[Evidence],
    coverage: Coverage,
    traza: list[TraceStep],
) -> Answer:
    subpreguntas = decompose(question)
    mensaje_usuario = build_user_message(question, evidence, subpreguntas, coverage)
    llm_respuesta = stack.llm.generate(
        system=SYSTEM_SYNTHESIS,
        messages=[
            {
                "role": "user",
                "content": mensaje_usuario,
                "query": question,
                "grounding_source": "\n".join(item.text for item in evidence),
            }
        ],
    )
    traza.append(
        TraceStep(
            stage="sintesis.llm",
            detail=f"detiene_por={llm_respuesta.stop_reason}",
            metadata={
                "uso_tokens": llm_respuesta.token_usage,
                "guardrail": llm_respuesta.guardrail_scores,
            },
        )
    )
    citas = extract_citations(llm_respuesta.text, evidence)
    return Answer(text=llm_respuesta.text, citations=citas, abstained=False, trace=list(traza))
