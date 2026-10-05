from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Iterator
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastembed import TextEmbedding
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient, models

MODEL_NAME = os.getenv("SEMANTIC_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
COLLECTION = os.getenv("QDRANT_COLLECTION", "libraryhub-search")
VECTOR_SIZE = 384

qdrant = QdrantClient(url=os.getenv("QDRANT_URL", "http://qdrant:6333"))
embedding_model: TextEmbedding | None = None
index_ready = False


class SearchDocument(BaseModel):
    entity_id: UUID
    entity_type: str
    label: str
    body: str
    work_ids: list[UUID]


class SyncRequest(BaseModel):
    documents: list[SearchDocument] = Field(default_factory=list, max_length=512)
    delete_ids: list[UUID] = Field(default_factory=list, max_length=2048)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=3000, ge=1, le=5000)


def model_instance() -> TextEmbedding:
    global embedding_model
    if embedding_model is None:
        embedding_model = TextEmbedding(
            model_name=MODEL_NAME,
            cache_dir=os.getenv("MODEL_CACHE", "/models"),
        )
    return embedding_model


def ensure_collection() -> None:
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE,
            ),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> Iterator[None]:
    global index_ready
    ensure_collection()
    index_ready = qdrant.count(collection_name=COLLECTION).count > 0
    next(model_instance().query_embed(["query: model warmup"]))
    yield


app = FastAPI(title="LibraryHub local semantic search", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    qdrant.get_collections()
    return {"status": "ok", "model": MODEL_NAME}


@app.get("/status")
def status() -> dict:
    count = qdrant.count(collection_name=COLLECTION).count
    return {"point_count": count, "ready": index_ready}


@app.post("/reset")
def reset() -> dict:
    global index_ready
    index_ready = False
    if qdrant.collection_exists(COLLECTION):
        qdrant.delete_collection(COLLECTION)
    ensure_collection()
    return {"reset": True}


@app.post("/sync")
def sync(payload: SyncRequest) -> dict:
    global index_ready
    empty_document_ids = [document.entity_id for document in payload.documents if not document.body.strip()]
    delete_ids = list(dict.fromkeys([*payload.delete_ids, *empty_document_ids]))
    if delete_ids:
        qdrant.delete(
            collection_name=COLLECTION,
            points_selector=models.PointIdsList(points=delete_ids),
            wait=True,
        )

    documents = [document for document in payload.documents if document.body.strip()]
    if documents:
        embedder = model_instance()
        for start in range(0, len(documents), 64):
            batch = documents[start : start + 64]
            vectors = list(
                embedder.passage_embed([document.body for document in batch])
            )
            qdrant.upsert(
                collection_name=COLLECTION,
                points=[
                    models.PointStruct(
                        id=document.entity_id,
                        vector=vector.tolist(),
                        payload={
                            "entity_type": document.entity_type,
                            "label": document.label,
                            "work_ids": [str(work_id) for work_id in document.work_ids],
                        },
                    )
                    for document, vector in zip(batch, vectors, strict=True)
                ],
                wait=True,
            )
    return {"upserted": len(documents), "deleted": len(delete_ids)}


@app.post("/ready")
def mark_ready() -> dict:
    global index_ready
    index_ready = True
    return {"ready": True}


@app.post("/search")
def search(payload: SearchRequest) -> dict:
    if not index_ready:
        raise HTTPException(status_code=503, detail="Semantic index is not ready")

    query_vector = next(
        model_instance().query_embed([payload.query.strip()])
    ).tolist()
    points = qdrant.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=payload.limit,
        with_payload=True,
    ).points

    return {
        "matches": [
            {"entity_id": str(point.id), "score": point.score}
            for point in points
        ]
    }