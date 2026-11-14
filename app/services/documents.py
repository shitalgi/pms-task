import logging
import time
from uuid import uuid4

import fitz
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.document import Document
from app.repositories.documents import DocumentRepository
from app.schemas.documents import ChunkingStrategy
from app.services.chunking import fixed_size_chunks, recursive_character_chunks
from app.services.llm import LLMService
from app.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


class InvalidDocumentError(ValueError):
    pass


class DocumentService:
    def __init__(
        self,
        settings: Settings,
        session: Session,
        llm: LLMService,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.settings = settings
        self.repository = DocumentRepository(session)
        self.llm = llm
        self.vector_store = vector_store

    @staticmethod
    def _extract_text(filename: str, content: bytes) -> tuple[str, str]:
        extension = filename.lower().rsplit(".", maxsplit=1)[-1] if "." in filename else ""
        if extension == "txt":
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise InvalidDocumentError("Text files must use UTF-8 encoding") from exc
            return text, "text/plain"
        if extension == "pdf":
            try:
                with fitz.open(stream=content, filetype="pdf") as pdf:
                    text = "\n".join(page.get_text() for page in pdf)
            except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
                raise InvalidDocumentError("The uploaded PDF is invalid or unreadable") from exc
            return text, "application/pdf"
        raise InvalidDocumentError("Only .pdf and .txt files are supported")

    async def ingest(
        self,
        filename: str,
        content: bytes,
        strategy: ChunkingStrategy,
    ) -> dict[str, object]:
        started = time.perf_counter()
        if not content:
            raise InvalidDocumentError("The uploaded file is empty")
        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise InvalidDocumentError(f"File exceeds the {self.settings.max_upload_size_mb} MB upload limit")

        text, content_type = self._extract_text(filename, content)
        if not text.strip():
            raise InvalidDocumentError("No readable text was found in the document")
        if strategy == "fixed":
            chunks = fixed_size_chunks(text, self.settings.max_chunk_size, self.settings.chunk_overlap)
        else:
            chunks = recursive_character_chunks(text, self.settings.max_chunk_size, self.settings.chunk_overlap)
        if not chunks:
            raise InvalidDocumentError("Document text could not be split into chunks")

        embeddings = await self.llm.embed(chunks)
        if len(embeddings) != len(chunks):
            raise RuntimeError("Embedding provider returned a different number of vectors than input chunks")
        document_id = str(uuid4())
        await self.vector_store.upsert_document(document_id, filename, chunks, embeddings)
        try:
            self.repository.create(
                Document(
                    id=document_id,
                    filename=filename,
                    content_type=content_type,
                    chunking_strategy=strategy,
                    chunk_count=len(chunks),
                )
            )
        except Exception:
            logger.exception("Failed to persist document metadata; removing vector points for %s", document_id)
            await self.vector_store.delete_document(document_id)
            raise
        return {
            "document_id": document_id,
            "filename": filename,
            "chunking_strategy": strategy,
            "chunk_count": len(chunks),
            "character_count": len(text),
            "processing_time_seconds": round(time.perf_counter() - started, 4),
            "status": "processed",
        }
