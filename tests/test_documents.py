import fitz
import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import create_database, initialize_database
from app.repositories.documents import DocumentRepository
from app.services.documents import DocumentService, InvalidDocumentError
from tests.conftest import FakeLLM, FakeVectorStore


@pytest.mark.asyncio
async def test_ingest_txt_persists_metadata_and_indexes_chunks() -> None:
    settings = Settings(database_url="sqlite://", openai_api_key="test", max_chunk_size=100, chunk_overlap=10)
    engine, factory = create_database(settings)
    initialize_database(engine)
    session: Session = factory()
    vectors = FakeVectorStore()

    result = await DocumentService(settings, session, FakeLLM(), vectors).ingest(
        "guide.txt",
        b"Palm Mind AI creates useful software for customers. This document contains enough text to ensure "
        b"the ingestion pipeline stores a real chunk in the vector index and saves the document details.",
        "fixed",
    )

    documents, total = DocumentRepository(session).list(10, 0)
    assert total == 1
    assert documents[0].id == result["document_id"]
    assert documents[0].chunk_count == result["chunk_count"]
    assert vectors.records
    session.close()
    engine.dispose()


@pytest.mark.asyncio
async def test_ingest_extracts_pdf_text() -> None:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "A readable PDF document.")
    content = pdf.tobytes()
    pdf.close()
    text, content_type = DocumentService._extract_text("one.pdf", content)

    assert "readable PDF" in text
    assert content_type == "application/pdf"


@pytest.mark.asyncio
async def test_ingest_rejects_unsupported_and_empty_documents() -> None:
    with pytest.raises(InvalidDocumentError):
        DocumentService._extract_text("image.png", b"contents")
    with pytest.raises(InvalidDocumentError):
        DocumentService._extract_text("broken.pdf", b"not a pdf")


def test_sqlite_database_creates_parent_directory(tmp_path) -> None:
    database_file = tmp_path / "nested" / "app.sqlite"
    settings = Settings(database_url=f"sqlite:///{database_file.as_posix()}")
    engine, _ = create_database(settings)

    assert database_file.parent.is_dir()
    engine.dispose()
