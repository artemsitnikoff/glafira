import logging
from datetime import datetime, timezone
from uuid import UUID
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import NotFoundError, FileTooLargeError, UnsupportedFileTypeError
from ..models import Candidate, Document, User, Event

logger = logging.getLogger(__name__)
from ..schemas.document import DocumentOut
from ..services.audit import audit
from ..services.storage import storage_service


# File validation constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png'}
# Человекочитаемый список разрешённых форматов для сообщений об ошибке
ALLOWED_EXTENSIONS_LABEL = ", ".join(sorted(ext.lstrip('.').upper() for ext in ALLOWED_EXTENSIONS))
ALLOWED_CONTENT_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'image/jpeg',
    'image/png',
    'image/jpg'
}


def _get_file_type(filename: str) -> str:
    """Get file type category from extension"""
    ext = Path(filename).suffix.lower()
    if ext == '.pdf':
        return 'pdf'
    elif ext in {'.doc', '.docx'}:
        return 'doc'
    elif ext in {'.jpg', '.jpeg', '.png'}:
        return 'img'
    else:
        return 'other'


async def get_candidate_documents(
    session: AsyncSession,
    candidate_id: UUID,
    company_id: UUID
) -> list[DocumentOut]:
    """Get documents for candidate"""
    # Verify candidate exists
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    # Get documents — имя загрузившего одним запросом (outerjoin User), без SELECT на каждый документ (N+1).
    result = await session.execute(
        select(Document, User.full_name)
        .outerjoin(User, Document.uploaded_by == User.id)
        .where(Document.candidate_id == candidate_id)
        .order_by(Document.created_at.desc())
    )
    rows = result.all()

    items = []
    for doc, uploaded_by_name in rows:
        items.append(DocumentOut(
            id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            size_bytes=doc.size_bytes,
            source=doc.source,
            uploaded_by_name=uploaded_by_name,
            created_at=doc.created_at
        ))

    return items


async def upload_document(
    session: AsyncSession,
    candidate_id: UUID,
    file: UploadFile,
    kind: str,
    company_id: UUID,
    actor_user_id: UUID
) -> DocumentOut:
    """Upload document for candidate"""
    # Verify candidate exists
    candidate_result = await session.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == company_id,
            Candidate.deleted_at.is_(None)
        )
    )
    if not candidate_result.scalar_one_or_none():
        raise NotFoundError("Кандидат")

    # Read file content
    content = await file.read()

    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        raise FileTooLargeError(MAX_FILE_SIZE // (1024 * 1024))

    # Validate file extension
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(ALLOWED_EXTENSIONS_LABEL)

    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedFileTypeError(ALLOWED_EXTENSIONS_LABEL)

    # Save to storage
    storage_path = await storage_service.save(
        content,
        company_id=company_id,
        candidate_id=candidate_id,
        filename=file.filename or "unknown"
    )

    # Create document record
    now = datetime.now(timezone.utc)
    document = Document(
        company_id=company_id,
        candidate_id=candidate_id,
        filename=file.filename or "unknown",
        file_type=_get_file_type(file.filename or ""),
        size_bytes=len(content),
        storage_path=storage_path,
        source=kind,
        uploaded_by=actor_user_id,
        created_at=now
    )

    session.add(document)

    # Audit
    await audit(
        session,
        action="upload_document",
        entity_type="document",
        entity_id=document.id,
        after={
            "filename": file.filename,
            "file_type": document.file_type,
            "size_bytes": len(content),
            "kind": kind
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    # Событие для ленты «Все действия» (Event != audit — лента читает таблицу events)
    session.add(
        Event(
            company_id=company_id,
            type="document",
            actor_type="human",
            actor_user_id=actor_user_id,
            text=f"Загружен файл: {file.filename or 'без имени'}",
            candidate_id=candidate_id,
        )
    )

    await session.flush()

    # Parse resume if it's a resume document
    if kind == 'resume':
        try:
            from app.services.glafira.resume_parse import parse_and_apply_resume
            await parse_and_apply_resume(
                session,
                candidate_id=candidate_id,
                content=content,
                filename=file.filename or "",
                company_id=company_id,
            )
        except Exception as e:
            # Don't block upload on parse failure
            logger.warning("Resume autoparse failed for candidate %s: %s", candidate_id, e)

    # Get uploader name
    user_result = await session.execute(
        select(User.full_name).where(User.id == actor_user_id)
    )
    uploaded_by_name = user_result.scalar_one()

    return DocumentOut(
        id=document.id,
        filename=document.filename,
        file_type=document.file_type,
        size_bytes=document.size_bytes,
        source=document.source,
        uploaded_by_name=uploaded_by_name,
        created_at=document.created_at
    )


async def get_document(session: AsyncSession, document_id: UUID, company_id: UUID) -> Document:
    """Get document by ID"""
    result = await session.execute(
        select(Document)
        .join(Candidate, Document.candidate_id == Candidate.id)
        .where(
            Document.id == document_id,
            Candidate.company_id == company_id
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise NotFoundError("Документ")
    return document


async def delete_document(
    session: AsyncSession,
    document_id: UUID,
    company_id: UUID,
    actor_user_id: UUID
) -> None:
    """Delete document"""
    document = await get_document(session, document_id, company_id)

    # Delete file from storage
    await storage_service.delete(document.storage_path)

    # Audit
    await audit(
        session,
        action="delete_document",
        entity_type="document",
        entity_id=document.id,
        before={
            "filename": document.filename,
            "file_type": document.file_type,
            "size_bytes": document.size_bytes
        },
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    # Delete from database
    await session.delete(document)
    await session.flush()