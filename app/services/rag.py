from uuid import uuid4

from app.services.bookings import BookingService
from app.services.llm import LLMService
from app.services.memory import RedisChatMemory
from app.services.vector_store import QdrantVectorStore


class RAGService:
    def __init__(
        self,
        llm: LLMService,
        vector_store: QdrantVectorStore,
        memory: RedisChatMemory,
        booking_service: BookingService,
    ) -> None:
        self.llm = llm
        self.vector_store = vector_store
        self.memory = memory
        self.booking_service = booking_service

    async def chat(self, message: str, session_id: str | None, top_k: int) -> dict[str, object]:
        resolved_session_id = session_id or str(uuid4())
        history = await self.memory.get_history(resolved_session_id)
        booking_intent = await self.llm.extract_booking_fields(message, history)
        booking_answer, booking_id = await self.booking_service.handle(
            resolved_session_id,
            booking_intent,
            message,
        )
        if booking_answer:
            await self.memory.append_turn(resolved_session_id, message, booking_answer)
            return {
                "session_id": resolved_session_id,
                "answer": booking_answer,
                "sources": [],
                "intent": "booking",
                "booking_id": booking_id,
            }

        query_embedding = await self.llm.embed([message])
        if len(query_embedding) != 1:
            raise RuntimeError("Embedding provider returned an invalid query embedding")
        sources = await self.vector_store.search(query_embedding[0], top_k)
        context = "\n\n".join(
            f"[Source: {item.filename}, chunk {item.chunk_index}]\n{item.text}" for item in sources
        )
        answer = await self.llm.answer(message, history, context)
        await self.memory.append_turn(resolved_session_id, message, answer)
        return {
            "session_id": resolved_session_id,
            "answer": answer,
            "sources": sources,
            "intent": "question",
            "booking_id": None,
        }
