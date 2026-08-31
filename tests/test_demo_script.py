"""El guion local resiste que la pregunta se tipee distinta en vivo.

En escena nadie copia la pregunta carácter por carácter: se omite una tilde,
se acorta la frase o se reformula sobre la marcha. Con match literal, cualquiera
de esas variantes hacía caer la demo al mensaje de "sin LLM conectado" delante
de la sala — un fallo de escena, no de dominio. Estos tests fijan las dos mitades
del contrato: las variantes razonables de las 10 preguntas del guion (P1, P2,
P4, P5 y los 5 casos "wow": Billing 2.0, soporte, onboarding, ventas,
incidentes) responden, y una pregunta ajena sigue cayendo al mensaje honesto
en vez de robarse el guion menos malo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo import (  # noqa: E402
    P1,
    P2,
    P4,
    P5,
    P_BILLING,
    P_INCIDENTE,
    P_ONBOARDING,
    P_SOPORTE,
    P_VENTAS,
    TEXTO_P_BILLING_INGENUO,
    build_scripted_llm,
)

_EVIDENCIA = (
    "\n\nEVIDENCIA RECUPERADA\n"
    "core-billing pagos notificaciones reportes-backend dashboard onboarding "
    "Amplitude Google Tag Manager Ana Ruiz CTO Proyecto Beta billing-2-0 "
    "auth-cache identidad webhooks motor-impuestos ventas soporte"
)

_MARCA_DE_GUION = {
    "P1": "María Salas",
    "P2": "Tres módulos",
    "P4": "Ana Ruiz",
    "P5": "reportes-frontend",
    "BILLING": "Identidad",
    "SOPORTE": "backoff exponencial",
    "ONBOARDING": "Renata Cifuentes",
    "VENTAS": "Competidor A",
    "INCIDENTE": "motor-impuestos",
    "SIN_GUION": "no tiene un LLM real",
}


def _get_answer(question: str, naive: bool = False) -> str:
    llm = build_scripted_llm(naive=naive)
    mensajes = [{"role": "user", "content": f"Pregunta del usuario: {question}{_EVIDENCIA}"}]
    return llm.generate("system", mensajes).text


@pytest.mark.parametrize(
    ("question", "script"),
    [
        (P1, "P1"),
        ("quien lidera el proyecto Beta", "P1"),
        (P2, "P2"),
        ("Si modifico la API de core-billing, que modulos se rompen?", "P2"),
        ("quien consume la API de core-billing?", "P2"),
        ("que modulos dependen de core-billing?", "P2"),
        ("que se rompe si toco core-billing", "P2"),
        ("impacto de cambiar core-billing en otros modulos", "P2"),
        (P4, "P4"),
        ("quien es la CTO de Nexora", "P4"),
        ("cuanto gana la CTO", "P4"),
        (P5, "P5"),
        ("Por que el frontend de reportes no emite eventos de Amplitude", "P5"),
        ("el frontend de reportes emite Amplitude?", "P5"),
        ("reportes-frontend manda eventos a Amplitude?", "P5"),
        (P_BILLING, "BILLING"),
        ("que puede retrasar billing 2.0 y que equipo lo resuelve", "BILLING"),
        (
            "por que se podria atrasar billing 2.0, que equipo es responsable "
            "y que decision tecnica explica el riesgo",
            "BILLING",
        ),
        (P_SOPORTE, "SOPORTE"),
        ("no le llegan los webhooks a un cliente, cual es la causa", "SOPORTE"),
        ("por que fallan los webhooks de un cliente y como lo arreglo", "SOPORTE"),
        (P_ONBOARDING, "ONBOARDING"),
        ("soy nueva en pagos que leo primero", "ONBOARDING"),
        ("que debo hacer en mi primera semana en el equipo de pagos", "ONBOARDING"),
        (P_VENTAS, "VENTAS"),
        ("nos dicen que somos caros que respondo", "VENTAS"),
        ("objecion de precio frente a la competencia", "VENTAS"),
        (P_INCIDENTE, "INCIDENTE"),
        ("que causo la facturacion duplicada del piloto multi moneda", "INCIDENTE"),
        (
            "causa raiz del incidente de facturacion duplicada en multi moneda",
            "INCIDENTE",
        ),
    ],
)
def test_the_on_stage_variants_get_an_answer(question: str, script: str) -> None:
    assert _MARCA_DE_GUION[script] in _get_answer(question)


@pytest.mark.parametrize(
    "question",
    [
        "cual es la capital de Francia",
        "como configuro kubernetes en produccion",
        "hola",
        "",
        "cual es la mejor receta de arepas",
    ],
)
def test_an_unrelated_question_does_not_steal_a_script(question: str) -> None:
    assert _MARCA_DE_GUION["SIN_GUION"] in _get_answer(question)


def test_relational_rephrasings_land_on_p2_and_not_another_script() -> None:
    """El caso que el dueño marcó como crítico: blast radius no puede degradarse.

    Las preguntas relacionales sobre `core-billing` comparten vocabulario con
    P5 (ambas nombran módulos del corpus), así que se verifica no solo que
    responden, sino que responden con el guion CORRECTO.
    """
    for pregunta in (
        "quien consume la API de core-billing?",
        "que modulos dependen de core-billing?",
        "que se rompe si toco core-billing",
    ):
        respuesta = _get_answer(pregunta)
        assert _MARCA_DE_GUION["P2"] in respuesta
        assert _MARCA_DE_GUION["P5"] not in respuesta


def test_billing_2_0_is_not_confused_with_core_billing() -> None:
    """`P2` y `P_BILLING` comparten el término "billing": el match tiene que
    desambiguar por el resto del vocabulario, no por esa palabra sola.
    """
    respuesta_core_billing = _get_answer(P2)
    assert _MARCA_DE_GUION["P2"] in respuesta_core_billing
    assert _MARCA_DE_GUION["BILLING"] not in respuesta_core_billing

    respuesta_billing_2_0 = _get_answer(P_BILLING)
    assert _MARCA_DE_GUION["BILLING"] in respuesta_billing_2_0
    assert _MARCA_DE_GUION["P2"] not in respuesta_billing_2_0


def test_naive_flag_swaps_only_the_billing_synthesis() -> None:
    """`naive=True` es un guion de DEMOSTRACIÓN (ver `TEXTO_P_BILLING_INGENUO`):
    tiene que cambiar la respuesta de `P_BILLING` exactamente al texto malo
    de la diapositiva y dejar cualquier otra pregunta del guion intacta.
    """
    assert _get_answer(P_BILLING, naive=True) == TEXTO_P_BILLING_INGENUO
    assert _get_answer(P_BILLING, naive=False) != TEXTO_P_BILLING_INGENUO
    assert _get_answer(P1, naive=True) == _get_answer(P1, naive=False)
    assert _get_answer(P5, naive=True) == _get_answer(P5, naive=False)
