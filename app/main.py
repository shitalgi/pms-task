import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.core.config import Settings, get_settings
from app.core.database import create_database, initialize_database
from app.core.logging import configure_logging
import app.models.booking
import app.models.document
from app.services.bookings import BookingService
from app.services.documents import DocumentService
from app.services.llm import LLMService
from app.services.memory import RedisChatMemory
from app.services.rag import RAGService
from app.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, initialize_resources: bool = True) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            if initialize_resources:
                initialize_database(application.state.engine)
                await application.state.vector_store.ensure_collection()
            yield
        finally:
            await application.state.redis.aclose()
            vector_client = getattr(application.state.vector_store, "client", None)
            if vector_client is not None:
                await vector_client.close()
            application.state.engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        description=(
            "Document ingestion, custom retrieval-augmented generation, and interview booking APIs. "
            "Configure OpenAI, Qdrant, and Redis through environment variables."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    configure_logging(app_settings)
    engine, session_factory = create_database(app_settings)
    redis_client = Redis.from_url(app_settings.redis_url, decode_responses=True)
    application.state.settings = app_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.redis = redis_client
    application.state.llm = LLMService(app_settings)
    application.state.vector_store = QdrantVectorStore(app_settings)

    def memory_service() -> RedisChatMemory:
        return RedisChatMemory(application.state.redis, app_settings)

    application.state.document_service_factory = lambda session: DocumentService(
        app_settings,
        session,
        application.state.llm,
        application.state.vector_store,
    )
    def rag_service(session):
        memory = memory_service()
        return RAGService(
            application.state.llm,
            application.state.vector_store,
            memory,
            BookingService(session, memory),
        )

    application.state.rag_service_factory = rag_service
    application.include_router(documents_router, prefix="/api/v1")
    application.include_router(chat_router, prefix="/api/v1")

    @application.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.exception_handler(RuntimeError)
    async def runtime_error_handler(_: Request, exc: RuntimeError) -> JSONResponse:
        logger.exception("A required service failed", exc_info=exc)
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled request error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred"})

    return application


app = create_app()
