"""Диагностика + сброс пароля админа (на случай «не могу залогиниться»).

Запуск на VPS:
    docker compose -f docker-compose.prod.yml run --rm backend python -m app.reset_admin

Печатает диагностику (версия bcrypt, есть ли юзер, проходит ли verify ДО),
затем сбрасывает пароль админа на дефолтный из app.seed и проверяет verify ПОСЛЕ.
Идемпотентно, безопасно гонять повторно.
"""
import asyncio
import logging

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.core.security import get_password_hash, verify_password
from app.models import User
from app.seed import ADMIN_EMAIL, ADMIN_PASSWORD

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    try:
        import bcrypt
        print(f"[diag] bcrypt version: {getattr(bcrypt, '__version__', '?')}")
    except Exception as e:  # pragma: no cover
        print(f"[diag] bcrypt import error: {e!r}")

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == ADMIN_EMAIL))
        ).scalar_one_or_none()

        if user is None:
            print(f"[diag] ❌ Пользователь {ADMIN_EMAIL} НЕ найден в БД.")
            print("[diag]    → база пустая/пересоздана? Запусти: python -m app.seed")
            return

        print(f"[diag] ✓ Найден: {user.email}, is_active={user.is_active}, hash={user.password_hash[:7]}…")

        try:
            ok_before = verify_password(ADMIN_PASSWORD, user.password_hash)
            print(f"[diag] verify(дефолтный пароль) ДО сброса: {ok_before}")
        except Exception as e:
            print(f"[diag] verify ДО сброса УПАЛ: {e!r}")

        user.password_hash = get_password_hash(ADMIN_PASSWORD)
        user.is_active = True
        await session.commit()

        ok_after = verify_password(ADMIN_PASSWORD, user.password_hash)
        print(f"[reset] ✓ Пароль админа сброшен на дефолтный (из app.seed). verify ПОСЛЕ: {ok_after}")
        print(f"[reset]   Логинься под {ADMIN_EMAIL} с дефолтным паролем из app/seed.py")


if __name__ == "__main__":
    asyncio.run(main())
