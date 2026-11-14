from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChunkingStrategy = Literal["fixed", "recursive"]


class DocumentIngestResponse(BaseModel):
    document_id: str
    filename: str
    chunking_strategy: ChunkingStrategy
    chunk_count: int
    character_count: int
    processing_time_seconds: float
    status: Literal["processed"] = "processed"


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    chunking_strategy: str
    chunk_count: int
    created_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int = Field(ge=0)
