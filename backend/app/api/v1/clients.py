from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...database import get_db
from ...deps import get_current_company_id, get_current_user
from ...core.errors import NotFoundError, ConflictError
from ...models import Client, User, Vacancy
from ...schemas.client import ClientOut, ClientCreate, ClientUpdate
from ...services.audit import audit

router = APIRouter()


async def _get_owned_client(session: AsyncSession, client_id: UUID, company_id: UUID) -> Client:
    """Загружает клиента строго в скоупе компании (чужой/несуществующий → 404)."""
    client = (await session.execute(
        select(Client).where(
            Client.id == client_id,
            Client.company_id == company_id,
        )
    )).scalar_one_or_none()
    if client is None:
        raise NotFoundError("Заказчик")
    return client


@router.get("", response_model=list[ClientOut])
async def list_clients(
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
):
    """List all clients for the company"""
    rows = (await session.execute(
        select(Client).where(Client.company_id == company_id).order_by(Client.name)
    )).scalars().all()
    return rows


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    data: ClientCreate,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Create a new client"""
    client = Client(company_id=company_id, **data.model_dump(exclude_unset=True))
    session.add(client)
    await session.flush()

    await audit(
        session,
        action="create_client",
        entity_type="client",
        entity_id=client.id,
        after={"name": client.name, "contact_person": client.contact_person},
        actor_user_id=current_user.id,
        company_id=company_id,
    )

    await session.commit()
    # После commit server-side updated_at/created_at помечены для перезагрузки —
    # refresh подтягивает их в async-контексте, иначе сериализация ClientOut
    # триггерит ленивый IO вне greenlet (MissingGreenlet).
    await session.refresh(client)
    return client


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: UUID,
    data: ClientUpdate,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Обновить заказчика (name, contact_person). Только свой клиент (иначе 404)."""
    client = await _get_owned_client(session, client_id, company_id)

    before = {"name": client.name, "contact_person": client.contact_person}

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(client, field, value)

    await session.flush()

    await audit(
        session,
        action="update_client",
        entity_type="client",
        entity_id=client.id,
        before=before,
        after={"name": client.name, "contact_person": client.contact_person},
        actor_user_id=current_user.id,
        company_id=company_id,
    )

    await session.commit()
    # см. create_client: refresh подтягивает server-side updated_at в async-контексте.
    await session.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: UUID,
    session: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    """Удалить заказчика. 409 если на нём есть вакансии (включая архивные)."""
    client = await _get_owned_client(session, client_id, company_id)

    # Любые вакансии (включая архивные / soft-deleted) блокируют удаление —
    # бизнес-правило: заказчика с вакансиями нельзя осиротить (хотя FK и SET NULL,
    # обнуление client_id у вакансий молча — нежелательно, требуем явного переназначения).
    vacancy_count = (await session.execute(
        select(func.count(Vacancy.id)).where(Vacancy.client_id == client_id)
    )).scalar() or 0

    if vacancy_count > 0:
        raise ConflictError(
            f"Нельзя удалить заказчика: на нём {vacancy_count} вакансий. "
            "Сначала переназначьте или удалите их."
        )

    await audit(
        session,
        action="delete_client",
        entity_type="client",
        entity_id=client.id,
        before={"name": client.name, "contact_person": client.contact_person},
        actor_user_id=current_user.id,
        company_id=company_id,
    )

    await session.delete(client)
    await session.commit()