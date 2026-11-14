from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, document: Document) -> Document:
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def list(self, limit: int, offset: int) -> tuple[list[Document], int]:
        documents = list(
            self.session.scalars(
                select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
            )
        )
        total = self.session.scalar(select(func.count()).select_from(Document)) or 0
        return documents, total
