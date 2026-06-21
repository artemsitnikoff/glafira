"""Сервис для получения последних диалогов (чатов) главной страницы"""

from sqlalchemy import select, or_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from uuid import UUID

from ...models import Message, Application, VacancyTeam, Vacancy
from ...schemas.home import HomeDialogOut


async def list_recent_dialogs(session: AsyncSession, company_id: UUID, limit: int = 12, manager_user_id: UUID | None = None) -> list[HomeDialogOut]:
    """Получает последнее сообщение на каждого кандидата, company-scoped"""

    # Используем DISTINCT ON для получения последнего сообщения на каждого кандидата
    query = (
        select(Message)
        .where(Message.company_id == company_id)
        .options(
            joinedload(Message.candidate),
            joinedload(Message.application).joinedload(Application.vacancy)
        )
        .order_by(
            Message.candidate_id,
            Message.sent_at.desc()
        )
        .distinct(Message.candidate_id)
    )

    if manager_user_id is not None:
        allowed_candidate_ids = (
            select(Application.candidate_id)
            .where(
                Application.company_id == company_id,
                or_(
                    exists().select_from(VacancyTeam).where(
                        (VacancyTeam.vacancy_id == Application.vacancy_id)
                        & (VacancyTeam.user_id == manager_user_id)
                        & (VacancyTeam.company_id == company_id)
                    ),
                    exists().select_from(Vacancy).where(
                        (Vacancy.id == Application.vacancy_id)
                        & (Vacancy.responsible_user_id == manager_user_id)
                        & (Vacancy.company_id == company_id)
                    ),
                ),
            )
        )
        query = query.where(Message.candidate_id.in_(allowed_candidate_ids))

    result = await session.execute(query)
    messages = result.scalars().all()

    # Пересортировать результат по sent_at desc в Python и взять [:limit]
    messages_sorted = sorted(messages, key=lambda msg: msg.sent_at, reverse=True)[:limit]

    dialogs = []
    for message in messages_sorted:
        # candidate_name
        candidate_name = message.candidate.full_name if message.candidate else "Неизвестный"

        # vacancy через application
        vacancy_id = None
        vacancy_name = None
        if message.application_id and message.application and message.application.vacancy:
            vacancy_id = message.application.vacancy.id
            vacancy_name = message.application.vacancy.name

        # preview - обрезаем body до ~120 символов
        preview = (message.body or '')[:120]

        # waiting = True если последнее сообщение direction=='in' (последнее слово за кандидатом)
        waiting = (message.direction == 'in')

        dialogs.append(HomeDialogOut(
            candidate_id=message.candidate_id,
            candidate_name=candidate_name,
            vacancy_id=vacancy_id,
            vacancy_name=vacancy_name,
            channel=message.channel,
            preview=preview,
            sent_at=message.sent_at,
            last_sender_type=message.sender_type,
            waiting=waiting
        ))

    return dialogs