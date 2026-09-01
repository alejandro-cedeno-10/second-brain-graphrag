#!/usr/bin/env python3
"""Lee los CfnOutput de los stacks ya desplegados y escribe `../.env` en
modo `aws` — para que nadie tenga que copiar ARNs/endpoints a mano en vivo.

Variables de FalkorDB: por default el grafo es local y
`SECOND_BRAIN_FALKOR_HOST` queda con su default (`localhost`). Pero si el
`GraphStack` opcional está desplegado (`-c enable_graph_ec2=true`, FalkorDB
en EC2 — ver `stacks/graph_stack.py`), este script lee su `FalkorHostOutput`
y escribe `SECOND_BRAIN_FALKOR_HOST` con la IP pública de la instancia. El
stack de grafo es el único opcional acá: si no existe, no es error.

Uso (desde `demo/infra/`, con credenciales AWS activas y los stacks ya
desplegados):

    python despues-del-deploy.py
    python despues-del-deploy.py --region us-west-2 --out ../.env

Es idempotente: pisa `.env` con los valores actuales de CloudFormation. Si
un stack no está desplegado, se aborta con un mensaje claro en vez de
escribir un `.env` a medias.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3

STACKS = [
    "SecondBrainStorageStack",
    "SecondBrainAgentStack",
    "SecondBrainObservabilityStack",
]

# Opcional: solo se lee si está desplegado (FalkorDB en EC2, bajo bandera).
GRAPH_STACK = "SecondBrainGraphStack"

# output_key -> variable SECOND_BRAIN_* que lee config.py (ver
# src/second_brain/config.py y .env.example). Los outputs que no mapean a
# ninguna variable (p.ej. CorpusBucketNameOutput, AgentRoleArnOutput) se
# omiten a propósito: no los lee el runtime del demo.
OUTPUT_TO_ENV_VAR = {
    "S3VectorsBucketOutput": "SECOND_BRAIN_S3_VECTORS_BUCKET",
    "S3VectorsIndexNameOutput": "SECOND_BRAIN_S3_VECTORS_INDEX_NAME",
    "BedrockKnowledgeBaseIdOutput": "SECOND_BRAIN_BEDROCK_KB_ID",
    "BedrockGuardrailIdOutput": "SECOND_BRAIN_BEDROCK_GUARDRAIL_ID",
    "BedrockGuardrailVersionOutput": "SECOND_BRAIN_BEDROCK_GUARDRAIL_VERSION",
}


def _leer_outputs(cfn, nombre_stack: str) -> dict[str, str]:
    respuesta = cfn.describe_stacks(StackName=nombre_stack)
    stacks = respuesta["Stacks"]
    if not stacks:
        raise SystemExit(f"El stack '{nombre_stack}' no existe. ¿Corriste `cdk deploy --all`?")
    outputs = stacks[0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def construir_env(region: str) -> str:
    session = boto3.Session(region_name=region)
    cfn = session.client("cloudformation")

    valores: dict[str, str] = {}
    for nombre_stack in STACKS:
        outputs = _leer_outputs(cfn, nombre_stack)
        for output_key, env_var in OUTPUT_TO_ENV_VAR.items():
            if output_key in outputs:
                valores[env_var] = outputs[output_key]

    try:
        outputs_grafo = _leer_outputs(cfn, GRAPH_STACK)
    except Exception:
        outputs_grafo = {}
    if "FalkorHostOutput" in outputs_grafo:
        valores["SECOND_BRAIN_FALKOR_HOST"] = outputs_grafo["FalkorHostOutput"]

    faltantes = set(OUTPUT_TO_ENV_VAR.values()) - set(valores)
    if faltantes:
        print(
            f"⚠️  No se encontraron todos los outputs esperados. Faltan: {sorted(faltantes)}",
            file=sys.stderr,
        )

    lineas = [
        "# Generado por infra/despues-del-deploy.py — NO editar a mano,",
        "# volver a correr el script si redesplegás.",
        "SECOND_BRAIN_MODE=aws",
        f"SECOND_BRAIN_AWS_REGION={region}",
        "",
        "SECOND_BRAIN_BEDROCK_EMBEDDINGS_MODEL_ID=cohere.embed-multilingual-v3",
        "SECOND_BRAIN_BEDROCK_EMBEDDINGS_DIM=1024",
        "SECOND_BRAIN_BEDROCK_RERANK_MODEL_ID=cohere.rerank-v3-5:0",
        "SECOND_BRAIN_BEDROCK_LLM_MODEL_ID=amazon.nova-pro-v1:0",
        "SECOND_BRAIN_BEDROCK_GUARDRAIL_TRACE=enabled",
        "",
    ]
    for env_var in [*OUTPUT_TO_ENV_VAR.values(), "SECOND_BRAIN_FALKOR_HOST"]:
        if env_var in valores:
            lineas.append(f"{env_var}={valores[env_var]}")
    lineas.append("")
    return "\n".join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--region",
        default=None,
        help="Región donde se desplegaron los stacks (default: la de la sesión boto3 activa)",
    )
    parser.add_argument(
        "--out",
        default="../.env",
        help="Path del .env a escribir (default: ../.env, es decir demo/.env)",
    )
    args = parser.parse_args()

    region = args.region or boto3.Session().region_name
    if not region:
        raise SystemExit(
            "No hay región configurada. Pasá --region o seteá AWS_REGION/AWS_DEFAULT_REGION."
        )

    contenido = construir_env(region)
    destino = Path(args.out)
    destino.write_text(contenido, encoding="utf-8")
    print(f"✅ Escrito {destino.resolve()} (SECOND_BRAIN_MODE=aws, región {region})")


if __name__ == "__main__":
    main()
