"""Разовая диагностика пароля admin@dclouds.ru.

Запуск:
  docker compose -f docker-compose.prod.yml run --rm backend python -m app.diagnose_admin
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.security import verify_password
from app.database import AsyncSessionLocal
from app.models import User


async def main() -> int:
    target_email = "admin@dclouds.ru"
    expected_password = "Glafira2026!"

    # Версии библиотек хеширования
    try:
        import bcrypt
        bcrypt_ver = getattr(bcrypt, "__version__", "?")
    except Exception as e:
        bcrypt_ver = f"import failed: {e}"
    try:
        import passlib
        passlib_ver = passlib.__version__
    except Exception as e:
        passlib_ver = f"import failed: {e}"
    print(f"bcrypt    version: {bcrypt_ver}")
    print(f"passlib   version: {passlib_ver}")
    print()

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(User))).scalars().all()
        print(f"Users в БД: {len(rows)}")
        for u in rows:
            ph = u.password_hash or ""
            print(f"  - email={u.email!r:32} active={u.is_active} hash_prefix={ph[:7]!r} hash_len={len(ph)}")
        print()

        admin = next((u for u in rows if u.email == target_email), None)
        if admin is None:
            print(f"❌ user {target_email!r} не найден в БД")
            return 1

        ph = admin.password_hash or ""
        print(f"=== verify_password({expected_password!r}, hash) для {target_email} ===")
        try:
            ok = verify_password(expected_password, ph)
            print(f"  result: {ok}")
            if ok:
                print("  ✅ Пароль на самом деле валидируется. Если /auth/login отдаёт 401 — баг в auth-сервисе или email регистр.")
            else:
                print("  ❌ Хеш в БД не соответствует паролю 'Glafira2026!'. Кто-то его перезаписал, или bcrypt verify сломан.")
        except Exception as e:
            print(f"  💥 verify_password raised: {type(e).__name__}: {e}")
            print("  Это значит библиотеки bcrypt/passlib не уживаются — нужно фиксить версии.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
