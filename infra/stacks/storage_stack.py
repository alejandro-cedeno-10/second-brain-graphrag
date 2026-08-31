"""StorageStack: el bucket del corpus, el índice de Amazon S3 Vectors, y
(bajo bandera) la Bedrock Knowledge Base que los une.

`AWS::S3Vectors::Index` y `AWS::S3Vectors::Bucket` ya tienen constructs L1
(`CfnIndex`, `CfnVectorBucket`) en `aws-cdk-lib.aws_s3vectors` desde la serie
2.2xx — no hacen falta `CfnResource`/custom resources para esto. Lo que
todavía NO existe en aws-cdk-lib (a la fecha de este repo) es un L2 de más
alto nivel (algo como `S3VectorsIndex` con `grantQuery()`/`grantWrite()`):
por eso el `AgentStack` arma el policy statement de `s3vectors:*` a mano en
vez de usar un método `.grant*()`.

La dimensión (1024) y la métrica de distancia (coseno) están fijadas para
que coincidan con Cohere Embed Multilingual v3 — ver
`SECOND_BRAIN_BEDROCK_EMBEDDINGS_DIM` en `src/second_brain/config.py`.

## Knowledge Base (bajo `enable_knowledge_base`)

Verificado offline contra el modelo de boto3 de `bedrock-agent`
(`SPIKE_COMPATIBILIDAD.md` §6): `aws_cdk.aws_bedrock` **no tiene L2** para
Knowledge Bases — solo `CfnKnowledgeBase`/`CfnKnowledgeBasePolicy` (L1) — así
que esto va todo por `Cfn*`, no hay atajo de alto nivel que perder.

`storageConfiguration.type = "S3_VECTORS"` referencia el índice de S3
Vectors ya creado arriba (la KB no crea su propio vector store). Se
identifica el índice solo por `indexArn` — sumarle `vectorBucketArn`/
`indexName` en simultáneo (las tres formas parte del contrato real, pero
redundantes entre sí) hace que el validador de plantillas de `cdk synth`
reporte la propiedad como "valid under more than one of the given schemas":
el ARN del índice ya identifica bucket + índice sin ambigüedad, así que
alcanza solo. El chunking (`FIXED_SIZE`, 512 tokens / 10% overlap) es el
que promete la charla y se mapea 1:1 a `maxTokens`/`overlapPercentage` del
data source, sin transformación. El bucket de corpus pasa a ser el data
source real (antes era solo el `CfnOutput` de abajo).

**Costo** (tabla del spike, todo verificado contra pricing oficial salvo
donde se indica): storage $5.00/GB/mes + retrieval estándar $1.00/1000
llamadas (parsing/embeddings gestionados sin cargo extra); con el corpus
chico de la demo, del orden de centavos a unos pocos dólares/mes. S3 Vectors
en sí (ya declarado arriba, no es costo nuevo de la KB) agrega storage
$0.06/GB/mes + query $2.50/millón.

Puesta bajo bandera (`enable_knowledge_base`, contexto CDK o
`SECOND_BRAIN_ENABLE_KB`) para poder desplegar el stack mínimo (solo S3
Vectors, lo que ya se usa hoy en modo AWS) sin arrastrar la KB ni el bucket
de corpus (que la SCP de la organización impide crear).
"""

from __future__ import annotations

from aws_cdk import ArnFormat, CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct

EMBEDDINGS_DIM = 1024
DISTANCE_METRIC = "cosine"

KB_EMBEDDING_MODEL_ID = "cohere.embed-multilingual-v3"
KB_CHUNK_MAX_TOKENS = 512
KB_CHUNK_OVERLAP_PERCENTAGE = 10


class StorageStack(Stack):
    """Bucket de documentos fuente + bucket e índice de S3 Vectors + KB opcional."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        enable_knowledge_base: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # El bucket de corpus es S3 CLASICO y solo existe como data source de la
        # Knowledge Base. La SCP de la organizacion de la organización
        # deniega s3:CreateBucket SIN los tags de gobernanza — verificado con
        # canarios: sin tags o con cualquier nombre falla; CON los tags inline
        # (van dentro de CreateBucketConfiguration.Tags, soportado por la API
        # de S3 desde 2025) el create pasa. CloudFormation propaga los tags del
        # stack (app.py), asi que este bucket sale del mismo deploy que el
        # resto — la condicion real es la bandera enable_knowledge_base, no la
        # SCP. Los buckets de S3 VECTORS usan otra API y nunca estuvieron
        # bloqueados.
        self.corpus_bucket = None
        if enable_knowledge_base:
            self.corpus_bucket = s3.Bucket(
                self,
                "CorpusBucket",
                bucket_name=f"second-brain-corpus-{self.account}-{self.region}",
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                enforce_ssl=True,
            )

        self.vector_bucket = s3vectors.CfnVectorBucket(
            self,
            "VectorBucket",
            vector_bucket_name=f"second-brain-vectors-{self.account}-{self.region}",
        )

        # `texto` (el contenido completo del chunk, que viaja en la metadata de
        # cada vector para poder citar el fragmento) va como clave NO filtrable:
        # la metadata filtrable de S3 Vectors tiene un tope duro de 2048 bytes
        # por vector (ValidationException de PutVectors, encontrado ingiriendo
        # el corpus real) y los chunks lo superan. No se filtra por texto nunca
        # — se filtra por doc_id/equipo — así que no se pierde capacidad.
        self.vector_index = s3vectors.CfnIndex(
            self,
            "VectorIndexNonFilterable",
            vector_bucket_name=self.vector_bucket.vector_bucket_name,
            index_name="second-brain",
            data_type="float32",
            dimension=EMBEDDINGS_DIM,
            distance_metric=DISTANCE_METRIC,
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=["texto"],
            ),
        )
        self.vector_index.add_dependency(self.vector_bucket)

        # RemovalPolicy.DESTROY en un CfnVectorBucket con vectores adentro
        # falla igual que un bucket S3 no vacío — no hay "auto_delete_objects"
        # para S3 Vectors todavía. Documentado en el README: `cdk destroy`
        # requiere vaciar el índice primero si se cargó el corpus completo.
        self.vector_bucket.apply_removal_policy(RemovalPolicy.DESTROY)
        self.vector_index.apply_removal_policy(RemovalPolicy.DESTROY)

        self.knowledge_base = None
        if enable_knowledge_base:
            self.knowledge_base = self._build_knowledge_base()

        if self.corpus_bucket is not None:
            CfnOutput(
                self,
                "CorpusBucketNameOutput",
                value=self.corpus_bucket.bucket_name,
                description="Bucket de documentos fuente (data source real de la "
                "Knowledge Base).",
            )
        CfnOutput(
            self,
            "S3VectorsBucketOutput",
            value=self.vector_bucket.vector_bucket_name,
            description="Mapea a SECOND_BRAIN_S3_VECTORS_BUCKET en .env",
        )
        CfnOutput(
            self,
            "S3VectorsIndexNameOutput",
            value=self.vector_index.index_name,
            description="Mapea a SECOND_BRAIN_S3_VECTORS_INDEX_NAME en .env",
        )
        if self.knowledge_base is not None:
            CfnOutput(
                self,
                "BedrockKnowledgeBaseIdOutput",
                value=self.knowledge_base.attr_knowledge_base_id,
                description="Mapea a SECOND_BRAIN_BEDROCK_KB_ID en .env (retrieval "
                "agéntico vía bedrock-agent-runtime.Retrieve)",
            )

    def _build_kb_vector_index(self) -> s3vectors.CfnIndex:
        """Índice PROPIO de la Knowledge Base, separado del índice `second-brain`
        que puebla la ingesta manual. Compartir índice mezclaría dos espacios
        vectoriales bajo la misma métrica (la KB embebe con Cohere; la ingesta
        manual, con Nova 2 ME): los upserts entrarían sin error y las búsquedas
        devolverían ruido con score plausible. Es la misma lección que el
        corpus externo de Navi documenta en producción. Cohere Embed
        Multilingual v3 tiene dimensión FIJA 1024 — por eso la KB no lleva
        `embeddingModelConfiguration` (el servicio rechaza "configurable
        dimensions" para este modelo) y este índice se declara 1024 a mano. `AMAZON_BEDROCK_METADATA` también
        va no-filtrable: la KB escribe ahí un JSON grande (contentLocation,
        sourceDocumentId, graphDocument...) que, filtrable, revienta el tope
        de 2048 bytes en los documentos largos — falló la mitad de la primera
        ingesta real por eso.
        """
        index = s3vectors.CfnIndex(
            self,
            "KbVectorIndexB",
            vector_bucket_name=self.vector_bucket.vector_bucket_name,
            index_name="second-brain-kb",
            data_type="float32",
            dimension=EMBEDDINGS_DIM,
            distance_metric=DISTANCE_METRIC,
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=[
                    "AMAZON_BEDROCK_TEXT",
                    "AMAZON_BEDROCK_METADATA",
                ],
            ),
        )
        index.add_dependency(self.vector_bucket)
        index.apply_removal_policy(RemovalPolicy.DESTROY)
        return index

    def _build_knowledge_base(self) -> bedrock.CfnKnowledgeBase:
        self.kb_vector_index = self._build_kb_vector_index()
        kb_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Permisos mínimos para que la Knowledge Base lea el corpus, "
            "invoque el modelo de embeddings, y lea/escriba su índice de S3 Vectors.",
        )
        kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeEmbeddingModel",
                actions=["bedrock:InvokeModel"],
                resources=[
                    self.format_arn(
                        service="bedrock",
                        account="",
                        resource="foundation-model",
                        resource_name=KB_EMBEDDING_MODEL_ID,
                        arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                    )
                ],
            )
        )
        kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3VectorsReadWrite",
                actions=[
                    "s3vectors:PutVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:GetIndex",
                    "s3vectors:ListVectors",
                    "s3vectors:DeleteVectors",
                ],
                resources=[
                    self.format_arn(
                        service="s3vectors",
                        resource="bucket",
                        resource_name=f"{self.vector_bucket.vector_bucket_name}/index/"
                        f"{self.kb_vector_index.index_name}",
                        arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                    )
                ],
            )
        )
        self.corpus_bucket.grant_read(kb_role)

        knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "SecondBrainKnowledgeBase",
            name="second-brain-kb",
            description="KB gestionada sobre el mismo índice de S3 Vectors que usa el "
            "adapter propio — ver `PLAN_SERVICIOS_REALES.md` §4: la KB es el ingestor, "
            "el retrieval híbrido + RRF + rerank propios se conservan.",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=self.format_arn(
                        service="bedrock",
                        account="",
                        resource="foundation-model",
                        resource_name=KB_EMBEDDING_MODEL_ID,
                        arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                    ),
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=self.kb_vector_index.attr_index_arn,
                ),
            ),
        )
        knowledge_base.add_dependency(self.kb_vector_index)
        default_policy = kb_role.node.try_find_child("DefaultPolicy")
        if default_policy is not None:
            knowledge_base.node.add_dependency(default_policy)
        knowledge_base.apply_removal_policy(RemovalPolicy.DESTROY)

        data_source = bedrock.CfnDataSource(
            self,
            # ID lógico "B": recrear el data source es la única forma
            # soportada de RESETEAR el estado del sync incremental — la KB
            # rastrea checksums de la fuente, no el contenido del índice, así
            # que recrear el índice por fuera la deja "sincronizada" con un
            # índice vacío (job COMPLETE con 0 indexados, visto en vivo).
            "CorpusDataSourceB",
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            name="second-brain-corpus-b",
            data_deletion_policy="DELETE",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=self.corpus_bucket.bucket_arn,
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=KB_CHUNK_MAX_TOKENS,
                        overlap_percentage=KB_CHUNK_OVERLAP_PERCENTAGE,
                    ),
                ),
            ),
        )
        data_source.apply_removal_policy(RemovalPolicy.DESTROY)
        return knowledge_base
