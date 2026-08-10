"""Подсчёт непрочитанных сообщений по диалогам (модуль «Чаты», фаза 1).

Диалог = кандидат. Непрочитанность считается на лету: входящее сообщение
(`Message.direction == 'in'`) непрочитано, если `sent_at` позже отметки
`MessageRead.last_read_at` этого юзера по этому кандидату. Строки MessageRead
нет → отметка = -infinity → все входящие непрочитаны.

Все хелперы строго скоуплены по company_id + user_id (пер-юзер изоляция, §2.3).
Тела сообщений не тянутся — только агрегаты COUNT.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, exists, func, literal, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Application, Candidate, Message, MessageRead, Vacancy, VacancyTeam
from ..schemas.chat import ChatDialogOut, ChatMetaOut
from .integrations.hh.service import get_valid_access_token

# «Никогда не читал» — любое sent_at позже -infinity → входящее непрочитано.
# Используется в COALESCE, когда LEFT JOIN не нашёл строку MessageRead.
_NEG_INF = literal_column("'-infinity'::timestamptz")


def _manager_allowed_candidate_ids(company_id: UUID, manager_user_id: UUID):
    """Подзапрос candidate_id, доступных менеджеру (зеркало home.list_recent_dialogs).

    Менеджер видит только кандидатов из вакансий, где он в команде (VacancyTeam) ИЛИ
    ответственный (responsible_user_id). Company-scoped. Возвращает column-подзапрос
    для `Message.candidate_id.in_(...)`.
    """
    return (
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


async def unread_count(
    session: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    candidate_id: UUID,
) -> int:
    """Число непрочитанных входящих в диалоге с одним кандидатом (company-scoped)."""
    last_read = (
        select(MessageRead.last_read_at)
        .where(
            MessageRead.company_id == company_id,
            MessageRead.user_id == user_id,
            MessageRead.candidate_id == candidate_id,
        )
        .scalar_subquery()
    )
    stmt = select(func.count(Message.id)).where(
        Message.company_id == company_id,
        Message.candidate_id == candidate_id,
        Message.direction == "in",
        Message.sent_at > func.coalesce(last_read, _NEG_INF),
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def unread_counts_bulk(
    session: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    candidate_ids: list[UUID],
) -> dict[UUID, int]:
    """Непрочитанные по множеству диалогов ОДНИМ запросом (без N+1).

    SQL-идея:
        SELECT m.candidate_id, COUNT(m.id)
        FROM messages m
        LEFT JOIN message_reads r
               ON r.candidate_id = m.candidate_id
              AND r.user_id      = :user_id
              AND r.company_id   = :company_id
        WHERE m.company_id  = :company_id
          AND m.candidate_id = ANY(:candidate_ids)
          AND m.direction    = 'in'
          AND m.sent_at > COALESCE(r.last_read_at, '-infinity'::timestamptz)
        GROUP BY m.candidate_id;

    Условие по user_id/company_id стоит в ON (а не в WHERE) — иначе LEFT JOIN
    выродится в INNER и потеряет кандидатов без строки MessageRead (у которых
    непрочитано ВСЁ). Кандидаты без входящих в результат GROUP BY не попадут —
    их добиваем нулём в Python.
    """
    if not candidate_ids:
        return {}

    stmt = (
        select(Message.candidate_id, func.count(Message.id))
        .select_from(Message)
        .outerjoin(
            MessageRead,
            and_(
                MessageRead.candidate_id == Message.candidate_id,
                MessageRead.user_id == user_id,
                MessageRead.company_id == company_id,
            ),
        )
        .where(
            Message.company_id == company_id,
            Message.candidate_id.in_(candidate_ids),
            Message.direction == "in",
            Message.sent_at > func.coalesce(MessageRead.last_read_at, _NEG_INF),
        )
        .group_by(Message.candidate_id)
    )
    result = await session.execute(stmt)

    counts: dict[UUID, int] = {cid: 0 for cid in candidate_ids}
    for candidate_id, cnt in result.all():
        counts[candidate_id] = int(cnt)
    return counts


async def mark_read(
    session: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    candidate_id: UUID,
    at: datetime | None = None,
) -> None:
    """Отметить диалог прочитанным до момента `at` (по умолчанию — сейчас).

    Upsert по (user_id, candidate_id): вставка новой строки MessageRead или
    сдвиг last_read_at существующей. Company-scoped (company_id пишется при
    вставке; при конфликте строка гарантированно того же кандидата → компании).
    """
    moment = at or datetime.now(timezone.utc)
    stmt = (
        pg_insert(MessageRead)
        .values(
            company_id=company_id,
            user_id=user_id,
            candidate_id=candidate_id,
            last_read_at=moment,
        )
        .on_conflict_do_update(
            constraint="uq_message_read_user_candidate",
            set_={"last_read_at": moment, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)


async def mark_all_read(
    session: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    manager_user_id: UUID | None = None,
) -> int:
    """Пометить прочитанными ВСЕ диалоги юзера ОДНИМ bulk-upsert (без цикла/N+1).

    Для КАЖДОГО кандидата этой компании, у которого есть входящее сообщение,
    вставляет/сдвигает строку MessageRead(last_read_at=now) юзера. Один стейтмент:
    `INSERT ... SELECT DISTINCT ... ON CONFLICT (user_id, candidate_id) DO UPDATE`.

    SQL-идея (один запрос):
        INSERT INTO message_reads (company_id, user_id, candidate_id, last_read_at)
        SELECT DISTINCT :company_id, :user_id, m.candidate_id, :now
        FROM messages m
        WHERE m.company_id = :company_id
          AND m.direction  = 'in'
          AND EXISTS (SELECT 1 FROM candidates c            -- не трогаем soft-удалённых
                       WHERE c.id = m.candidate_id AND c.deleted_at IS NULL)
          [AND m.candidate_id IN (<вакансии менеджера>)]    -- только для роли manager
        ON CONFLICT (user_id, candidate_id)
        DO UPDATE SET last_read_at = :now, updated_at = now();

    Константы (company_id/user_id/now) одинаковы во всех строках → `SELECT DISTINCT`
    схлопывается по candidate_id, давая ровно одну вставляемую строку на кандидата.
    Строго company_id + user_id (пер-юзер: чужие ReadState не трогает, §2.3).
    `manager_user_id` (роль manager) ограничивает кандидатами его вакансий
    (тот же `_manager_allowed_candidate_ids`, что в total_unread/list_dialogs).

    Возвращает число затронутых кандидатов (rowcount: вставленные + обновлённые).
    """
    now = datetime.now(timezone.utc)

    # SELECT DISTINCT со скалярными константами (company_id/user_id/now) + candidate_id.
    src = (
        select(
            literal(company_id, type_=MessageRead.company_id.type).label("company_id"),
            literal(user_id, type_=MessageRead.user_id.type).label("user_id"),
            Message.candidate_id.label("candidate_id"),
            literal(now, type_=MessageRead.last_read_at.type).label("last_read_at"),
        )
        .where(
            Message.company_id == company_id,
            Message.direction == "in",
            # Не помечаем soft-удалённых кандидатов (зеркало фильтра в total_unread).
            exists().where(
                Candidate.id == Message.candidate_id,
                Candidate.deleted_at.is_(None),
            ),
        )
        .distinct()
    )
    if manager_user_id is not None:
        src = src.where(
            Message.candidate_id.in_(
                _manager_allowed_candidate_ids(company_id, manager_user_id)
            )
        )

    stmt = (
        pg_insert(MessageRead)
        .from_select(["company_id", "user_id", "candidate_id", "last_read_at"], src)
        .on_conflict_do_update(
            constraint="uq_message_read_user_candidate",
            set_={"last_read_at": now, "updated_at": func.now()},
        )
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


async def total_unread(
    session: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    manager_user_id: UUID | None = None,
) -> int:
    """Суммарно непрочитанных входящих по ВСЕМ диалогам юзера (бейдж сайдбара).

    Один лёгкий агрегат-запрос. LEFT JOIN messages→message_reads по
    (candidate_id, user_id, company_id): message_reads уникальна на пару
    (user_id, candidate_id) → фан-аута нет, каждое сообщение матчится не более
    чем к одной строке. Company-scoped.

    `manager_user_id` (для роли manager) ограничивает подсчёт кандидатами его
    вакансий — иначе бейдж превысил бы число диалогов, которые он может открыть.
    """
    stmt = (
        select(func.count(Message.id))
        .select_from(Message)
        .outerjoin(
            MessageRead,
            and_(
                MessageRead.candidate_id == Message.candidate_id,
                MessageRead.user_id == user_id,
                MessageRead.company_id == company_id,
            ),
        )
        .where(
            Message.company_id == company_id,
            Message.direction == "in",
            Message.sent_at > func.coalesce(MessageRead.last_read_at, _NEG_INF),
            # ⚠️ Исключаем soft-удалённых кандидатов: их диалоги не в списке (list_dialogs
            # фильтрует deleted_at) и read по ним даёт 404 → иначе бейдж «залипал» бы >0.
            exists().where(
                Candidate.id == Message.candidate_id,
                Candidate.deleted_at.is_(None),
            ),
        )
    )
    if manager_user_id is not None:
        stmt = stmt.where(
            Message.candidate_id.in_(
                _manager_allowed_candidate_ids(company_id, manager_user_id)
            )
        )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_dialogs(
    session: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    manager_user_id: UUID | None = None,
    q: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> list[ChatDialogOut]:
    """Список диалогов для попапа: ПО КАНДИДАТУ (диалог = человек).

    Строится БЕЗ N+1 ровно тремя запросами независимо от числа диалогов:
      1) DISTINCT ON (candidate_id) — последнее сообщение каждого кандидата
         (company-/manager-scoped), с JOIN candidate + application→vacancy для
         контекста, поиском `q` и пагинацией;
      2) chats.unread_counts_bulk — непрочитанные ОДНИМ GROUP BY по собранным
         candidate_ids (пер-юзер);
      3) MAX(sent_at) входящих ОДНИМ GROUP BY — last_inbound_at («был на связи»).

    Контекст (vacancy/channel/preview/sender) — от ПОСЛЕДНЕГО сообщения диалога.
    Telegram-сообщения без application_id дают ОДИН диалог на человека независимо
    от числа вакансий; hh-тред контекстуализируется вакансией последнего сообщения.
    """
    # 1) Последнее сообщение на каждого кандидата (DISTINCT ON) — company-scoped.
    base = select(
        Message.candidate_id.label("candidate_id"),
        Message.channel.label("channel"),
        Message.body.label("body"),
        Message.sent_at.label("sent_at"),
        Message.sender_type.label("sender_type"),
        Message.application_id.label("application_id"),
    ).where(Message.company_id == company_id)

    if manager_user_id is not None:
        base = base.where(
            Message.candidate_id.in_(
                _manager_allowed_candidate_ids(company_id, manager_user_id)
            )
        )

    base = base.order_by(
        Message.candidate_id, Message.sent_at.desc(), Message.id.desc()
    ).distinct(Message.candidate_id)
    last_sq = base.subquery("last_msg")

    name_expr = func.concat_ws(
        " ", Candidate.last_name, Candidate.first_name, Candidate.middle_name
    )

    outer = (
        select(
            last_sq.c.candidate_id,
            last_sq.c.channel,
            last_sq.c.body,
            last_sq.c.sent_at,
            last_sq.c.sender_type,
            Candidate.last_name,
            Candidate.first_name,
            Candidate.middle_name,
            Candidate.extra,
            Vacancy.id.label("vacancy_id"),
            Vacancy.name.label("vacancy_name"),
        )
        .select_from(last_sq)
        .join(Candidate, Candidate.id == last_sq.c.candidate_id)
        .outerjoin(Application, Application.id == last_sq.c.application_id)
        .outerjoin(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(Candidate.deleted_at.is_(None))
    )

    if q and q.strip():
        like = f"%{q.strip()}%"
        # Поиск по имени кандидата ИЛИ названию вакансии последнего сообщения.
        outer = outer.where(or_(name_expr.ilike(like), Vacancy.name.ilike(like)))

    outer = outer.order_by(
        last_sq.c.sent_at.desc(), last_sq.c.candidate_id
    ).limit(limit).offset(offset)

    rows = (await session.execute(outer)).all()

    candidate_ids = [r.candidate_id for r in rows]

    # 2) Непрочитанные — один bulk-запрос (пер-юзер).
    unread_map = await unread_counts_bulk(
        session, company_id=company_id, user_id=user_id, candidate_ids=candidate_ids
    )

    # 3) last_inbound_at — один GROUP BY по тем же кандидатам.
    inbound_map: dict[UUID, datetime] = {}
    if candidate_ids:
        inbound_rows = await session.execute(
            select(Message.candidate_id, func.max(Message.sent_at))
            .where(
                Message.company_id == company_id,
                Message.candidate_id.in_(candidate_ids),
                Message.direction == "in",
            )
            .group_by(Message.candidate_id)
        )
        inbound_map = {cid: ts for cid, ts in inbound_rows.all()}

    dialogs: list[ChatDialogOut] = []
    for r in rows:
        parts = [r.last_name, r.first_name]
        if r.middle_name:
            parts.append(r.middle_name)
        name = " ".join(p for p in parts if p)
        dialogs.append(
            ChatDialogOut(
                candidate_id=r.candidate_id,
                name=name,
                avatar_url=(r.extra or {}).get("photo_url"),
                vacancy_id=r.vacancy_id,
                vacancy_name=r.vacancy_name,
                channel=r.channel,
                preview=(r.body or "")[:120],
                sent_at=r.sent_at,
                last_sender_type=r.sender_type,
                unread_count=unread_map.get(r.candidate_id, 0),
                last_inbound_at=inbound_map.get(r.candidate_id),
            )
        )
    return dialogs


async def get_candidate_chat_meta(
    session: AsyncSession,
    *,
    company_id: UUID,
    candidate_id: UUID,
) -> ChatMetaOut | None:
    """Мета каналов кандидата для композера/шапки. None → кандидата нет (→ 404).

    available_channels честны: 'hh' СТРОГО при наличии Application.hh_chat_id;
    'telegram' — при наличии контакта (телефон / tg-username / закэшированный
    tg_user_id). Никаких Max/WhatsApp/SMS/Email и никаких выдуманных статусов.
    """
    # Локальный импорт: не тянуть Telegram-модуль в импорт-тайм сервиса чатов.
    from .integrations.telegram.service import extract_telegram_username

    candidate = (
        await session.execute(
            select(Candidate).where(
                Candidate.id == candidate_id,
                Candidate.company_id == company_id,
                Candidate.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if candidate is None:
        return None

    # hh доступен ТОЛЬКО при реальном диалоге (hh_chat_id) — company-scoped.
    hh_available = bool(
        (
            await session.execute(
                select(func.count(Application.id)).where(
                    Application.company_id == company_id,
                    Application.candidate_id == candidate_id,
                    Application.hh_chat_id.isnot(None),
                )
            )
        ).scalar_one()
    )

    tg_username = extract_telegram_username(candidate.messengers or [])
    tg_uid = (candidate.extra or {}).get("tg_user_id")
    telegram_available = bool(candidate.phone or tg_username or tg_uid)

    last_in = (
        await session.execute(
            select(Message.channel, Message.sent_at)
            .where(
                Message.company_id == company_id,
                Message.candidate_id == candidate_id,
                Message.direction == "in",
            )
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
    ).first()
    last_inbound_channel = last_in[0] if last_in else None
    last_inbound_at = last_in[1] if last_in else None

    available_channels: list[str] = []
    if telegram_available:
        available_channels.append("telegram")
    if hh_available:
        available_channels.append("hh")

    # default: предпочтительный (если telegram и доступен) → канал последнего
    # входящего (если доступен) → первый доступный → None.
    default_channel: str | None = None
    if candidate.preferred_channel == "telegram" and "telegram" in available_channels:
        default_channel = "telegram"
    elif last_inbound_channel and last_inbound_channel in available_channels:
        default_channel = last_inbound_channel
    elif available_channels:
        default_channel = available_channels[0]

    return ChatMetaOut(
        candidate_id=candidate_id,
        hh_available=hh_available,
        telegram_available=telegram_available,
        last_inbound_at=last_inbound_at,
        last_inbound_channel=last_inbound_channel,
        default_channel=default_channel,
        available_channels=available_channels,
    )


async def sync_candidate_hh_inbound(
    session: AsyncSession,
    *,
    company_id: UUID,
    candidate_id: UUID,
) -> dict:
    """On-demand приём hh для ОДНОГО кандидата (зеркало telegram/sync).

    Переиспользует `jobs.poll_hh_messages.poll_chat_messages` — ту же логику, что
    крон: тянет сообщения по всем Application этого кандидата с hh_chat_id
    (company-scoped), дедуп по external_id (повторный вызов не плодит). Коммит —
    на вызывающем (роут). Возвращает {"imported": N}.

    Нет hh_chat_id у кандидата → {"imported": 0} (не ошибка). Интеграция hh не
    подключена/токен недоступен → {"imported": 0} (graceful, без исключения).
    """
    # Ленивый импорт: не тащить jobs-модуль (и его logging.basicConfig) в импорт-тайм.
    from ..jobs.poll_hh_messages import poll_chat_messages

    rows = (
        await session.execute(
            select(Application.hh_chat_id, Application.id).where(
                Application.company_id == company_id,
                Application.candidate_id == candidate_id,
                Application.hh_chat_id.isnot(None),
            )
        )
    ).all()
    if not rows:
        return {"imported": 0}

    try:
        access_token = await get_valid_access_token(session, company_id)
    except Exception:
        # hh не подключён/токен протух — не роняем открытие чата, просто нечего тянуть.
        return {"imported": 0}

    imported = 0
    for chat_id, application_id in rows:
        imported += await poll_chat_messages(
            session, company_id, chat_id, candidate_id, application_id, access_token
        )
    return {"imported": imported}
