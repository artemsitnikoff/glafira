from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ...database import get_db
from ...deps import get_current_company_id, get_current_user
from ...models import Client, User
from ...schemas.client import ClientOut, ClientCreate
from ...services.audit import audit

router = APIRouter()


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
    return client