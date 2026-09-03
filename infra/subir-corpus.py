#!/usr/bin/env python3
"""Sube el corpus al bucket que la Knowledge Base usa como data source,
aplicando LA MISMA exclusion que la ingesta propia.

Por que existe: el bucket de corpus solo vive para ser el data source de la
KB, y `bedrock.CfnDataSource` no puede excluir archivos — su
`inclusionPrefixes` acepta UN solo prefijo, y el corpus tiene nueve
categorias en la raiz. Asi que la exclusion tiene que pasar ANTES: lo que no
debe indexarse, no se sube.

Que se excluye y por que: `corpus/README.md` es el contrato de diseno del
corpus para humanos, no contenido indexable — `ingestion.load_corpus` ya lo
salta. Medido contra la cuenta real el 03-sep-2026: con ese README en el
indice de la KB, la pregunta sin respuesta del corpus ("la facturacion del
Q4 2025") lo recupera con score 0.82, supera el umbral del coverage gate y
el sistema DEJA DE ABSTENERSE. Los dos caminos de ingesta tienen que cubrir
el mismo conjunto de documentos o la comparacion entre ambos miente.

Es idempotente y espeja: sube lo que falta o cambio, y BORRA del bucket lo
que ya no corresponda (es lo que saca un README subido por una corrida
vieja). Corre antes de `ingestar-knowledge-base.py`.

Uso (desde `demo/infra/`, con credenciales activas):

    python subir-corpus.py
    python subir-corpus.py --region us-west-2 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3

STORAGE_STACK = "SecondBrainStorageStack"
BUCKET_OUTPUT = "CorpusBucketNameOutput"

EXCLUIDOS = {"README.md"}
"""Espeja `ingestion.load_corpus`, que lee todos los `.md` salvo `README.md`.
Si aquella regla cambia, esta tiene que cambiar con ella: son el mismo
contrato del corpus visto desde los dos caminos de ingesta.
"""


def _bucket_desde_cloudformation(region: str) -> str:
    cfn = boto3.client("cloudformation", region_name=region)
    try:
        stacks = cfn.describe_stacks(StackName=STORAGE_STACK)["Stacks"]
    except cfn.exceptions.ClientError as error:
        raise SystemExit(f"No pude leer '{STORAGE_STACK}': {error}") from error
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stacks[0].get("Outputs", [])}
    bucket = outputs.get(BUCKET_OUTPUT)
    if not bucket:
        raise SystemExit(
            f"'{STORAGE_STACK}' no expone '{BUCKET_OUTPUT}': desplega con "
            "-c enable_knowledge_base=true antes de subir el corpus."
        )
    return bucket


def _documentos_locales(raiz: Path) -> dict[str, Path]:
    return {
        ruta.relative_to(raiz).as_posix(): ruta
        for ruta in sorted(raiz.rglob("*.md"))
        if ruta.name not in EXCLUIDOS
    }


def _claves_remotas(s3, bucket: str) -> set[str]:
    claves: set[str] = set()
    for pagina in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        claves.update(objeto["Key"] for objeto in pagina.get("Contents", []))
    return claves


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--corpus", default=str(Path(__file__).resolve().parents[1] / "corpus"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    raiz = Path(args.corpus)
    if not raiz.is_dir():
        raise SystemExit(f"No existe el corpus en '{raiz}'.")

    bucket = _bucket_desde_cloudformation(args.region)
    s3 = boto3.client("s3", region_name=args.region)
    locales = _documentos_locales(raiz)
    remotas = _claves_remotas(s3, bucket)
    sobrantes = sorted(remotas - set(locales))

    print(f"bucket {bucket} · {len(locales)} documentos locales · {len(remotas)} remotos")
    if args.dry_run:
        print(f"  [dry-run] subiria {len(locales)} · borraria {sobrantes or '(nada)'}")
        return 0

    for clave, ruta in locales.items():
        s3.upload_file(str(ruta), bucket, clave)
    for clave in sobrantes:
        s3.delete_object(Bucket=bucket, Key=clave)
        print(f"  borrado (no indexable): {clave}")

    print(f"OK: {len(locales)} subidos · {len(sobrantes)} borrados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
