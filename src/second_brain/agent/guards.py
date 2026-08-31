"""EL PATRÓN "defensa en profundidad": capas de salida baratas y deterministas
que corren SIEMPRE (a diferencia del gate en `agent.gate`, que a veces evita
hasta invocar el LLM). Junto con el coverage gate, este módulo es la mitad de
la demo del patrón que la charla nombra "defensa en profundidad con
kill-switch por capa" — acá, reducida a las capas que caben en una demo: cada
una es barata, corre en el 100% de los turnos, y ninguna reemplaza a las
otras (un guard de salida roto nunca tapa una premisa mal resuelta río
arriba, por eso el gate corre ANTES de la síntesis y estos guards DESPUÉS).

`validate_citations` y `guard_urls` comparten un invariante: SOLO QUITAN. Ninguna
agrega texto, cita ni URL — su trabajo es recortar lo que el LLM haya
inventado a pesar del prompt, nunca completar lo que le faltó (eso, si hace
falta, es trabajo del gate/síntesis río arriba). `canary` no toca la
respuesta en absoluto: es una métrica de observabilidad de costo cero.

EL ANCLAJE AL GRAFO (`validate_relational_claims`) es un guard más de esta
misma familia, con el mismo invariante de "solo quita": ninguna de las dos
capas anteriores verifica que una afirmación relacional ("X depende de Y",
"el equipo de X es responsable de Y", "X es la causa de Y") esté realmente
sostenida por una arista del grafo o por el texto de la evidencia — solo
verifican que el `doc_id` citado exista, no que lo citado sea cierto. Un RAG
plano puede citar 4 documentos reales y aun así inventar el PUENTE entre
ellos (ver el docstring de `validate_relational_claims` para el caso
completo). Igual que el resto del módulo: determinista, sin LLM, fail-open
en el llamador (`agent.orchestrator._apply_guards`), y nunca agrega
información — solo degrada, explícitamente, la afirmación que no encuentra
respaldo.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from second_brain.agent.tools import Evidence
from second_brain.ports import Answer, TraceStep

_CITATION_PATTERN = re.compile(r"\[source:([^\]]+)\]")
_EXTRA_SPACES_PATTERN = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(r"\s+([.,;:!?])")
_URL_PATTERN = re.compile(r"https?://[^\s)\]]+")


def validate_citations(answer: Answer, evidence: list[Evidence]) -> Answer:
    """Recorta toda marca `[source:doc_id]` cuyo `doc_id` no esté en `evidence`.

    También filtra `answer.citations` con el mismo criterio, para que la
    lista estructurada y el texto nunca se contradigan sobre qué se citó de
    verdad este turno. Nunca agrega una cita que falte.
    """
    doc_ids_validos = {item.doc_id for item in evidence}
    texto_validado = _normalize_spaces(
        _CITATION_PATTERN.sub(
            lambda m: m.group(0) if m.group(1).strip() in doc_ids_validos else "",
            answer.text,
        )
    )
    citas_validas = [cita for cita in answer.citations if cita.document in doc_ids_validos]
    return replace(answer, text=texto_validado, citations=citas_validas)


def _normalize_spaces(text: str) -> str:
    sin_dobles = _EXTRA_SPACES_PATTERN.sub(" ", text)
    return _SPACE_BEFORE_PUNCTUATION_PATTERN.sub(r"\1", sin_dobles).strip()


def guard_urls(text: str, evidence: list[Evidence]) -> str:
    """Defanguea toda URL que no aparezca textualmente en la evidencia del turno.

    Una URL que el LLM menciona pero que ningún documento recuperado
    contiene no está evidenciada — puede ser una alucinación o, peor, un
    intento de exfiltración. Defanguear (no borrar) dejar constancia legible
    de que apareció, sin que sea clickeable por accidente.
    """
    textos_evidencia = [item.text for item in evidence]

    def _reemplazar(match: re.Match[str]) -> str:
        url = match.group(0)
        if any(url in texto_ev for texto_ev in textos_evidencia):
            return url
        return _defang(url)

    return _URL_PATTERN.sub(_reemplazar, text)


def _defang(url: str) -> str:
    return url.replace("://", "[:]//", 1).replace(".", "[.]")


@dataclass
class Canary:
    """Métrica de costo cero por turno: no cambia la respuesta, solo la mide."""

    tool_calls: int
    citations: int
    targets_searched: list[str]
    targets_cited: list[str]
    drift: list[str]
    abstention_form: str | None


def canary(answer: Answer, trace: list[TraceStep]) -> Canary:
    """Calcula la métrica de drift: objetivo buscado, con resultados, no citado.

    `targets_searched` sale solo de `herramienta.buscar_documentos` — no
    de `herramienta.navegar_grafo`, a propósito: el punto de un blast radius
    es justamente traer documentos DISTINTOS al nodo raíz consultado, y eso
    no es drift, es el resultado esperado del traversal.
    """
    tool_calls = sum(1 for paso in trace if paso.stage.startswith("herramienta."))
    targets_searched = [
        paso.metadata["objetivo"]
        for paso in trace
        if paso.stage == "herramienta.buscar_documentos"
        and paso.metadata
        and paso.metadata.get("objetivo")
        and paso.metadata.get("resultados", 0) > 0
    ]
    targets_cited = sorted({cita.document for cita in answer.citations})
    drift = [objetivo for objetivo in targets_searched if objetivo not in targets_cited]
    return Canary(
        tool_calls=tool_calls,
        citations=len(answer.citations),
        targets_searched=targets_searched,
        targets_cited=targets_cited,
        drift=drift,
        abstention_form=_abstention_form(answer, trace),
    )


def _abstention_form(answer: Answer, trace: list[TraceStep]) -> str | None:
    if not answer.abstained:
        return None
    paso_gate = next((paso for paso in trace if paso.stage == "gate.cobertura"), None)
    if paso_gate and paso_gate.metadata:
        cobertura = paso_gate.metadata.get("cobertura")
        if cobertura:
            return str(cobertura)
    return "abstencion"


# --- Anclaje al grafo -------------------------------------------------------
#
# El caso que motiva esta capa (ver `demo.py::P_BILLING`): la pregunta "¿qué
# dependencia puede retrasar Billing 2.0, qué equipo debe resolverla y qué
# decisión técnica explica el riesgo?" trae evidencia real de 4 documentos
# (`producto/billing-2-0.md`, `servicios/auth-cache.md`,
# `arquitectura/decisiones.md`, `incidentes/postmortem-inc-042-auth-cache.md`)
# pero SOLO DOS relaciones entre ellos existen de verdad:
#   - `billing-2-0` DEPENDE_DE `auth-cache` (roadmap, y arista real del grafo)
#   - `auth-cache` es propiedad del equipo de Identidad (catálogo de servicios)
# Ni ADR-017 ni INC-042 afirman ser la CAUSA del retraso — un LLM sin esta
# capa puede citar los 4 documentos reales y aun así inventar ese puente
# causal, o asignarle la dependencia al equipo equivocado (Plataforma en vez
# de Identidad). `validate_citations` no lo detecta: los 4 `doc_id` SON
# válidos, el problema es la afirmación que los conecta, no la cita en sí.
#
# Diseño (ver el reporte final de la tarea para el detalle completo):
#
# 1. DETECCIÓN sin LLM, por patrones sobre tres familias de verbo
#    (DEPENDE_DE/CONSUME/LLAMA_A, RESPONSABLE_DE, CAUSA). Las entidades de
#    dependencia/causa se reconocen por FORMA (slug kebab-case, código
#    `ADR-\d+`/`INC-\d+`), nunca por una lista harcodeada del corpus. El
#    equipo de una afirmación de responsabilidad se reconoce igual de
#    genérico ("equipo de <Propio>"): a propósito NO se restringe a los
#    equipos que YA aparecen en la evidencia de este turno, porque la
#    afirmación errónea del caso Billing 2.0 nombra "Plataforma", que no es
#    dueño de ningún documento devuelto — si el detector solo reconociera
#    equipos ya vistos en la evidencia, nunca vería esa afirmación para
#    poder degradarla (ver `_ownership_claims`).
# 2. VERIFICACIÓN determinista contra la evidencia de ESTE turno:
#    - dependencia (DEPENDE_DE/CONSUME/LLAMA_A, unificadas para verificar:
#      la elección de verbo del LLM es prosa, no la arista real) contra una
#      arista de grafo exacta y direccional (`Evidence.source == "grafo"`,
#      que ya verbaliza la dirección correcta, ver `agent.tools`) o, si el
#      traversal no corrió, contra un respaldo textual direccional en la
#      evidencia documental.
#    - responsabilidad de equipo contra el campo `equipo` del frontmatter
#      del documento de la entidad en cuestión (señal robusta: no depende de
#      parsear negaciones en prosa libre).
#    - causa, contra co-ocurrencia direccional NO NEGADA del sujeto y el
#      objeto en un mismo ítem de evidencia — el corpus de la demo nunca
#      declara una causa así que, salvo que la evidencia lo diga de verdad,
#      esto va a fallar (a propósito: es la categoría de afirmación más
#      fácil de inventar y la más difícil de sostener).
# 3. DEGRADACIÓN explícita (nunca silenciosa) de la oración completa que
#    contenga SOLO afirmaciones sin respaldo — si una oración mezcla una
#    afirmación respaldada con una que no, se deja intacta (más vale una
#    falsa afirmación que sobrevive por ambigüedad de parseo que borrar
#    contenido correcto que el detector no supo separar).
#
# Limitaciones conocidas (ver también el reporte de la tarea):
# - Resolución de pronombres ("resolverlo", sujeto implícito) es una
#   heurística de "última entidad mencionada", no gramática real: puede
#   apuntar a la entidad equivocada. En el corpus de la demo eso nunca
#   produce un falso positivo (ver el reporte), pero no es una garantía
#   general.
# - El sujeto implícito de la PRIMERA oración de la respuesta se completa
#   con el sujeto del turno (`Evidence.is_target`) porque `SYSTEM_SYNTHESIS`
#   exige anclar ahí (ver `agent.synthesis`); en oraciones posteriores un
#   sujeto no reconocido hace que la afirmación se OMITA, nunca que se
#   adivine — evita degradar contenido de comparación legítimo.

_NEGATION_WORDS = re.compile(r"\b(no|nunca|tampoco|ninguno|ninguna)\b", re.IGNORECASE)
_PROCLITIC_PRONOUN = re.compile(r"\b(?:lo|la|los|las)\s*$", re.IGNORECASE)

_KEBAB_ENTITY_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")
_CODE_ENTITY_PATTERN = re.compile(r"\b(?:ADR|INC)-\d+\b")
_ANY_ENTITY_PATTERN = re.compile(f"{_CODE_ENTITY_PATTERN.pattern}|{_KEBAB_ENTITY_PATTERN.pattern}")

_SENTENCE_PATTERN = re.compile(r"[^.!?\n]+[.!?]?")

_DEPENDENCY_TRIGGERS: dict[str, re.Pattern[str]] = {
    "DEPENDE_DE": re.compile(
        r"\bdepend\w*\s+de\w*\b|\bdependencia\s+(?:con|de|del)\b", re.IGNORECASE
    ),
    "CONSUME": re.compile(r"\bconsum\w*\b", re.IGNORECASE),
    "LLAMA_A": re.compile(r"\bllam\w*\s+a\b", re.IGNORECASE),
}
_GRAPH_RELATION_LABELS = {
    "DEPENDE_DE": "depende de",
    "CONSUME": "consume a",
    "LLAMA_A": "llama a",
}
_ANY_DEPENDENCY_TRIGGER = re.compile(
    "|".join(f"(?:{patron.pattern})" for patron in _DEPENDENCY_TRIGGERS.values()),
    re.IGNORECASE,
)

_TEAM_MENTION = re.compile(r"equipo\s+(?:de\s+)?(?P<team>[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]*)")
_OWNERSHIP_PREDICATE = re.compile(
    r"es\s+(?:el\s+)?responsable\s+de|debe\s+resolver(?:lo|la|los|las)?\b"
    r"|es\s+due[ñn]o\s+de|es\s+propiedad\s+de",
    re.IGNORECASE,
)
_CAUSAL_TRIGGER = re.compile(
    r"\bha\s+causado\b|\bcausad[oa]\b|\bcaus[oó]\b|\bes\s+la\s+causa\b"
    r"|\bexplica\b|\bprovoc[oó]\b",
    re.IGNORECASE,
)

_PREDICATE_LABEL_ES = {
    "DEPENDE_DE": "depende de",
    "CONSUME": "consume a",
    "LLAMA_A": "llama a",
    "RESPONSABLE_DE": "es responsable de",
    "CAUSA": "es la causa de",
}


@dataclass
class RelationalClaim:
    """Una afirmación relacional detectada en el texto de la respuesta, ya
    con sujeto y objeto resueltos (heurísticamente) a entidades conocidas.
    """

    kind: str
    subject: str
    object: str
    sentence: str


@dataclass
class ClaimVerdict:
    """Lo que `--trace` y la UI muestran: cada afirmación detectada, con el
    veredicto de si el grafo/evidencia la respalda.
    """

    kind: str
    subject: str
    object: str
    supported: bool
    sentence: str


def validate_relational_claims(
    answer: Answer, evidence: list[Evidence], turn_subject: str | None = None
) -> tuple[Answer, list[ClaimVerdict]]:
    """Degrada afirmaciones relacionales de `answer.text` sin respaldo real.

    Ver el bloque de comentarios "Anclaje al grafo" arriba de este bloque
    para el diseño completo. En resumen: detecta afirmaciones de dependencia,
    responsabilidad de equipo y causalidad por patrones (sin LLM), las
    verifica contra las aristas del grafo y el texto de `evidence` de ESTE
    turno, y solo toca (reemplazándola por una declaración explícita de
    falta de evidencia) la oración cuyas afirmaciones detectadas son TODAS
    sin respaldo. Devuelve la `Answer` (sin tocar si no hay nada que
    degradar) y la lista de veredictos para la traza.

    `turn_subject` es el sujeto de la pregunta (`objetivo` ya resuelto por
    `resolve_targets`), para completar un sujeto/objeto implícito en la
    primera oración o en una anáfora sin antecedente. Si quien llama no lo
    tiene a mano (p.ej. un test que ejercita el guard aislado), se infiere
    de la evidencia (`_turn_subject`) como mejor esfuerzo — pero esa
    inferencia puede confundirse cuando `_reanchor_graph_neighbors` marcó
    varios vecinos del blast radius como `is_target=True`, así que el
    orquestador SIEMPRE debe pasarlo explícito.
    """
    sujeto_turno = turn_subject if turn_subject is not None else _turn_subject(evidence)
    hallazgos = _extract_claims(answer.text, sujeto_turno)
    if not hallazgos:
        return answer, []

    por_oracion: dict[tuple[int, int], list[RelationalClaim]] = {}
    for span, claim in hallazgos:
        por_oracion.setdefault(span, []).append(claim)

    veredictos: list[ClaimVerdict] = []
    reemplazos: list[tuple[int, int, str]] = []
    for span, claims in por_oracion.items():
        evaluados = [(_is_supported(claim, evidence), claim) for claim in claims]
        for soportada, claim in evaluados:
            veredictos.append(
                ClaimVerdict(
                    claim.kind, claim.subject, claim.object, soportada, claim.sentence.strip()
                )
            )
        if all(not soportada for soportada, _ in evaluados):
            mensaje = " ".join(_degrade_message(claim) for _, claim in evaluados)
            reemplazos.append((span[0], span[1], mensaje))

    if not reemplazos:
        return answer, veredictos

    texto_nuevo = _normalize_spaces(_apply_replacements(answer.text, reemplazos))
    doc_ids_restantes = {m.group(1).strip() for m in _CITATION_PATTERN.finditer(texto_nuevo)}
    citas_restantes = [c for c in answer.citations if c.document in doc_ids_restantes]
    return replace(answer, text=texto_nuevo, citations=citas_restantes), veredictos


def _apply_replacements(text: str, reemplazos: list[tuple[int, int, str]]) -> str:
    for inicio, fin, nuevo in sorted(reemplazos, key=lambda r: r[0], reverse=True):
        text = text[:inicio] + nuevo + text[fin:]
    return text


def _degrade_message(claim: RelationalClaim) -> str:
    verbo = _PREDICATE_LABEL_ES.get(claim.kind, claim.kind.lower())
    return f"[sin evidencia suficiente para afirmar que {claim.subject} {verbo} {claim.object}]"


def _is_supported(claim: RelationalClaim, evidence: list[Evidence]) -> bool:
    if claim.kind in _GRAPH_RELATION_LABELS:
        if _graph_edge_supports(claim.subject, claim.object, evidence):
            return True
        return _text_support(claim.subject, claim.object, _ANY_DEPENDENCY_TRIGGER, evidence)
    if claim.kind == "RESPONSABLE_DE":
        return _ownership_supported(claim.subject, claim.object, evidence)
    if claim.kind == "CAUSA":
        return _text_support(claim.subject, claim.object, _CAUSAL_TRIGGER, evidence)
    return True


def _graph_edge_supports(subject: str, object_: str, evidence: list[Evidence]) -> bool:
    for item in evidence:
        if item.source != "grafo":
            continue
        for etiqueta in _GRAPH_RELATION_LABELS.values():
            if item.text == f"`{subject}` {etiqueta} `{object_}`.":
                return True
    return False


def _text_support(
    subject: str, object_: str, trigger: re.Pattern[str], evidence: list[Evidence]
) -> bool:
    ventana = 150
    sujeto, objeto = subject.lower(), object_.lower()
    for item in evidence:
        texto = item.text
        for match in trigger.finditer(texto):
            antes = texto[max(0, match.start() - ventana) : match.start()]
            despues = texto[match.end() : match.end() + ventana]
            if sujeto not in antes.lower() or objeto not in despues.lower():
                continue
            if _NEGATION_WORDS.search(antes[-40:]):
                continue
            return True
    return False


def _ownership_supported(team: str, entity: str, evidence: list[Evidence]) -> bool:
    equipo_esperado = _normalize_team(team)
    for item in evidence:
        if item.source != "documentos" or not item.metadata:
            continue
        if _entity_from_doc_id(item.doc_id) != entity:
            continue
        equipo = item.metadata.get("equipo")
        if equipo and _normalize_team(str(equipo)) == equipo_esperado:
            return True
    return False


def _normalize_team(text: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return sin_acentos.strip().lower()


def _entity_from_doc_id(doc_id: str) -> str:
    return Path(doc_id).stem


def _turn_subject(evidence: list[Evidence]) -> str | None:
    """El sujeto que `agent.synthesis` le exige anclar a la respuesta: el
    documento (o entidad de grafo) marcado `is_target` con más evidencia
    este turno. Se usa SOLO como último recurso para completar un sujeto u
    objeto implícito en la primera oración / en una anáfora sin antecedente
    — nunca para inventar una entidad que no aparece en la evidencia real.
    """
    candidatos = [
        _entity_from_doc_id(item.doc_id)
        for item in evidence
        if item.source == "documentos" and item.is_target and item.doc_id
    ]
    if candidatos:
        return Counter(candidatos).most_common(1)[0][0]
    de_grafo = next((item for item in evidence if item.source == "grafo"), None)
    if de_grafo:
        entidades = _scan_entities(de_grafo.text)
        if entidades:
            return entidades[0]
    return None


def _scan_entities(fragmento: str) -> list[str]:
    return [match.group(0) for match in _ANY_ENTITY_PATTERN.finditer(fragmento)]


_PROTECTED_SPAN_PATTERNS = (re.compile(r"\[source:[^\]]+\]"), re.compile(r"`[^`]*`"))
_DECIMAL_DOT_PATTERN = re.compile(r"(?<=\d)\.(?=\d)")
_DOT_MARKER = "․"
"""Marcador de un solo carácter (no `.`) para enmascarar puntos que NO son
fin de oración antes de partir el texto en oraciones — dos casos:
`[source:doc_id]`/spans entre backticks (`producto/billing-2-0.md` dentro de
una cita) y decimales entre dígitos (`Billing 2.0`, `p99 de 4.2 segundos`).
Sin esto cualquiera de los dos parte una oración a la mitad (mismo
problema, y misma solución, que `graph.extraction._split_into_sentences`).
Reemplazo 1-a-1 (no cambia el largo del texto), así los offsets calculados
sobre el texto enmascarado siguen siendo válidos contra el texto original.
"""


def _mask_dots_in_protected_spans(text: str) -> str:
    resultado = text
    for patron in _PROTECTED_SPAN_PATTERNS:
        resultado = patron.sub(lambda m: m.group(0).replace(".", _DOT_MARKER), resultado)
    return _DECIMAL_DOT_PATTERN.sub(_DOT_MARKER, resultado)


def _split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Recorta el espacio en blanco inicial de cada oración FUERA del span
    reemplazable — sin esto, degradar una oración se come el espacio (o el
    `\\n\\n` entre párrafos) que la separaba de la anterior, dejando
    `...auth-cache].[sin evidencia...` pegado.
    """
    enmascarado = _mask_dots_in_protected_spans(text)
    oraciones = []
    for match in _SENTENCE_PATTERN.finditer(enmascarado):
        inicio = match.start()
        while inicio < match.end() and text[inicio].isspace():
            inicio += 1
        oraciones.append((inicio, match.end(), text[inicio : match.end()]))
    return oraciones


def _extract_claims(
    text: str, turn_subject: str | None
) -> list[tuple[tuple[int, int], RelationalClaim]]:
    resultado: list[tuple[tuple[int, int], RelationalClaim]] = []
    last_entity: str | None = None
    for indice, (inicio, fin, oracion) in enumerate(_split_sentences(text)):
        es_primera = indice == 0
        claims = [
            *_dependency_claims(oracion, last_entity, turn_subject, es_primera),
            *_ownership_claims(oracion, last_entity, turn_subject),
            *_causal_claims(oracion, last_entity, turn_subject),
        ]
        for claim in claims:
            resultado.append(((inicio, fin), claim))
        entidades = _scan_entities(oracion)
        if entidades:
            last_entity = entidades[-1]
    return resultado


def _entities_in_range(oracion: str, inicio: int, fin: int) -> list[str]:
    """Entidades cuyo MATCH COMPLETO cae dentro de `[inicio, fin)`.

    Escanea siempre la oración entera (nunca un substring pre-cortado): un
    slug puede empezar antes de `inicio` o terminar después de `fin` si se
    lo buscara sobre un substring recortado a esa ventana, partiéndolo a la
    mitad (p.ej. `postmortem-inc-042-auth-cache` cortado en
    `postmortem-inc-042-aut`). Filtrar por posición DESPUÉS de encontrar el
    match completo evita ese slug corrupto — a costo de, en el peor caso,
    no ver una entidad cuyo span cruza el borde de la ventana, lo cual solo
    puede hacer que la capa omita una afirmación (fail-open), nunca que la
    corrompa.
    """
    return [
        m.group(0)
        for m in _ANY_ENTITY_PATTERN.finditer(oracion)
        if m.start() >= inicio and m.end() <= fin
    ]


def _dependency_claims(
    oracion: str, last_entity: str | None, turn_subject: str | None, es_primera: bool
) -> list[RelationalClaim]:
    claims: list[RelationalClaim] = []
    for tipo, patron in _DEPENDENCY_TRIGGERS.items():
        for trig in patron.finditer(oracion):
            zona_negacion = oracion[max(0, trig.start() - 40) : trig.start()]
            if _NEGATION_WORDS.search(zona_negacion):
                continue
            sujetos = _entities_in_range(oracion, 0, trig.start())
            if sujetos:
                subject = sujetos[-1]
            elif es_primera and turn_subject:
                subject = turn_subject
            else:
                continue
            limite_objeto = min(len(oracion), trig.end() + 150)
            objetos = _entities_in_range(oracion, trig.end(), limite_objeto)
            proclitico = oracion[max(0, trig.start() - 15) : trig.start()]
            if objetos:
                object_ = objetos[0]
            elif _PROCLITIC_PRONOUN.search(proclitico):
                object_ = last_entity or turn_subject
            else:
                object_ = None
            if not object_ or object_ == subject:
                continue
            claims.append(RelationalClaim(tipo, subject, object_, oracion))
    return claims


def _ownership_claims(
    oracion: str,
    last_entity: str | None,
    turn_subject: str | None,
) -> list[RelationalClaim]:
    """Detecta "equipo de X {es responsable de|debe resolver|...}".

    A propósito NO restringe `X` a un vocabulario de equipos conocido del
    corpus (nada hardcodeado, nada derivado solo de la evidencia de este
    turno): la afirmación errónea del caso Billing 2.0 nombra "Plataforma",
    que no es dueño de ningún documento retornado este turno — si el
    detector solo reconociera equipos que YA aparecen en la evidencia,
    nunca vería esa afirmación para poder degradarla. La verificación
    (`_ownership_supported`) es la que decide si `X` es o no el equipo real,
    contra el frontmatter `equipo` de la evidencia.
    """
    claims: list[RelationalClaim] = []
    for team_match in _TEAM_MENTION.finditer(oracion):
        team = team_match.group("team")
        ventana_predicado = oracion[team_match.end() : team_match.end() + 60]
        predicado = _OWNERSHIP_PREDICATE.search(ventana_predicado)
        if predicado is None:
            continue
        inicio_predicado = team_match.end() + predicado.start()
        fin_predicado = team_match.end() + predicado.end()
        zona_negacion = oracion[max(0, team_match.start() - 20) : inicio_predicado]
        if _NEGATION_WORDS.search(zona_negacion):
            continue
        if re.search(r"(?:lo|la|los|las)$", predicado.group(0), re.IGNORECASE):
            object_ = last_entity or turn_subject
        else:
            limite_objeto = min(len(oracion), fin_predicado + 150)
            objetos = _entities_in_range(oracion, fin_predicado, limite_objeto)
            object_ = objetos[0] if objetos else (last_entity or turn_subject)
        if not object_ or object_ == team:
            continue
        claims.append(RelationalClaim("RESPONSABLE_DE", team, object_, oracion))
    return claims


def _causal_claims(
    oracion: str, last_entity: str | None, turn_subject: str | None
) -> list[RelationalClaim]:
    claims: list[RelationalClaim] = []
    for trig in _CAUSAL_TRIGGER.finditer(oracion):
        inicio_zona_sujeto = max(0, trig.start() - 100)
        zona_negacion = oracion[inicio_zona_sujeto : trig.start()]
        if _NEGATION_WORDS.search(zona_negacion):
            continue
        sujetos = _entities_in_range(oracion, inicio_zona_sujeto, trig.start())
        if not sujetos:
            continue
        subject = sujetos[-1]
        limite_objeto = min(len(oracion), trig.end() + 100)
        objetos = _entities_in_range(oracion, trig.end(), limite_objeto)
        object_ = objetos[0] if objetos else (last_entity or turn_subject)
        if not object_ or object_ == subject:
            continue
        claims.append(RelationalClaim("CAUSA", subject, object_, oracion))
    return claims
