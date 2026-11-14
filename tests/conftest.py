from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import initialize_database
from app.main import create_app
from app.schemas.chat import SourceDocument
from app.services.bookings import BookingService
from app.services.documents import DocumentService
from app.services.memory import RedisChatMemory
from app.services.rag import RAGService


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)

    async def aclose(self) -> None:
        return None


class FakeLLM:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.0] for text in texts]

    async def extract_booking_fields(self, message: str, history: list[dict[str, str]]) -> dict[str, object]:
        return {"intent": "question", "confirmation": None, "cancel": False}

    async def answer(self, question: str, history: list[dict[str, str]], context: str) -> str:
        return f"Answer based on: {context}"


class FakeVectorStore:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, str, list[float]]] = []

    async def upsert_document(
        self,
        document_id: str,
        filename: str,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> None:
        self.records.extend(
            (document_id, filename, chunk, embedding)
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        )

    async def delete_document(self, document_id: str) -> None:
        self.records = [item for item in self.records if item[0] != document_id]

    async def search(self, embedding: list[float], limit: int) -> list[SourceDocument]:
        return [
            SourceDocument(
                document_id="document-1",
                filename="handbook.txt",
                chunk_index=0,
                score=0.91,
                text="Palm Mind AI builds applied AI products.",
            )
        ][:limit]


@pytest.fixture
def app_client() -> Generator[TestClient, None, None]:
    settings = Settings(
        database_url="sqlite://",
        openai_api_key="test-key",
        max_chunk_size=100,
        chunk_overlap=10,
    )
    application = create_app(settings, initialize_resources=False)
    initialize_database(application.state.engine)
    application.state.redis = FakeRedis()
    application.state.llm = FakeLLM()
    application.state.vector_store = FakeVectorStore()
    application.state.document_service_factory = lambda session: DocumentService(
        settings,
        session,
        application.state.llm,
        application.state.vector_store,
    )

    def rag_factory(session):
        memory = RedisChatMemory(application.state.redis, settings)
        return RAGService(
            application.state.llm,
            application.state.vector_store,
            memory,
            BookingService(session, memory),
        )

    application.state.rag_service_factory = rag_factory
    with TestClient(application) as client:
        yield client
