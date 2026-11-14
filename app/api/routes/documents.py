from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.models.document import Document
from app.repositories.documents import DocumentRepository
from app.schemas.documents import ChunkingStrategy, DocumentIngestResponse, DocumentListResponse
from app.services.documents import DocumentService, InvalidDocumentError

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/ingest", response_model=DocumentIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_document(
    request: Request,
    file: UploadFile = File(..., description="A PDF or UTF-8 text file"),
    chunking_strategy: ChunkingStrategy = Query(default="recursive"),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        content = await file.read(request.app.state.settings.max_upload_size_mb * 1024 * 1024 + 1)
        if not file.filename:
            raise InvalidDocumentError("A filename is required")
        service: DocumentService = request.app.state.document_service_factory(session)
        return await service.ingest(file.filename, content, chunking_strategy)
    except InvalidDocumentError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        await file.close()


@router.get("", response_model=DocumentListResponse)
def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    documents, total = DocumentRepository(session).list(limit, offset)
    return {"documents": documents, "total": total}
