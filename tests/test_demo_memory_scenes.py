"""Las tres escenas de memoria del guion LOCAL agéntico (Acto 4, ver
`GUION_ACTO4_MEMORIA.md`): M1 (seguimiento anafórico, STM), M2 (preferencia
cambia forma) y M3 (memoria mentirosa degradada por el anclaje al grafo).

A diferencia de `tests/test_strands_agent_memory.py` (que arma sus propios
`ScriptedRule` a mano para probar el CABLEADO de memoria en el camino
agéntico), este archivo ejercita el GUION REAL que arma
`demo.build_agentic_scripted_llm` — el mismo que corre `demo.py query`/`chat`
en modo local — para que estas tres escenas queden deterministas sin AWS
(ver `openspec/changes/agregar-memoria-second-brain/tasks.md`, 8.3/8.4).

Cubre, con comportamiento OBSERVABLE (traza + texto + citas), que:
- El guion decide llamar `recall_memory` en las tres escenas (`P_M1_SEGUIMIENTO`
  y `P_BILLING` bajo memoria activa), y NUNCA para una pregunta ajena (P1),
  aunque memoria esté activa para el turno.
- M3: el hecho falso recuperado de memoria queda DEGRADADO por el mismo
  anclaje al grafo que degradaría una alucinación del modelo — nunca citado
  como si viniera de "memoria".
- M2: la preferencia cambia el FORMATO (texto más corto, sin desarrollar
  ADR-017/INC-042 en prosa) sin tocar ni los hechos ni las 4 citas.
- M1: dentro de un mismo proceso (como `demo.py chat`), la STM del turno 1
  resuelve el referente del turno 2 sin que la pregunta nombre el sujeto.
- Sin `actor_id`/`session_id` explícitos (tercera capa de activación), o sin
  `stack.memory` configurado, ninguna de las tres escenas se activa: el
  guion se comporta byte a byte como si memoria no existiera.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_memory_store import FakeMemoryStore
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.memory_graph_store import MemoryGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.agent.strands_agent import answer_agentic
from second_brain.config import Stack
from second_brain.graph.build import build_graph
from second_brain.ingestion import chunk_document, index, load_corpus
from second_brain.ports import Answer, TraceStep
from second_brain.retrieval import LexicalIndex, build_lexical_index

RUTA_CORPUS = Path(__file__).resolve().parent.parent / "corpus"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo import (  # noqa: E402
    P2,
    P_BILLING,
    P_M1_SEGUIMIENTO,
    SEMILLA_M2_PREFERENCIA,
    SEMILLA_M3_HECHO_FALSO,
    TEXTO_M1_SEGUIMIENTO,
    TEXTO_P_BILLING_CON_PREFERENCIA,
    TEXTO_P_BILLING_INGENUO,
    build_agentic_scripted_llm,
)

P1 = "¿Quién lidera el Proyecto Beta?"


def _stack_and_corpus() -> tuple[Stack, LexicalIndex]:
    stack = Stack(
        embeddings=FakeEmbeddings(),
        vector_store=MemoryVectorStore(),
        graph_store=MemoryGraphStore(),
        rerank=FakeRerank(),
        llm=None,
    )
    corpus = load_corpus(RUTA_CORPUS)
    index(corpus, stack)
    todos_los_chunks = [chunk for doc in corpus for chunk in chunk_document(doc)]
    indice = build_lexical_index(todos_los_chunks)
    build_graph(RUTA_CORPUS, stack)
    return stack, indice


def _step(trace: list[TraceStep], stage: str) -> TraceStep | None:
    return next((paso for paso in trace if paso.stage == stage), None)


def _afirmaciones(respuesta: Answer) -> list[dict[str, Any]]:
    paso = _step(respuesta.trace, "guards.aplicados")
    return list((paso.metadata or {}).get("afirmaciones", [])) if paso else []


def _con_memoria_activa(actor_id: str, session_id: str) -> tuple[Stack, LexicalIndex]:
    stack, indice = _stack_and_corpus()
    stack.memory = FakeMemoryStore()
    stack.llm = build_agentic_scripted_llm(stack, actor_id=actor_id, session_id=session_id)
    return stack, indice


# --- M1: seguimiento anafórico dentro de un mismo proceso (como `chat`) -----


def test_m1_stm_resuelve_el_referente_sin_nombrar_el_sujeto() -> None:
    """Replica `demo.py chat --agentic --actor-id ... --session-id ...`: un
    único `Stack` (y por lo tanto un único `FakeMemoryStore` en RAM) para
    los dos turnos, igual que dentro del REPL de `chat`.
    """
    stack, indice = _con_memoria_activa("demo-speaker-m1", "m1-take1")

    turno_1 = answer_agentic(P2, stack, indice, actor_id="demo-speaker-m1", session_id="m1-take1")
    assert turno_1.abstained is False
    assert _step(turno_1.trace, "herramienta.recordar_memoria") is None

    turno_2 = answer_agentic(
        P_M1_SEGUIMIENTO, stack, indice, actor_id="demo-speaker-m1", session_id="m1-take1"
    )

    paso_memoria = _step(turno_2.trace, "herramienta.recordar_memoria")
    assert paso_memoria is not None
    assert paso_memoria.detail == "1 recuerdo (STM sesión=1, LTM hechos=0, LTM preferencias=0)"

    assert turno_2.abstained is False
    assert turno_2.text == TEXTO_M1_SEGUIMIENTO
    assert any(cita.document == "servicios/core-billing.md" for cita in turno_2.citations)
    assert not any(cita.document == "memoria" for cita in turno_2.citations)

    afirmaciones = {(a["tipo"], a["objeto"]): a["respaldada"] for a in _afirmaciones(turno_2)}
    assert afirmaciones[("RESPONSABLE_DE", "core-billing")] is True


def test_m1_sin_turno_previo_en_la_sesion_no_inventa_un_dueno() -> None:
    """Sesión distinta (sin el turno 1 sobre `core-billing`): STM no tiene
    nada que recordar y el turno se abstiene — el comportamiento honesto
    esperado, no un bug de la escena (ver GUION_ACTO4_MEMORIA.md, Gotcha de M1).
    """
    stack, indice = _con_memoria_activa("demo-speaker-m1", "sesion-nueva")

    respuesta = answer_agentic(
        P_M1_SEGUIMIENTO, stack, indice, actor_id="demo-speaker-m1", session_id="sesion-nueva"
    )

    paso_memoria = _step(respuesta.trace, "herramienta.recordar_memoria")
    assert paso_memoria is not None
    assert paso_memoria.detail == "0 recuerdos (STM sesión=0, LTM hechos=0, LTM preferencias=0)"
    assert respuesta.abstained is True


# --- M2: la preferencia cambia el formato, nunca los hechos ni las citas ---


def test_m2_preferencia_cambia_el_formato_no_los_hechos_ni_las_citas() -> None:
    stack, indice = _con_memoria_activa("demo-speaker-m2", "m2-take1")
    stack.memory.seed_preferencia("demo-speaker-m2", SEMILLA_M2_PREFERENCIA)

    con_preferencia = answer_agentic(
        P_BILLING, stack, indice, actor_id="demo-speaker-m2", session_id="m2-take1"
    )

    paso_memoria = _step(con_preferencia.trace, "herramienta.recordar_memoria")
    assert paso_memoria is not None
    assert paso_memoria.detail == "1 recuerdo (STM sesión=0, LTM hechos=0, LTM preferencias=1)"

    assert con_preferencia.abstained is False
    assert con_preferencia.text == TEXTO_P_BILLING_CON_PREFERENCIA
    assert not any(cita.document == "memoria" for cita in con_preferencia.citations)

    stack_control, indice_control = _stack_and_corpus()
    stack_control.llm = build_agentic_scripted_llm(stack_control)
    sin_memoria = answer_agentic(P_BILLING, stack_control, indice_control)

    assert _step(sin_memoria.trace, "herramienta.recordar_memoria") is None

    documentos_con_preferencia = {c.document for c in con_preferencia.citations}
    documentos_sin_memoria = {c.document for c in sin_memoria.citations}
    assert documentos_con_preferencia == documentos_sin_memoria == {
        "producto/billing-2-0.md",
        "servicios/auth-cache.md",
        "arquitectura/decisiones.md",
        "incidentes/postmortem-inc-042-auth-cache.md",
    }

    cobertura_con = (_step(con_preferencia.trace, "gate.cobertura").metadata or {})["cobertura"]
    cobertura_sin = (_step(sin_memoria.trace, "gate.cobertura").metadata or {})["cobertura"]
    assert cobertura_con == cobertura_sin

    assert "Identidad" in con_preferencia.text
    assert "Plataforma" not in con_preferencia.text
    assert len(con_preferencia.text) < len(sin_memoria.text)

    afirmaciones_con = _afirmaciones(con_preferencia)
    assert all(a["respaldada"] for a in afirmaciones_con)


# --- M3: memoria mentirosa, degradada por el mismo anclaje al grafo --------


def test_m3_hecho_falso_recordado_se_degrada_igual_que_una_alucinacion() -> None:
    """`respuesta.text` compara contra el texto YA DEGRADADO (no contra
    `TEXTO_P_BILLING_INGENUO` crudo): lo que esta escena tiene que probar es
    que `validate_relational_claims` degrada el puente sin respaldo sea cual
    sea su origen (modelo o memoria), no que el guion devolvió ese texto tal
    cual.
    """
    stack, indice = _con_memoria_activa("demo-speaker-m3", "m3-take1")
    stack.memory.seed_hecho("demo-speaker-m3", SEMILLA_M3_HECHO_FALSO)

    respuesta = answer_agentic(
        P_BILLING, stack, indice, actor_id="demo-speaker-m3", session_id="m3-take1"
    )

    paso_memoria = _step(respuesta.trace, "herramienta.recordar_memoria")
    assert paso_memoria is not None
    assert paso_memoria.detail == "1 recuerdo (STM sesión=0, LTM hechos=1, LTM preferencias=0)"

    assert respuesta.abstained is False
    assert "dependencia con auth-cache" in respuesta.text
    assert respuesta.text != TEXTO_P_BILLING_INGENUO

    afirmaciones = {(a["tipo"], a["objeto"]): a["respaldada"] for a in _afirmaciones(respuesta)}
    assert afirmaciones[("DEPENDE_DE", "auth-cache")] is True
    assert any(tipo == "RESPONSABLE_DE" and not ok for (tipo, _obj), ok in afirmaciones.items())
    assert any(tipo == "CAUSA" and not ok for (tipo, _obj), ok in afirmaciones.items())

    assert "sin evidencia suficiente para afirmar que Plataforma" in respuesta.text
    assert not any(cita.document == "memoria" for cita in respuesta.citations)
    assert "producto/billing-2-0.md" in {c.document for c in respuesta.citations}


# --- Sin actor/sesión (o sin memoria configurada), nada se activa ---------


def test_sin_actor_id_ni_session_id_las_tres_escenas_quedan_inertes() -> None:
    """El mismo hecho FALSO de M3 y la misma pregunta de seguimiento de M1,
    pero con el guion armado y llamado SIN `actor_id`/`session_id` (como
    `demo.py query --agentic` sin esas dos banderas) — igual que la tercera
    capa de activación exige en `agent.strands_agent.answer_agentic`, el
    resultado tiene que ser el de siempre: sin `recall_memory`, sin
    degradación por memoria, sin la respuesta de M1.
    """
    stack, indice = _stack_and_corpus()
    stack.memory = FakeMemoryStore()
    stack.memory.seed_hecho("demo-speaker-m3", SEMILLA_M3_HECHO_FALSO)
    stack.llm = build_agentic_scripted_llm(stack)

    billing_sin_activar = answer_agentic(P_BILLING, stack, indice)
    assert _step(billing_sin_activar.trace, "herramienta.recordar_memoria") is None
    assert billing_sin_activar.text != TEXTO_P_BILLING_INGENUO
    assert "Identidad" in billing_sin_activar.text
    assert "no hay evidencia suficiente" in billing_sin_activar.text

    seguimiento_sin_activar = answer_agentic(P_M1_SEGUIMIENTO, stack, indice)
    assert _step(seguimiento_sin_activar.trace, "herramienta.recordar_memoria") is None
    assert seguimiento_sin_activar.abstained is True


def test_sin_stack_memory_las_tres_escenas_quedan_inertes() -> None:
    """`stack.memory is None` (memoria ni siquiera configurada) con
    `actor_id`/`session_id` SÍ presentes: sigue sin activar nada — las tres
    capas son necesarias, no alcanza con dos de tres.
    """
    stack, indice = _stack_and_corpus()
    stack.llm = build_agentic_scripted_llm(stack, actor_id="demo-speaker-m3", session_id="s1")

    respuesta = answer_agentic(
        P_BILLING, stack, indice, actor_id="demo-speaker-m3", session_id="s1"
    )
    assert _step(respuesta.trace, "herramienta.recordar_memoria") is None
    assert respuesta.text != TEXTO_P_BILLING_INGENUO


def test_memoria_activa_no_se_filtra_a_preguntas_ajenas() -> None:
    """Memoria activa para el turno no significa que el guion llame
    `recall_memory` para CUALQUIER pregunta — solo `P_M1_SEGUIMIENTO` y
    `P_BILLING` la piden en este guion; P1 tiene que responder exactamente
    igual que sin memoria, sin ese tool call de más.
    """
    stack, indice = _con_memoria_activa("demo-speaker-otro", "s1")

    respuesta = answer_agentic(P1, stack, indice, actor_id="demo-speaker-otro", session_id="s1")

    assert _step(respuesta.trace, "herramienta.recordar_memoria") is None
    assert respuesta.abstained is False
    assert "María Salas" in respuesta.text
