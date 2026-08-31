"""Adapters reales sobre AWS (Bedrock, S3 Vectors).

Ningún módulo de este paquete importa `boto3` a nivel de módulo: el import
vive dentro de cada constructor/función que efectivamente lo necesita. Así,
correr en `SECOND_BRAIN_MODE=local` nunca requiere tener `boto3` instalado
ni credenciales configuradas, y los tests de este repo corren sin AWS.
"""
