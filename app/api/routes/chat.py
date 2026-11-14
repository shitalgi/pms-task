from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag import RAGService

router = APIRouter(prefix="/chat", tags=["Conversational RAG"])


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, session: Session = Depends(get_db)) -> dict[str, object]:
    service: RAGService = request.app.state.rag_service_factory(session)
    return await service.chat(payload.message, payload.session_id, payload.top_k)
