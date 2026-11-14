from uuid import uuid4

from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings
from app.schemas.chat import SourceDocument


class QdrantVectorStore:
    def __init__(self, settings: Settings, client: AsyncQdrantClient | None = None) -> None:
        self.settings = settings
        self.client = client or AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )

    async def ensure_collection(self) -> None:
        collections = await self.client.get_collections()
        if self.settings.qdrant_collection not in {item.name for item in collections.collections}:
            await self.client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=self.settings.embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )

    async def upsert_document(
        self,
        document_id: str,
        filename: str,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> None:
        points = [
            models.PointStruct(
                id=str(uuid4()),
                vector=embedding,
                payload={
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": index,
                    "text": chunk,
                },
            )
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        if points:
            await self.client.upsert(collection_name=self.settings.qdrant_collection, points=points, wait=True)

    async def search(self, embedding: list[float], limit: int) -> list[SourceDocument]:
        response = await self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=embedding,
            limit=limit,
            with_payload=True,
        )
        sources: list[SourceDocument] = []
        for point in response.points:
            payload = point.payload or {}
            try:
                sources.append(
                    SourceDocument(
                        document_id=str(payload["document_id"]),
                        filename=str(payload["filename"]),
                        chunk_index=int(payload["chunk_index"]),
                        score=float(point.score or 0),
                        text=str(payload["text"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return sources

    async def delete_document(self, document_id: str) -> None:
        await self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=models.Filter(
                must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
            ),
            wait=True,
        )
