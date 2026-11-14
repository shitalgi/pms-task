from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    top_k: int = Field(default=5, ge=1, le=20)


class SourceDocument(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    score: float
    text: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[SourceDocument] = Field(default_factory=list)
    intent: str = "question"
    booking_id: str | None = None
