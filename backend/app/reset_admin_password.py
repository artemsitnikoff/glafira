"""One-off: сброс пароля admin@dclouds.ru → Glafira2026!.

Запуск:  python -m app.reset_admin_password

После использования файл можно удалить (это разовый сервис-скрипт).
"""
import asyncio
import sys

from sqlalchemy import update

from app.core.security import get_password_hash
from app.database import AsyncSessionLocal
from app.models import User

ADMIN_EMAIL = "admin@dclouds.ru"
ADMIN_PASSWORD = "Glafira2026!"


async def main() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(User)
            .where(User.email == ADMIN_EMAIL)
            .values(
                password_hash=get_password_hash(ADMIN_PASSWORD),
                is_active=True,
            )
        )
        await session.commit()
        rows = result.rowcount
        if rows == 0:
            print(f"ERROR: user {ADMIN_EMAIL} not found in DB", flush=True)
            return 1
        print(f"OK: password reset for {ADMIN_EMAIL} (rows updated: {rows})", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
