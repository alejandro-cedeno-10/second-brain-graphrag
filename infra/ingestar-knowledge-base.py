#!/usr/bin/env python3
"""Dispara la ingesta de la Bedrock Knowledge Base con `StartIngestionJob` y
espera a que termine.

Existe porque el `cdk deploy` crea la KB y su data source VACÍOS: el CDK no
tiene forma de disparar una ingesta, así que sin este paso la KB queda
declarada pero sin un solo vector. Antes se corría a mano desde la consola;
tenerlo acá lo vuelve repetible y auditable (imprime el conteo real de
documentos indexados, no un "listo").

Es el análogo, del lado gestionado, de lo que `python demo.py ingest` hace
del lado del pipeline propio. Los dos leen el MISMO corpus y escriben en
ÍNDICES DISTINTOS de S3 Vectors (ver `stacks/storage_stack.py`), así que
correr uno nunca pisa lo del otro.

Uso (desde `demo/infra/`, con credenciales activas y el Storage stack
desplegado con `-c enable_knowledge_base=true`):

    python ingestar-knowledge-base.py
    python ingestar-knowledge-base.py --region us-west-2 --timeout 900
"""

from __future__ import annotations

import argparse
import sys
import time

import boto3

STORAGE_STACK = "SecondBrainStorageStack"
KB_ID_OUTPUT = "BedrockKnowledgeBaseIdOutput"
ESTADOS_FINALES = {"COMPLETE", "FAILED", "STOPPED"}
INTERVALO_SONDEO_SEGUNDOS = 10


def _kb_id_desde_cloudformation(region: str) -> str:
    cfn = boto3.client("cloudformation", region_name=region)
    try:
        stacks = cfn.describe_stacks(StackName=STORAGE_STACK)["Stacks"]
    except cfn.exceptions.ClientError as error:
        raise SystemExit(f"No pude leer '{STORAGE_STACK}': {error}") from error
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stacks[0].get("Outputs", [])}
    kb_id = outputs.get(KB_ID_OUTPUT)
    if not kb_id:
        raise SystemExit(
            f"'{STORAGE_STACK}' no expone '{KB_ID_OUTPUT}': desplegá con "
            "-c enable_knowledge_base=true antes de ingestar."
        )
    return kb_id


def _data_source_id(cliente, kb_id: str) -> str:
    fuentes = cliente.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]
    if not fuentes:
        raise SystemExit(f"La KB '{kb_id}' no tiene data sources.")
    return fuentes[0]["dataSourceId"]


def _esperar(cliente, kb_id: str, ds_id: str, job_id: str, timeout: int) -> dict:
    limite = time.monotonic() + timeout
    while True:
        job = cliente.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id
        )["ingestionJob"]
        estado = job["status"]
        if estado in ESTADOS_FINALES:
            return job
        if time.monotonic() > limite:
            raise SystemExit(f"Timeout ({timeout}s) esperando el job {job_id} (estado={estado}).")
        print(f"  … {estado}")
        time.sleep(INTERVALO_SONDEO_SEGUNDOS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    kb_id = _kb_id_desde_cloudformation(args.region)
    cliente = boto3.client("bedrock-agent", region_name=args.region)
    ds_id = _data_source_id(cliente, kb_id)

    print(f"KB {kb_id} · data source {ds_id} — StartIngestionJob…")
    job_id = cliente.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)[
        "ingestionJob"
    ]["ingestionJobId"]

    job = _esperar(cliente, kb_id, ds_id, job_id, args.timeout)
    stats = job.get("statistics", {})
    print(
        f"{job['status']}: {stats.get('numberOfDocumentsScanned', 0)} escaneados · "
        f"{stats.get('numberOfNewDocumentsIndexed', 0)} indexados · "
        f"{stats.get('numberOfDocumentsFailed', 0)} fallidos"
    )
    return 0 if job["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
