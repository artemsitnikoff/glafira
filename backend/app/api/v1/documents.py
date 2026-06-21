from fastapi import APIRouter, Depends, File, UploadFile, Form, Path
from fastapi.responses import FileResponse
from uuid import UUID

from ...deps import get_current_user, get_current_company_id
from ...models import User
from ...core.errors import ForbiddenError
from ...core.permissions import can_manager_access_candidate
from ...database import get_db
from ...schemas.document import DocumentOut
from ...services.document import (
    get_candidate_documents,
    upload_document,
    get_document,
    delete_document
)
from ...services.storage import storage_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/candidates/{candidate_id}/documents", response_model=list[DocumentOut])
async def get_documents(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Менеджер: только кандидаты из своих вакансий (PII!)
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    return await get_candidate_documents(session, candidate_id, company_id)


@router.post("/candidates/{candidate_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document_route(
    candidate_id: UUID,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    parse: bool = Form(True),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Менеджер: только кандидаты из своих вакансий
    if user.role == "manager":
        if not await can_manager_access_candidate(session, user.id, candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному кандидату")

    result = await upload_document(session, candidate_id, file, kind, parse, company_id, user.id)
    await session.commit()
    return result


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    document = await get_document(session, document_id, company_id)

    # Менеджер: только документы кандидатов из своих вакансий (PII!)
    if current_user.role == "manager":
        if not await can_manager_access_candidate(session, current_user.id, document.candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному документу")

    file_path = storage_service.get_path(document.storage_path)

    return FileResponse(
        path=str(file_path),
        filename=document.filename,
        media_type="application/octet-stream"
    )


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document_route(
    document_id: UUID,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    session: AsyncSession = Depends(get_db),
):
    # Менеджер: только документы кандидатов из своих вакансий
    if user.role == "manager":
        document = await get_document(session, document_id, company_id)
        if not await can_manager_access_candidate(session, user.id, document.candidate_id, company_id):
            raise ForbiddenError("Нет доступа к данному документу")

    await delete_document(session, document_id, company_id, user.id)
    await session.commit()