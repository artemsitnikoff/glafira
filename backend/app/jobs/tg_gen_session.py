"""Генератор Telethon StringSession (ИНТЕРАКТИВНО).

Запуск на VPS с терминалом (флаг -it обязателен!):
  docker compose -f docker-compose.prod.yml run --rm -it backend \
    python -m app.jobs.tg_gen_session

Сценарий: спросит номер телефона → код (придёт в Telegram/SMS) → облачный пароль
2FA (если включён) → напечатает готовую StringSession. Эту строку вставьте в UI
«Подключить готовой строкой сессии».

Использует TELEGRAM_API_ID / TELEGRAM_API_HASH из .env — те же должны ОСТАТЬСЯ в
.env (сессия привязана к этому api_id/api_hash).

⚠️ StringSession = полный доступ к аккаунту. Никому не показывайте, не коммитьте.
⚠️ Если код не приходит — это та же проблема доставки (soft-лимит/недоверенный
   api_id), генератор её не обходит: подождите или используйте api_id, под которым
   код доставляется.
"""

import os
import sys

# Корень проекта в путь (как в остальных app.jobs.*)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from telethon.sync import TelegramClient  # noqa: E402  (sync-обёртка для интерактива)
from telethon.sessions import StringSession  # noqa: E402

from app.config import settings  # noqa: E402


def main() -> None:
    api_id = settings.TELEGRAM_API_ID
    api_hash = settings.TELEGRAM_API_HASH

    print("=" * 56)
    print(" Генератор Telegram StringSession")
    print("=" * 56)
    if not api_id or not api_hash:
        print("!!! TELEGRAM_API_ID / TELEGRAM_API_HASH не заданы в .env.")
        return
    try:
        api_id_int = int(api_id)
    except (TypeError, ValueError):
        print(f"!!! TELEGRAM_API_ID не целое число: {api_id!r}")
        return

    if not sys.stdin or not sys.stdin.isatty():
        print("!!! Нет интерактивного терминала. Запускайте с флагом -it:")
        print("    docker compose -f docker-compose.prod.yml run --rm -it backend \\")
        print("      python -m app.jobs.tg_gen_session")
        return

    print(f"api_id={api_id_int}, api_hash=…{api_hash[-2:]}")
    print("Дальше введите данные по запросу (номер в формате +79991234567).\n")

    # Контекст-менеджер сам выполнит интерактивный вход (номер → код → 2FA).
    with TelegramClient(StringSession(), api_id_int, api_hash) as client:
        me = client.get_me()
        session_str = client.session.save()
        print("\n" + "=" * 56)
        print(" УСПЕХ — сессия создана")
        print("=" * 56)
        print(f"Аккаунт: id={getattr(me, 'id', None)} "
              f"@{getattr(me, 'username', None)} {getattr(me, 'phone', None)}")
        print("\nВаша StringSession (скопируйте ЦЕЛИКОМ, вставьте в UI):\n")
        print(session_str)
        print("\n⚠️ Это полный доступ к аккаунту — не показывайте никому, не коммитьте.")


if __name__ == "__main__":
    main()
