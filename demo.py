"""CLI de la demo Second Brain GraphRAG (Nexora Corp) — la cara del sistema.

Todo lo que este archivo hace ya existe como función de dominio en
`second_brain.*` (ingesta, retrieval, grafo, agente): acá solo se arma la
experiencia de terminal (typer + rich) que un speaker corre en vivo. La
única pieza nueva de dominio es el guion del LLM local (`build_scripted_llm`
y `CapturingLlm`, más abajo): en modo local no hay ningún modelo real
detrás de `LlmPort`, así que esta CLI arma un `ScriptedLlm` con las
síntesis de P1, P2, P4 y P5 (P3 nunca llega al LLM, el coverage gate se
abstiene antes) más los 5 casos "wow" (Billing 2.0, soporte, onboarding,
ventas, incidentes). Los textos de P1/P2/P4/P5 son los que
`tests/test_agent.py` verificó contra el corpus real; los 5 casos "wow"
se verificaron a mano contra el mismo pipeline real (`query --trace` +
`check`, ver `corpus/README.md`) porque son nuevos. `CapturingLlm` es un wrapper transparente
de `LlmPort` (duck typing, cero cambio de contrato) que solo existe para que
`--trace` pueda mostrar cuánto recortaron los guards, sin que `agent.guards`
tenga que exponer esa métrica por su cuenta.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path as RutaArchivo
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape as _escape_markup
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from second_brain.adapters.local.scripted_llm import (
    ScriptedCondition,
    ScriptedLlm,
    ScriptedRule,
)
from second_brain.agent.orchestrator import answer
from second_brain.agent.postprocess import entity_from_doc_id
from second_brain.agent.strands_agent import answer_agentic
from second_brain.config import Settings, Stack, build_stack
from second_brain.graph.build import build_graph
from second_brain.graph.traversal import blast_radius
from second_brain.ingestion import chunk_document, index, load_corpus
from second_brain.ports import Answer, LlmPort, LlmResponse, Path, ToolCall, TraceStep
from second_brain.retrieval import LexicalIndex, build_lexical_index, resolve_targets

RUTA_BASE = RutaArchivo(__file__).resolve().parent
RUTA_CORPUS_DEFAULT = RUTA_BASE / "corpus"
RUTA_DATOS_DEFAULT = RUTA_BASE / ".data"

P1 = "¿Quién lidera el Proyecto Beta?"
P2 = "Si modifico la API de core-billing, ¿qué módulos se rompen?"
P3 = "¿Cuál fue la facturación del Q4 2025?"
P4 = "¿Quién es la CTO y cuánto gana?"
P5 = "¿Por qué el frontend de reportes no emite eventos de Amplitude?"

# Casos de uso "wow" (gancho de apertura + soporte, onboarding, ventas e
# incidentes): se suman al guion original sin tocar P1..P5. Ver
# `corpus/README.md` para el contrato completo de cada una.
P_BILLING = (
    "¿Qué dependencia puede retrasar Billing 2.0, qué equipo debe resolverla "
    "y qué decisión técnica explica el riesgo?"
)
P_SOPORTE = (
    "Un cliente dice que no le llegan los webhooks, ¿cuál es la causa más "
    "probable y cómo lo resuelvo?"
)
P_ONBOARDING = (
    "Soy nueva en el equipo de Pagos, ¿qué debo leer primero y cuál es mi "
    "entregable de la semana 1?"
)
P_VENTAS = (
    "Un prospecto dice que somos más caros que la competencia, ¿cómo "
    "respondo esa objeción?"
)
P_INCIDENTE = (
    "¿Qué causó el incidente de facturación duplicada durante el piloto de "
    "multi-moneda y qué se corrigió?"
)

_CITATION_PATTERN = re.compile(r"\[source:([^\]]+)\]")

_TEXTO_P1 = "María Salas lidera el Proyecto Beta [source:org/proyectos.md]."
_TEXTO_P2 = (
    "Tres módulos consumen `core-billing` y se romperían: `pagos` llama a "
    "`GET /billing/rates` antes de autorizar cobros [source:pagos], "
    "`notificaciones` depende del evento `billing.updated` "
    "[source:notificaciones], y `reportes-backend` lo consume directo y "
    "también de forma transitiva vía `pagos` [source:reportes-backend]."
)
_TEXTO_P4 = (
    "Ana Ruiz es la CTO de Nexora Corp [source:org/equipo.md]. La base de "
    "conocimiento indexada no tiene datos de nómina de las personas, así "
    "que no puedo decir cuánto gana."
)
_TEXTO_P5 = (
    "En la documentación indexada de `reportes-frontend`, el tracking se "
    "implementa con el composable `useTracking`, que envía eventos a "
    "Google Tag Manager; no hay ninguna integración con Amplitude "
    "[source:frontends/reportes-frontend.md].\n\n"
    "A diferencia de `dashboard` y `onboarding`, que sí integran Amplitude, "
    "la decisión de arquitectura (ADR-014) fue no adoptarlo en "
    "`reportes-frontend` por ser una superficie de bajo tráfico "
    "[source:arquitectura/decisiones.md]."
)
_TEXTO_P_BILLING = (
    "Hay evidencia de que `billing-2-0` depende de `auth-cache` "
    "[source:producto/billing-2-0.md] y de que el equipo de Identidad es "
    "responsable de resolver esa dependencia, no Plataforma "
    "[source:servicios/auth-cache.md]. Sin embargo, la decisión ADR-017 "
    "documenta por qué existe `auth-cache` [source:arquitectura/decisiones.md] "
    "y el postmortem INC-042 documenta un incidente de latencia ya resuelto "
    "sobre ese mismo servicio "
    "[source:incidentes/postmortem-inc-042-auth-cache.md]; ninguno de los dos "
    "afirma que cause un retraso en `billing-2-0`: no hay evidencia "
    "suficiente para atribuirles esa causa."
)
TEXTO_P_BILLING_INGENUO = (
    "Billing 2.0 podría retrasarse por la dependencia con auth-cache "
    "[source:producto/billing-2-0.md]. El equipo de Plataforma debe "
    "resolverlo, ya que la decisión ADR-017 introdujo una caché "
    "distribuida que ha causado problemas de latencia "
    "[source:arquitectura/decisiones.md] "
    "[source:incidentes/postmortem-inc-042-auth-cache.md]."
)
"""El guion "modo ingenuo": la respuesta MALA de la diapositiva de apertura
(le echa la culpa a Plataforma y a ADR-017, calcado del ejemplo de la
charla), palabra por palabra la misma que
`tests/test_agent.py::test_billing_2_0_bridge_is_degraded_but_the_real_dependency_and_team_survive`
ya verificó contra `validate_relational_claims` — se define acá (no en el
test) para que `build_scripted_llm`/`build_agentic_scripted_llm` la usen
sin retipearla, y el test importa esta constante en vez de llevar su
propia copia, así las dos nunca pueden divergir en silencio. Ver
`query(..., naive=True)`: es un guion de DEMOSTRACIÓN a propósito malo
para mostrar en vivo cómo el anclaje al grafo degrada las dos afirmaciones
sin respaldo (Plataforma, ADR-017 como causa) y conserva las dos que sí
tienen respaldo (la dependencia con auth-cache, el equipo de Identidad) —
nunca un modo de producción.
"""
_TEXTO_P_SOPORTE = (
    "La causa más probable es que el endpoint del cliente empezó a devolver "
    "error y `webhooks` agotó los 5 reintentos con backoff exponencial, "
    "deteniendo el envío a ese endpoint [source:soporte/catalogo-casos.md]. "
    "Para confirmarlo, revisá `GET /webhooks/entregas/{account_id}` "
    "[source:servicios/webhooks.md]: si el endpoint del cliente ya responde "
    "bien, pedile que lo reactive; si no puede, Nivel 2 puede republicar los "
    "últimos eventos perdidos."
)
_TEXTO_P_ONBOARDING = (
    "En tu primera semana en Pagos, leé primero `servicios/pagos.md` y "
    "`servicios/motor-impuestos.md`, y conocé a Renata Cifuentes (Tech Lead) "
    "[source:rrhh/onboarding-por-area.md]. Tu primer entregable de la semana "
    "1 es correr como ejercicio guiado el postmortem de facturación "
    "duplicada, para aprender cómo se investiga un incidente acá "
    "[source:rrhh/onboarding-por-area.md]. La guardia de Pagos rota entre "
    "Tomás Vidal y Sofía Prada [source:org/equipo-pagos.md]."
)
_TEXTO_P_VENTAS = (
    "El plan de entrada del Competidor A es más barato, pero no incluye "
    "sincronización nativa con ERP: para una cuenta que la necesita, el "
    "costo total con un conector de terceros suele superar el plan "
    "`enterprise` de Nexora Corp [source:ventas/matriz-competitiva.md]. Antes "
    "de usar este argumento, confirmá que el prospecto realmente necesita "
    "esa integración [source:ventas/objeciones-precio.md]."
)
_TEXTO_P_INCIDENTE = (
    "El incidente fue causado porque `pagos` trataba un timeout de "
    "`motor-impuestos` como señal de que el cobro no se había intentado, y "
    "reintentaba desde cero sin verificar el estado real de la transacción "
    "contra la pasarela externa — cuando el primer intento sí había "
    "capturado el cobro, el reintento generaba un segundo cargo "
    "[source:incidentes/postmortem-facturacion-duplicada.md]. Ya se "
    "corrigió: `pagos` ahora verifica el estado real antes de reintentar, y "
    "se redujo el timeout interno de `motor-impuestos` para que expire "
    "antes que el de `pagos` "
    "[source:incidentes/postmortem-facturacion-duplicada.md]."
)
_TEXTO_POR_DEFECTO = (
    "Esta demo local no tiene un LLM real conectado: el guion offline solo "
    "cubre las preguntas documentadas en corpus/README.md. Corré una de "
    "esas preguntas, o pasá SECOND_BRAIN_MODE=aws para respuestas reales "
    "vía Bedrock."
)

_CYPHER_TOP_ENTITIES = (
    "MATCH (n:Entidad)-[r:RELACION]-(m:Entidad) "
    "RETURN n.id AS entidad, count(r) AS conexiones "
    "ORDER BY conexiones DESC"
)


def _force_utf8_stdio() -> None:
    """Evita el `UnicodeEncodeError` de rich en consolas Windows con codepage heredado.

    Fuera de Docker (la ruta "sin Docker" del README corre en PowerShell/cmd
    nativos), stdout hereda el codepage ANSI del sistema (cp1252 es común en
    instalaciones en español) en vez de UTF-8. Los emojis y símbolos que
    `demo.py` imprime (✔, 🧠, 🔍, ...) no existen en ese codepage y rompen
    `console.print` con un traceback, sin que la lógica de negocio haya
    fallado. `reconfigure` está disponible desde Python 3.7 en streams de
    texto; los adapters Docker/CI ya corren con `PYTHONIOENCODING=utf-8` o
    locale UTF-8, así que ahí este bloque es un no-op.
    """
    for flujo in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            flujo.reconfigure(encoding="utf-8", errors="replace")


_force_utf8_stdio()
logging.basicConfig(level=logging.ERROR)

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)
console = Console()


class CapturingLlm:
    """Wrapper transparente de `LlmPort`: reenvía `generate` y guarda la última respuesta cruda.

    Existe solo para que `query --trace` pueda medir cuántas citas y URLs
    recortaron los guards sin que `agent.guards` tenga que instrumentarse
    para eso — cumple `LlmPort` por duck typing, así que sirve igual sobre
    el `ScriptedLlm` local que sobre un `BedrockLlm` real.
    """

    def __init__(self, interno: LlmPort) -> None:
        self._interno = interno
        self.ultima_respuesta: LlmResponse | None = None

    def generate(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        self.ultima_respuesta = self._interno.generate(system, messages, tools)
        return self.ultima_respuesta


_QUESTION_FILLER_WORDS = frozenset(
    {
        "cual", "cuales", "cuanto", "cuanta", "como", "donde", "quien", "quienes",
        "porque", "para", "por", "que", "los", "las", "del", "con", "una", "uno",
        "sus", "sin", "son", "fue", "hay", "mas", "muy", "esta", "este", "esto",
        "esos", "esas", "sobre", "desde", "entre", "pero", "todos", "todas",
    }
)


def _normalize(text: str) -> str:
    """Minúsculas, sin tildes ni puntuación: en escena nadie tipea exacto.

    Un acento omitido o un signo de interrogación de más no pueden decidir si
    la demo responde o cae al mensaje de "sin LLM conectado" delante de la
    sala. La comparación se hace sobre esta forma canónica, no sobre el texto
    literal.
    """
    descompuesto = unicodedata.normalize("NFD", text.lower())
    sin_tildes = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_tildes).split())


def _distinctive_terms(question: str) -> frozenset[str]:
    """Las palabras que IDENTIFICAN una pregunta, sin el relleno interrogativo.

    El corte de longitud es 3 y no 4 a propósito: las siglas cortas ("CTO",
    "API") suelen ser LO distintivo de la pregunta, y descartarlas dejaba a
    P4 identificada por una sola palabra. Lo que filtra el ruido es la lista
    de relleno, no la longitud.
    """
    return frozenset(
        palabra
        for palabra in _normalize(question).split()
        if len(palabra) >= 3 and palabra not in _QUESTION_FILLER_WORDS
    )


def _question_from_message(contenido: str) -> str:
    """Aísla la línea de la pregunta; el resto del mensaje es evidencia.

    Puntuar sobre el mensaje entero haría ganar a cualquier guion por
    vocabulario compartido: varias preguntas de la demo aparecen citadas
    dentro de la evidencia de comparación de las otras.
    """
    for linea in contenido.splitlines():
        if linea.strip().lower().startswith("pregunta del usuario:"):
            return linea.split(":", 1)[1]
    return contenido


def _similarity(script_terms: frozenset[str], question_terms: frozenset[str]) -> float:
    """Solapamiento en la dirección más favorable de las dos.

    Medir solo cuántos términos del guion aparecen en la pregunta castiga a
    las reformulaciones CORTAS, que son las más probables en vivo: "¿quién
    consume la API de core-billing?" es la misma pregunta relacional que la
    canónica y comparte casi todo su propio vocabulario, aunque cubra apenas
    la mitad del de aquella. Tomar el máximo de ambas direcciones acepta esa
    variante sin abrirle la puerta a una pregunta ajena, que no solapa en
    ninguna de las dos.
    """
    if not script_terms or not question_terms:
        return 0.0
    comunes = len(script_terms & question_terms)
    return max(comunes / len(script_terms), comunes / len(question_terms))


def _script_wins(
    index: int, script_terms_by_entry: list[frozenset[str]], piso: float = 0.5
) -> ScriptedCondition:
    """El guion responde solo si es el mejor match ÚNICO y supera el piso.

    Exigir el máximo estricto (no un umbral suelto) es lo que impide que dos
    preguntas con vocabulario parecido se roben la respuesta entre sí; el
    piso evita que una pregunta ajena caiga en el guion menos malo en vez de
    en el mensaje honesto de "esta pregunta no está guionada".
    """

    def cuando(system: str, messages: list[dict[str, Any]]) -> bool:
        preguntados = _distinctive_terms(_question_from_message(messages[-1]["content"]))
        parecidos = [_similarity(terminos, preguntados) for terminos in script_terms_by_entry]
        mejor = max(parecidos)
        return mejor >= piso and parecidos[index] == mejor and parecidos.count(mejor) == 1

    return cuando


def build_scripted_llm(naive: bool = False) -> ScriptedLlm:
    """Arma el `ScriptedLlm` de la demo con las síntesis de P1, P2, P4, P5 y los
    5 casos "wow" (Billing 2.0, soporte, onboarding, ventas, incidentes).

    Los textos de P1, P2, P4 y P5 son literalmente los que `tests/test_agent.py`
    ya verificó contra el corpus real (citas correctas, anclaje al sujeto en
    P5, honestidad parcial en P4): la demo en vivo muestra el mismo
    comportamiento que el smoke test (`check`) certifica, nunca uno mejor.
    P3 no tiene regla porque el coverage gate la aborta antes del LLM.

    Los 5 casos "wow" se verificaron de la misma forma contra el pipeline
    real (`demo.py query --trace`, ver `corpus/README.md`): cada cita
    apunta a un `doc_id` que la recuperación real (híbrida + grafo) trae
    como evidencia para esa pregunta exacta, no a un documento elegido a
    mano. `P_BILLING` es el caso más delicado: el gate real clasifica el
    turno como `suficiente` (no distingue a nivel de sub-afirmación qué
    partes están probadas), así que la honestidad de "afirmo la dependencia
    y el equipo, pero declino la causa" es enteramente responsabilidad de
    este texto guionado — en modo AWS (LLM real) depende de que el modelo
    sea así de disciplinado con la instrucción de honestidad del
    `SYSTEM_SYNTHESIS`, porque ningún guard determinista verifica la validez
    de una afirmación causal entre dos documentos igualmente citables.

    El match es por términos distintivos y no por texto literal: en vivo la
    pregunta se reformula, se tipea sin tildes o se le agrega una palabra, y
    ninguna de esas variantes puede tumbar la demo.

    `naive=True` reemplaza SOLO la síntesis de `P_BILLING` por
    `TEXTO_P_BILLING_INGENUO` (el guion de demostración deliberadamente malo
    que inventa el puente a Plataforma/ADR-017): todo lo demás —las otras 8
    preguntas, los guards, el gate— corre exactamente igual, así que lo
    único que cambia frente al comportamiento por defecto es esa única
    respuesta, y solo cuando quien llama lo pide explícito.
    """
    texto_billing = TEXTO_P_BILLING_INGENUO if naive else _TEXTO_P_BILLING
    guiones = [
        (P1, _TEXTO_P1),
        (P2, _TEXTO_P2),
        (P4, _TEXTO_P4),
        (P5, _TEXTO_P5),
        (P_BILLING, texto_billing),
        (P_SOPORTE, _TEXTO_P_SOPORTE),
        (P_ONBOARDING, _TEXTO_P_ONBOARDING),
        (P_VENTAS, _TEXTO_P_VENTAS),
        (P_INCIDENTE, _TEXTO_P_INCIDENTE),
    ]
    terminos_por_guion = [_distinctive_terms(pregunta) for pregunta, _ in guiones]
    return ScriptedLlm(
        rules=[
            ScriptedRule(
                when=_script_wins(indice, terminos_por_guion),
                response=LlmResponse(text=texto),
            )
            for indice, (_, texto) in enumerate(guiones)
        ],
        default_response=LlmResponse(text=_TEXTO_POR_DEFECTO),
    )


def _agentic_scripts(naive: bool = False) -> list[tuple[str, str | None]]:
    """Los mismos 10 guiones agénticos, con `P_BILLING` swapeado a
    `TEXTO_P_BILLING_INGENUO` cuando `naive=True` — misma razón que
    `build_scripted_llm(naive=...)`: una función en vez de una lista fija a
    nivel de módulo porque la síntesis de Billing 2.0 ahora depende de un
    parámetro, no de una constante. `P3` mapea a `None` porque el gate corta
    sobre `AfterToolsEvent`: esa pregunta nunca llega a redactar.
    """
    texto_billing = TEXTO_P_BILLING_INGENUO if naive else _TEXTO_P_BILLING
    return [
        (P1, _TEXTO_P1),
        (P2, _TEXTO_P2),
        (P3, None),
        (P4, _TEXTO_P4),
        (P5, _TEXTO_P5),
        (P_BILLING, texto_billing),
        (P_SOPORTE, _TEXTO_P_SOPORTE),
        (P_ONBOARDING, _TEXTO_P_ONBOARDING),
        (P_VENTAS, _TEXTO_P_VENTAS),
        (P_INCIDENTE, _TEXTO_P_INCIDENTE),
    ]


def _has_tool_result(messages: list[dict[str, Any]]) -> bool:
    return any(
        "toolResult" in bloque for mensaje in messages for bloque in mensaje.get("content", [])
    )


def _question_from_agentic_messages(messages: list[dict[str, Any]]) -> str:
    """El primer mensaje de la conversación con un `Agent` de Strands es
    siempre la pregunta original en texto plano (`[{"text": pregunta}]`) y
    sigue siendo `messages[0]` en la segunda llamada (Strands lo conserva,
    solo agrega mensajes de assistant/tool después) — a diferencia de
    `_question_from_message`, que lee `Pregunta del usuario:` del mensaje
    que arma `agent.synthesis.build_user_message` para el pipeline fijo.
    """
    if not messages:
        return ""
    bloques = messages[0].get("content", [])
    textos = [bloque["text"] for bloque in bloques if isinstance(bloque, dict) and "text" in bloque]
    return textos[0] if textos else ""


def _agentic_script_wins(
    index: int, script_terms_by_entry: list[frozenset[str]], phase: str, piso: float = 0.5
) -> ScriptedCondition:
    """La misma regla de `_script_wins` (mejor match único por encima del
    piso), separada en dos fases por turno: `"decide"` (primera llamada,
    sin resultados de tool todavía) y `"draft"` (segunda llamada, ya con
    evidencia) — el mismo índice gana las dos fases porque la similitud se
    calcula sobre el mismo texto de pregunta en ambas.
    """

    def cuando(system: str, messages: list[dict[str, Any]]) -> bool:
        if _has_tool_result(messages) != (phase == "draft"):
            return False
        preguntados = _distinctive_terms(_question_from_agentic_messages(messages))
        parecidos = [_similarity(terminos, preguntados) for terminos in script_terms_by_entry]
        mejor = max(parecidos)
        return mejor >= piso and parecidos[index] == mejor and parecidos.count(mejor) == 1

    return cuando


def _build_decide_response(question: str, stack: Stack) -> LlmResponse:
    """La decisión de tool que tomaría un modelo real: ancla la búsqueda al
    mismo `target` que resolvería `resolve_targets` (el resolver que YA usa
    el pipeline fijo) y, si hay un sujeto resuelto, navega el grafo desde
    esa entidad — así la evidencia recolectada por el camino agéntico es
    equivalente a la que recolecta `agent.orchestrator._collect_evidence`,
    y las mismas síntesis ya verificadas contra el pipeline real siguen
    siendo honestas acá.
    """
    objetivos = resolve_targets(question, stack)
    if not objetivos:
        return LlmResponse(
            tool_calls=[ToolCall(name="search_documents", arguments={"question": question})],
            stop_reason="tool_use",
        )
    entidad = entity_from_doc_id(objetivos[0])
    return LlmResponse(
        tool_calls=[
            ToolCall(
                name="search_documents",
                arguments={"question": question, "target": entidad},
                id="t1",
            ),
            ToolCall(name="traverse_graph", arguments={"entity": entidad}, id="t2"),
        ],
        stop_reason="tool_use",
    )


def build_agentic_scripted_llm(stack: Stack, naive: bool = False) -> ScriptedLlm:
    """El guion del camino agéntico: mismas síntesis que `build_scripted_llm`
    (P1, P2, P4, P5 y los 5 casos "wow"; P3 nunca redacta) pero partidas en
    dos fases por pregunta — decidir la tool, después redactar — para que
    el `Agent` de Strands recorra un loop real en vez de recibir la
    respuesta ya armada. Una pregunta fuera de guion cae en
    `default_response` sin tool call: `answer_agentic` la fuerza a
    abstención igual (ver su docstring), así que el resultado visible es
    "no encontré evidencia" en vez del mensaje amistoso de
    `_TEXTO_POR_DEFECTO` — efecto secundario aceptado de que la garantía
    fail-closed no distingue "sin evidencia" de "sin guion".

    `naive` viaja igual que en `build_scripted_llm`: swapea únicamente la
    fase de redacción de `P_BILLING` por `TEXTO_P_BILLING_INGENUO` (la fase
    de decisión de tools no cambia, porque decidir qué buscar no es lo que
    el guion ingenuo demuestra).
    """
    guiones_agenticos = _agentic_scripts(naive)
    terminos_por_guion = [_distinctive_terms(pregunta) for pregunta, _ in guiones_agenticos]
    reglas: list[ScriptedRule] = []
    for indice, (pregunta, texto) in enumerate(guiones_agenticos):
        reglas.append(
            ScriptedRule(
                when=_agentic_script_wins(indice, terminos_por_guion, phase="decide"),
                response=_build_decide_response(pregunta, stack),
            )
        )
        if texto is not None:
            reglas.append(
                ScriptedRule(
                    when=_agentic_script_wins(indice, terminos_por_guion, phase="draft"),
                    response=LlmResponse(text=texto, stop_reason="end_turn"),
                )
            )
    return ScriptedLlm(
        rules=reglas,
        default_response=LlmResponse(text=_TEXTO_POR_DEFECTO, stop_reason="end_turn"),
    )


def _resolve_settings() -> Settings:
    """Settings desde el entorno, con un `vector_store_path` local por default.

    Sin esto, cada invocación de la CLI en modo local arrancaría con un
    `MemoryVectorStore` vacío (es puro RAM): `ingest` y `query` corren en
    procesos distintos, así que hace falta persistir a disco entre ambos.
    Se respeta cualquier override explícito de `SECOND_BRAIN_VECTOR_STORE_PATH`.
    """
    settings = Settings.from_env()
    if settings.mode == "local" and not settings.vector_store_path:
        settings = replace(settings, vector_store_path=str(RUTA_DATOS_DEFAULT / "vector_store"))
    return settings


def _build_cli_stack(settings: Settings, agentic: bool = False, naive: bool = False) -> Stack:
    """Arma el stack de la CLI. `agentic` y `naive` solo importan en modo
    local: eligen entre el guion determinista (`build_scripted_llm`) y el
    guion en dos fases del loop agéntico (`build_agentic_scripted_llm`), y
    dentro de cualquiera de los dos, entre la síntesis honesta de
    `P_BILLING` y `TEXTO_P_BILLING_INGENUO`. En modo `aws` el `LlmPort` es
    el mismo `BedrockLlm` real sin importar `naive` — el guion ingenuo es
    una pieza de la demo local, no algo que se le pueda pedir a un modelo
    real que finja.
    """
    if settings.vector_store_path:
        RutaArchivo(settings.vector_store_path).parent.mkdir(parents=True, exist_ok=True)
    stack = build_stack(settings)
    if settings.mode == "aws":
        interno = stack.llm
    elif agentic:
        interno = build_agentic_scripted_llm(stack, naive=naive)
    else:
        interno = build_scripted_llm(naive=naive)
    stack.llm = CapturingLlm(interno)
    return stack


def _build_cli_lexical_index() -> LexicalIndex:
    documentos = load_corpus(RUTA_CORPUS_DEFAULT)
    chunks = [chunk for doc in documentos for chunk in chunk_document(doc)]
    return build_lexical_index(chunks)


def _step(traza: list[TraceStep], stage: str) -> TraceStep | None:
    return next((p for p in traza if p.stage == stage), None)


def _coverage_of(answer: Answer) -> str | None:
    paso = _step(answer.trace, "gate.cobertura")
    return paso.metadata.get("cobertura") if paso and paso.metadata else None


@app.command()
def ingest() -> None:
    """Carga el corpus, indexa vectores y construye el grafo de dependencias.

    Es el único comando que escribe: `query`, `graph-top` y `check` solo
    leen del vector store y del grafo que este comando deja listos. Correrlo
    de nuevo es seguro (`index` y `build_graph` son idempotentes) — es
    la forma de "resetear" la demo ante cualquier duda antes de subir al
    escenario.
    """
    settings = _resolve_settings()
    stack = _build_cli_stack(settings)

    columnas = (
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
    )
    with Progress(*columnas, console=console) as progress:
        tarea = progress.add_task("Cargando corpus...", total=3)
        documentos = load_corpus(RUTA_CORPUS_DEFAULT)
        progress.update(tarea, advance=1, description="Indexando vectores...")
        stats = index(documentos, stack)
        progress.update(tarea, advance=1, description="Construyendo grafo...")
        grafo = build_graph(RUTA_CORPUS_DEFAULT, stack)
        progress.update(tarea, advance=1, description="Listo")

    console.print(
        f"[green]✔[/] {stats.documents} documentos → {stats.chunks} chunks "
        f"(dim={stats.embeddings_dim})"
    )
    console.print(
        f"[green]✔[/] grafo: {len(grafo.entities)} entidades, "
        f"{len(grafo.relations)} relaciones"
    )


def _format_path(path: Path) -> str:
    """Dibuja el camino con la flecha apuntando como el corpus declara la relación.

    Es la línea que la sala LEE durante la demo, así que la flecha tiene que
    coincidir con lo que la respuesta afirma: un blast radius se recorre
    contra la flecha (`←`), pero un camino recorrido a favor debe mostrarse
    con `→` o el diagrama contradice a la evidencia que lo acompaña.
    """
    partes = [path.nodes[0]]
    for indice, (relacion, nodo) in enumerate(
        zip(path.relations, path.nodes[1:], strict=True)
    ):
        directa = path.directions[indice] if indice < len(path.directions) else False
        partes.append(f"—{relacion}→" if directa else f"←{relacion}—")
        partes.append(nodo)
    return " ".join(partes)


def _measure_guards(stack: Stack, answer: Answer) -> tuple[int, int]:
    captura = stack.llm
    crudo = ""
    if isinstance(captura, CapturingLlm) and captura.ultima_respuesta:
        crudo = captura.ultima_respuesta.text
    doc_ids_crudos = dict.fromkeys(_CITATION_PATTERN.findall(crudo))
    citas_recortadas = max(len(doc_ids_crudos) - len(answer.citations), 0)
    urls_defanged = answer.text.count("[:]//")
    return citas_recortadas, urls_defanged


def _print_trace(stack: Stack, answer: Answer) -> None:
    traza = answer.trace
    paso_objetivos = _step(traza, "objetivos.resueltos")
    paso_buscador = _step(traza, "herramienta.buscar_documentos")
    paso_navegador = _step(traza, "herramienta.navegar_grafo")
    paso_gate = _step(traza, "gate.cobertura")

    navego_grafo = bool(
        paso_navegador and paso_navegador.metadata and paso_navegador.metadata.get("resultados", 0)
    )
    if answer.abstained:
        tipo_pregunta = "sin evidencia suficiente"
    elif navego_grafo:
        tipo_pregunta = "relacional"
    else:
        tipo_pregunta = "simple"
    console.print(f"🧠 orquestador → pregunta {tipo_pregunta} detectada")

    resultados_busqueda = 0
    if paso_buscador and paso_buscador.metadata:
        resultados_busqueda = paso_buscador.metadata.get("resultados", 0)
    console.print(f"🔍 buscador   → híbrida + RRF + rerank → {resultados_busqueda} statements")

    if navego_grafo and paso_objetivos and paso_objetivos.metadata:
        objetivos = paso_objetivos.metadata.get("objetivos") or []
        if objetivos:
            entidad = RutaArchivo(objetivos[0]).stem
            caminos = blast_radius(entidad, stack, max_hops=3)
            console.print("🕸️ navegador  → traversal (openCypher [*1..3]):")
            for camino in caminos:
                console.print(f"     {_format_path(camino)}")
            sufijo = "s" if len(caminos) != 1 else ""
            console.print(f"     ✅ {len(caminos)} camino{sufijo}")

    if paso_gate and paso_gate.metadata:
        cobertura = str(paso_gate.metadata.get("cobertura", "")).upper()
        console.print(f"🚪 gate       → {cobertura}")

    paso_sintesis = _step(traza, "sintesis.llm")
    if paso_sintesis and paso_sintesis.metadata and paso_sintesis.metadata.get("guardrail"):
        scores = paso_sintesis.metadata["guardrail"]
        detalle = " · ".join(f"{k}={v:.2f}" for k, v in scores.items())
        console.print(f"🧯 guardrail  → {detalle} (puntúa, no bloquea)")

    if answer.abstained:
        console.print("🛡️ guards     → no aplica (abstención sin síntesis)")
    else:
        citas_recortadas, urls_defanged = _measure_guards(stack, answer)
        console.print(
            f"🛡️ guards     → {citas_recortadas} citas recortadas · "
            f"{urls_defanged} URLs defanged"
        )
        _print_relational_claims(traza)

    console.print(f"📤 respuesta con {len(answer.citations)} citas")


def _print_relational_claims(traza: list[TraceStep]) -> None:
    """El "momento visual" del anclaje al grafo: qué afirmación relacional
    detectó `agent.guards.validate_relational_claims` y si la respalda el
    grafo/evidencia de este turno, o se degradó por falta de evidencia.
    """
    paso_guards = _step(traza, "guards.aplicados")
    afirmaciones = (paso_guards.metadata or {}).get("afirmaciones", []) if paso_guards else []
    if not afirmaciones:
        return
    console.print("🔗 anclaje    → afirmaciones relacionales de la respuesta:")
    for afirmacion in afirmaciones:
        marca = "✅ respaldada" if afirmacion["respaldada"] else "⛔ degradada (sin evidencia)"
        console.print(
            f"     {marca} — {afirmacion['sujeto']} {afirmacion['tipo']} {afirmacion['objeto']}"
        )


def _truncate(text: str, length: int) -> str:
    return text if len(text) <= length else text[: length - 1] + "…"


def _print_answer(answer: Answer) -> None:
    """Muestra la respuesta escapando markup de Rich.

    `answer.text` lleva marcas `[source:doc_id]` — el corchete literal
    que sostiene la promesa central de la charla ("cada afirmación cita su
    fuente"). Rich interpreta `[...]` como una etiqueta de estilo por
    defecto: sin escapar, `console.print`/`Panel` tratan `[source:...]`
    como un tag inválido y lo descartan en silencio, borrando la cita de la
    pantalla aunque siga intacta en `answer.citations`. `_escape_markup`
    neutraliza los corchetes sin tocar el texto visible.
    """
    estilo = "yellow" if answer.abstained else "cyan"
    texto_seguro = _escape_markup(answer.text)
    console.print(Panel(texto_seguro, title="Respuesta", border_style=estilo))
    if answer.citations:
        tabla = Table(title="Citas")
        tabla.add_column("Documento")
        tabla.add_column("Fragmento")
        for cita in answer.citations:
            fragmento_seguro = _escape_markup(_truncate(cita.fragment, 70))
            tabla.add_row(_escape_markup(cita.document), fragmento_seguro)
        console.print(tabla)


@app.command()
def query(
    question: str = typer.Argument(..., help="Pregunta en lenguaje natural."),
    trace: bool = typer.Option(
        False, "--trace", help="Mostrar el trace paso a paso del pipeline del agente."
    ),
    agentic: bool = typer.Option(
        False,
        "--agentic",
        help="Usar el loop agéntico (Agent de Strands) en vez del pipeline fijo.",
    ),
    naive: bool = typer.Option(
        False,
        "--naive",
        help=(
            "Guion de DEMOSTRACIÓN para Billing 2.0: un LLM deliberadamente "
            "malo que inventa el puente a Plataforma/ADR-017, para mostrar "
            "en vivo cómo el anclaje al grafo lo degrada. Solo modo local; "
            "no es un modo de producción."
        ),
    ),
) -> None:
    """Responde `question` contra el stack ya ingestado (correr `ingest` antes).

    `--agentic` cambia el camino determinista (`agent.orchestrator.answer`,
    default) por el loop de un `Agent` de Strands
    (`agent.strands_agent.answer_agentic`): el modelo decide cuándo llamar
    `search_documents`/`traverse_graph` en vez de que el orquestador las
    invoque siempre en el mismo orden. El coverage gate y los guards de
    salida son los mismos en los dos caminos (ver `agent.gate_hook` y
    `agent.postprocess`).

    `--naive` reemplaza únicamente la síntesis de la pregunta de Billing 2.0
    por `TEXTO_P_BILLING_INGENUO`: el resto del guion no cambia. Sirve para
    mostrar, sobre la MISMA pregunta, el antes (LLM que alucina el puente
    causal) y el después (`agent.guards.validate_relational_claims`
    degradándolo) — es un guion de demostración, no un modo de producción,
    y sin la bandera el comportamiento es idéntico al de siempre.
    """
    settings = _resolve_settings()
    if naive and settings.mode != "local":
        console.print(
            "[yellow]⚠ --naive es un guion de demostración de la CLI local: "
            "no tiene efecto en modo 'aws' (ahí responde el LLM real).[/]"
        )
    stack = _build_cli_stack(settings, agentic=agentic, naive=naive)
    indice = _build_cli_lexical_index()

    responder = answer_agentic if agentic else answer
    respuesta = responder(question, stack, indice)

    if naive and settings.mode == "local":
        console.print(
            "[yellow]⚠ Modo ingenuo activo: guion de demostración "
            "deliberadamente malo (solo afecta la síntesis de Billing 2.0), "
            "no una alucinación espontánea del sistema.[/]"
        )
    if trace:
        _print_trace(stack, respuesta)
    _print_answer(respuesta)


@app.command("graph-top")
def graph_top(
    top: int = typer.Option(10, "--top", help="Cuántas entidades mostrar."),
) -> None:
    """Top entidades del grafo por número de conexiones — el cierre de la demo.

    Señala el hub: la entidad de la que "todo depende" es, casi siempre, la
    misma cuyo blast radius conviene revisar antes de tocarla.
    """
    settings = _resolve_settings()
    stack = _build_cli_stack(settings)
    filas = stack.graph_store.query(_CYPHER_TOP_ENTITIES)

    tabla = Table(title="Top entidades por conexiones")
    tabla.add_column("Entidad")
    tabla.add_column("Conexiones", justify="right")
    for fila in filas[:top]:
        tabla.add_row(str(fila["entidad"]), str(fila["conexiones"]))
    console.print(tabla)


_MCP_TRANSPORTS = ("stdio", "sse", "streamable-http")


@app.command("mcp-server")
def mcp_server_cmd(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        help="stdio (clientes de escritorio, p.ej. Claude Code) | sse | streamable-http.",
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Solo aplica a sse/streamable-http."),
    port: int = typer.Option(8765, "--port", help="Solo aplica a sse/streamable-http."),
) -> None:
    """Levanta el second brain como servidor MCP: sus dos manos
    (`search_documents`/`traverse_graph`) expuestas como herramientas MCP
    para cualquier cliente que hable el protocolo (Claude Code, Strands,
    etc.) — ver el README para el bloque de configuración de Claude Code.

    Con `--transport stdio` (default) este comando no imprime NADA por
    stdout fuera del protocolo MCP: el transporte stdio usa stdout como el
    canal de mensajes JSON-RPC, así que un `console.print` acá rompería el
    framing para el cliente que lo lanzó como subproceso.
    """
    if transport not in _MCP_TRANSPORTS:
        raise typer.BadParameter(f"transport debe ser uno de {_MCP_TRANSPORTS}")

    from second_brain.mcp.server import build_mcp_server

    settings = _resolve_settings()
    stack = build_stack(settings)
    indice = _build_cli_lexical_index()
    mcp_app = build_mcp_server(stack, indice, host=host, port=port)
    mcp_app.run(transport=transport)  # type: ignore[arg-type]


@app.command("a2a-server")
def a2a_server_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(9500, "--port"),
    public_url: str | None = typer.Option(
        None,
        "--public-url",
        envvar="SECOND_BRAIN_A2A_PUBLIC_URL",
        help="URL anunciada en la Agent Card para que otros agentes se conecten "
        "(default: http://{host}:{port}/). Hace falta pasarla cuando --host es una "
        "dirección de BIND que ningún cliente puede usar para conectarse — p.ej. "
        "0.0.0.0 en Docker: ahí --public-url (o la env var) tiene que ser el nombre "
        "del servicio de compose, como http://a2a-server:9500/.",
    ),
    progress_delay: float = typer.Option(
        0.2,
        "--progress-delay",
        help="Demora (segundos) entre eventos de progreso — cosmético, para que el "
        "streaming se vea en vivo frente a público. 0 para tests/CI.",
    ),
) -> None:
    """Levanta el second brain como servidor A2A: publica su Agent Card y
    responde cada turno con el loop agéntico completo
    (`agent.strands_agent.answer_agentic`, coverage gate y guards
    incluidos) — ver `second_brain.a2a.server` para por qué NO es un
    `strands.multiagent.a2a.A2AServer` crudo.

    Es el primer proceso de la demo de cierre. El segundo es `a2a-client`,
    corriendo en otra terminal (o `make a2a-demo` / `.\\make.ps1 a2a-demo`
    para lanzar los dos con un solo comando).
    """
    from second_brain.a2a.server import serve

    settings = _resolve_settings()
    stack = _build_cli_stack(settings, agentic=True)
    indice = _build_cli_lexical_index()
    url_anunciada = public_url or f"http://{host}:{port}/"
    console.print(
        f"[cyan]Second brain A2A[/] escuchando en http://{host}:{port} "
        f"— Agent Card en {url_anunciada}.well-known/agent-card.json"
    )
    serve(stack, indice, host=host, port=port, progress_delay=progress_delay, public_url=public_url)


@app.command("a2a-client")
def a2a_client_cmd(
    question: str = typer.Argument(
        P2, help="Pregunta a hacerle al second brain por A2A (default: la de cierre de la charla)."
    ),
    endpoint: str = typer.Option("http://127.0.0.1:9500", "--endpoint"),
) -> None:
    """El "agente de soporte": el SEGUNDO proceso de la demo de cierre.

    No importa nada de `second_brain.agent.*` ni de `second_brain.config`
    — todo lo que sabe del second brain lo aprende en vivo por A2A: primero
    descubre su Agent Card, después le pregunta y muestra el streaming de
    progreso (nunca tokens crudos del LLM) hasta la respuesta final, con
    sus citas llegando como datos estructurados (no como texto re-parseado).

    Requiere `a2a-server` corriendo en otra terminal contra el mismo `--endpoint`.
    """
    from second_brain.a2a.support_agent import SUPPORT_AGENT_INTRO, ask, discover

    console.print(Panel(SUPPORT_AGENT_INTRO, title="🤝 Agente de soporte", border_style="magenta"))

    async def _run() -> None:
        card = await discover(endpoint)
        console.print(f"[green]✔[/] Agent Card descubierta: [bold]{_escape_markup(card.name)}[/]")
        console.print(f"    {_escape_markup(card.description)}")
        for skill in card.skills:
            console.print(f"    • skill: {_escape_markup(skill.name)}")

        console.print(f"\n[bold]Pregunta:[/] {_escape_markup(question)}\n")

        def on_progress(text: str) -> None:
            console.print(f"[dim]… {_escape_markup(text)}[/]")

        respuesta = await ask(endpoint, question, on_progress=on_progress)
        estilo = "yellow" if respuesta.abstained else "cyan"
        console.print(
            Panel(
                _escape_markup(respuesta.text),
                title="Respuesta del second brain (recibida por A2A)",
                border_style=estilo,
            )
        )
        if respuesta.citations:
            tabla = Table(title="Citas (llegaron por A2A como datos estructurados, no como texto)")
            tabla.add_column("Documento")
            tabla.add_column("Fragmento")
            for cita in respuesta.citations:
                tabla.add_row(
                    _escape_markup(str(cita.get("document", ""))),
                    _escape_markup(_truncate(str(cita.get("fragment", "")), 70)),
                )
            console.print(tabla)
        else:
            console.print("[yellow]Sin citas en la respuesta.[/]")

    asyncio.run(_run())


@dataclass
class _Verification:
    """Una fila del smoke test: la pregunta, y cómo decidir si pasó."""

    name: str
    question: str
    evaluate: Callable[[Answer], tuple[bool, str]]


def _verify_p1(answer: Answer) -> tuple[bool, str]:
    tiene_nombre = "María Salas" in answer.text
    tiene_cita = any(c.document == "org/proyectos.md" for c in answer.citations)
    ok = not answer.abstained and tiene_nombre and tiene_cita
    detalle = "cita org/proyectos.md y nombra a María Salas" if ok else "faltó nombre o cita"
    return ok, detalle


def _verify_p2(answer: Answer) -> tuple[bool, str]:
    documentos_citados = {c.document for c in answer.citations}
    esperados = {"pagos", "notificaciones", "reportes-backend"}
    ok = (
        _coverage_of(answer) == "suficiente"
        and esperados.issubset(documentos_citados)
        and "core-billing.md" not in documentos_citados
    )
    detalle = (
        "traversal multi-hop cita pagos/notificaciones/reportes-backend"
        if ok
        else f"citó {sorted(documentos_citados)}, esperaba superset de {sorted(esperados)}"
    )
    return ok, detalle


def _verify_p3(answer: Answer) -> tuple[bool, str]:
    """El número exacto de llamadas al modelo depende del camino: el
    pipeline fijo evalúa el gate ANTES de invocar al LLM (0 llamadas); el
    loop agéntico ya gastó la llamada que decidió buscar cuando el gate
    corta sobre `AfterToolsEvent` (1 llamada de decisión, 0 de redacción) —
    ver `agent.gate_hook`. Ninguna de las dos redacta una respuesta.
    """
    ok = answer.abstained and _coverage_of(answer) == "sin_evidencia"
    paso_llamadas = _step(answer.trace, "agente.llamadas_modelo")
    if paso_llamadas and paso_llamadas.metadata:
        llamadas = paso_llamadas.metadata.get("llamadas_modelo")
        resumen = f"{llamadas} llamada(s) de decisión, 0 de redacción"
    else:
        resumen = "0 llamadas al LLM"
    detalle = f"abstención por sin_evidencia, {resumen}" if ok else "no se abstuvo"
    return ok, detalle


def _verify_p4(answer: Answer) -> tuple[bool, str]:
    sin_numeros = not any(char.isdigit() for char in answer.text)
    ok = (
        _coverage_of(answer) == "parcial"
        and "Ana Ruiz" in answer.text
        and "nómina" in answer.text
        and sin_numeros
    )
    detalle = "nombra a Ana Ruiz y declara falta de nómina, sin inventar cifra" if ok else "falló"
    return ok, detalle


def _verify_p5(answer: Answer) -> tuple[bool, str]:
    primer_parrafo = answer.text.split("\n\n")[0]
    ok = (
        "reportes-frontend" in primer_parrafo
        and "dashboard" not in primer_parrafo
        and "onboarding" not in primer_parrafo
        and "A diferencia de" in answer.text
    )
    detalle = "ancla en reportes-frontend, compara marcado" if ok else "pivoteó fuera del ancla"
    return ok, detalle


def _verify_p_billing(answer: Answer) -> tuple[bool, str]:
    """El gancho de apertura: abstención POR AFIRMACIÓN, no por turno.

    El gate real clasifica este turno como evidencia suficiente/parcial
    (no hay abstención de turno completo), pero el texto debe afirmar
    solo los dos saltos probados (dependencia + equipo) y declinar
    explícitamente el puente causal hacia ADR-017/INC-042, citando los 4
    documentos igual — ninguno de los 4 se cae por falta de evidencia real.
    """
    documentos_citados = {c.document for c in answer.citations}
    esperados = {
        "producto/billing-2-0.md",
        "servicios/auth-cache.md",
        "arquitectura/decisiones.md",
        "incidentes/postmortem-inc-042-auth-cache.md",
    }
    ok = (
        not answer.abstained
        and _coverage_of(answer) in {"suficiente", "parcial"}
        and esperados.issubset(documentos_citados)
        and "Identidad" in answer.text
        and "no hay evidencia suficiente" in answer.text
    )
    detalle = (
        "afirma dependencia+equipo, declina ADR-017/INC-042 como causa, cita los 4 docs"
        if ok
        else f"citó {sorted(documentos_citados)}"
    )
    return ok, detalle


def _verify_p_soporte(answer: Answer) -> tuple[bool, str]:
    documentos_citados = {c.document for c in answer.citations}
    esperados = {"soporte/catalogo-casos.md", "servicios/webhooks.md"}
    ok = (
        not answer.abstained
        and _coverage_of(answer) in {"suficiente", "parcial"}
        and esperados.issubset(documentos_citados)
        and "webhooks" in answer.text
    )
    detalle = "causa + endpoint de diagnóstico, cita casos y webhooks" if ok else "falló"
    return ok, detalle


def _verify_p_onboarding(answer: Answer) -> tuple[bool, str]:
    documentos_citados = {c.document for c in answer.citations}
    esperados = {"rrhh/onboarding-por-area.md", "org/equipo-pagos.md"}
    ok = (
        not answer.abstained
        and _coverage_of(answer) in {"suficiente", "parcial"}
        and esperados.issubset(documentos_citados)
        and "Renata Cifuentes" in answer.text
    )
    detalle = "guía de onboarding de Pagos con entregable de semana 1 y guardia" if ok else "falló"
    return ok, detalle


def _verify_p_ventas(answer: Answer) -> tuple[bool, str]:
    documentos_citados = {c.document for c in answer.citations}
    esperados = {"ventas/matriz-competitiva.md", "ventas/objeciones-precio.md"}
    ok = (
        not answer.abstained
        and _coverage_of(answer) in {"suficiente", "parcial"}
        and esperados.issubset(documentos_citados)
    )
    detalle = "objeción de precio respondida con matriz competitiva" if ok else "falló"
    return ok, detalle


def _verify_p_incidente(answer: Answer) -> tuple[bool, str]:
    documentos_citados = {c.document for c in answer.citations}
    esperados = {"incidentes/postmortem-facturacion-duplicada.md"}
    ok = (
        not answer.abstained
        and _coverage_of(answer) in {"suficiente", "parcial"}
        and esperados.issubset(documentos_citados)
        and "motor-impuestos" in answer.text
        and "pagos" in answer.text
    )
    detalle = "causa raíz + corrección, cita el postmortem" if ok else "falló"
    return ok, detalle


_VERIFICATIONS = [
    _Verification("P1 — liderazgo simple", P1, _verify_p1),
    _Verification("P2 — blast radius de core-billing", P2, _verify_p2),
    _Verification("P3 — abstención honesta", P3, _verify_p3),
    _Verification("P4 — parcial sin inventar salario", P4, _verify_p4),
    _Verification("P5 — anclaje al sujeto (la trampa)", P5, _verify_p5),
    _Verification(
        "Billing 2.0 — abstención por afirmación (gancho)", P_BILLING, _verify_p_billing
    ),
    _Verification("Soporte — causa raíz de webhooks", P_SOPORTE, _verify_p_soporte),
    _Verification(
        "Onboarding — primera semana en Pagos", P_ONBOARDING, _verify_p_onboarding
    ),
    _Verification("Ventas — objeción de precio", P_VENTAS, _verify_p_ventas),
    _Verification(
        "Incidentes — postmortem de facturación duplicada", P_INCIDENTE, _verify_p_incidente
    ),
]


def _run_verifications(
    stack: Stack,
    lexical_index: LexicalIndex,
    responder: Callable[[str, Stack, LexicalIndex], Answer],
) -> list[tuple[str, bool, str]]:
    resultados = []
    for verificacion in _VERIFICATIONS:
        respuesta = responder(verificacion.question, stack, lexical_index)
        ok, detalle = verificacion.evaluate(respuesta)
        resultados.append((verificacion.name, ok, detalle))
    return resultados


@app.command()
def check() -> None:
    """Corre las 10 preguntas del guion en LOS DOS caminos (pipeline fijo y
    loop agéntico) y valida el comportamiento del contrato en ambos.

    Es el smoke test que el speaker corre antes de subir al escenario: si
    algo rompió una de las garantías documentadas en `corpus/README.md`,
    en cualquiera de los dos caminos, esto lo dice ANTES de la charla, no
    en vivo frente a la sala.
    """
    settings = _resolve_settings()
    indice = _build_cli_lexical_index()

    stack_fijo = _build_cli_stack(settings, agentic=False)
    stack_agentico = _build_cli_stack(settings, agentic=True)

    caminos = [
        ("fijo", stack_fijo, answer),
        ("agéntico", stack_agentico, answer_agentic),
    ]

    resultados: list[tuple[str, bool, str]] = []
    for etiqueta, stack, responder in caminos:
        for nombre, ok, detalle in _run_verifications(stack, indice, responder):
            resultados.append((f"{nombre} [{etiqueta}]", ok, detalle))

    for nombre, ok, detalle in resultados:
        marca = "[green]✔ OK[/]" if ok else "[red]✘ FALLA[/]"
        console.print(f"{marca}  {nombre} — {detalle}")

    total_ok = sum(1 for _, ok, _ in resultados if ok)
    console.print(f"\n[bold]{total_ok}/{len(resultados)} verificaciones OK[/]")
    if total_ok != len(resultados):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
