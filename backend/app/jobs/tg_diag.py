"""Диагностика доставки кода Telegram. НИЧЕГО в БД не пишет.

Запуск на VPS (в контейнере backend):
  docker compose -f docker-compose.prod.yml run --rm backend \
    python -m app.jobs.tg_diag +79991234567

  # переотправить (next_type, обычно SMS), если уже был send выше в той же сессии —
  # НЕ работает между запусками (сессия не сохраняется); для resend используйте UI.

Что печатает:
  - заданы ли TELEGRAM_API_ID / TELEGRAM_API_HASH (api_hash маскируется);
  - к какому дата-центру (DC) подключились;
  - ПОЛНЫЙ ответ Telegram на send_code_request: тип канала доставки
    (SentCodeTypeApp / Sms / Call / ...), резервный next_type, timeout, наличие hash;
  - при ошибке — класс исключения и traceback.

По этому сразу видно, КУДА Telegram реально отправил код и почему его может не быть
там, где вы ищете.
"""

import asyncio
import os
import sys
import traceback

# Корень проекта в путь (как в остальных app.jobs.*)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from telethon import TelegramClient  # noqa: E402
from telethon.sessions import StringSession  # noqa: E402

from app.config import settings  # noqa: E402


def _mask(s: str) -> str:
    s = s or ""
    return (s[:4] + "***" + s[-2:]) if len(s) > 8 else "***"


async def main(phone: str) -> None:
    api_id = settings.TELEGRAM_API_ID
    api_hash = settings.TELEGRAM_API_HASH

    print("=" * 56)
    print(" Telegram диагностика доставки кода")
    print("=" * 56)
    print(f"номер (вход):       {phone}")
    print(f"TELEGRAM_API_ID:    {'SET (' + str(api_id) + ')' if api_id else 'MISSING'}")
    print(f"TELEGRAM_API_HASH:  {'SET (len=' + str(len(api_hash)) + ', ' + _mask(api_hash) + ')' if api_hash else 'MISSING'}")

    if not api_id or not api_hash:
        print("\n!!! api creds отсутствуют в .env — Telegram не сможет отправить код.")
        print("    Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH (my.telegram.org) и перезапустите backend.")
        return
    try:
        api_id_int = int(api_id)
    except (TypeError, ValueError):
        print(f"\n!!! TELEGRAM_API_ID не целое число: {api_id!r}")
        return

    client = TelegramClient(StringSession(), api_id_int, api_hash)
    try:
        await client.connect()
        print(f"connected:          {client.is_connected()}")
        try:
            print(f"DC:                 {client.session.dc_id}")
        except Exception:
            pass

        try:
            sent = await client.send_code_request(phone)
        except Exception as e:  # noqa: BLE001
            print("\n=== send_code_request ОШИБКА ===")
            print(f"{type(e).__name__}: {e}")
            traceback.print_exc()
            return

        code_type = type(sent.type).__name__
        next_type = type(sent.next_type).__name__ if sent.next_type else None
        print("\n=== send_code_request УСПЕХ ===")
        print(f"канал доставки (type):  {code_type}")
        print(f"резервный (next_type):  {next_type}")
        print(f"timeout до resend:      {getattr(sent, 'timeout', None)} сек")
        print(f"phone_code_hash:        {'есть' if sent.phone_code_hash else 'ПУСТО'}")
        print("\n--- сырой ответ Telegram ---")
        print(sent.stringify())

        print("\n--- как читать ---")
        print("SentCodeTypeApp   → код ушёл в ПРИЛОЖЕНИЕ Telegram (чат «Telegram», 42777), не SMS.")
        print("SentCodeTypeSms   → код по SMS на номер.")
        print("SentCodeTypeCall  → код продиктуют звонком.")
        if code_type == "SentCodeTypeApp":
            print(
                "\nЭто App-код. Если в приложении его НЕТ:\n"
                "  • под этим номером нет активной сессии Telegram (некуда доставить) — нажмите\n"
                "    в UI «Отправить заново» (next_type обычно SMS), либо войдите в Telegram под номером;\n"
                "  • либо api_id/api_hash фильтруются антифродом (создайте свои на my.telegram.org)."
            )
    finally:
        await client.disconnect()


async def check_session(session_str: str) -> None:
    """Проверка ГОТОВОЙ StringSession с api_id/api_hash из .env. Печатает точную причину."""
    api_id = settings.TELEGRAM_API_ID
    api_hash = settings.TELEGRAM_API_HASH

    print("=" * 56)
    print(" Telegram диагностика готовой сессии")
    print("=" * 56)
    print(f"TELEGRAM_API_ID:    {'SET (' + str(api_id) + ')' if api_id else 'MISSING'}")
    print(f"TELEGRAM_API_HASH:  {'SET (len=' + str(len(api_hash)) + ', ' + _mask(api_hash) + ')' if api_hash else 'MISSING'}")
    print(f"длина строки сессии: {len(session_str)} символов (рабочая StringSession обычно 300–360)")

    if not api_id or not api_hash:
        print("\n!!! api creds отсутствуют в .env.")
        return
    try:
        api_id_int = int(api_id)
    except (TypeError, ValueError):
        print(f"\n!!! TELEGRAM_API_ID не целое число: {api_id!r}")
        return

    try:
        ss = StringSession(session_str)
    except Exception as e:  # noqa: BLE001
        print(f"\n!!! StringSession не распарсилась: {type(e).__name__}: {e}")
        print("    Строка повреждена/обрезана/не StringSession. Скопируйте её ЦЕЛИКОМ.")
        return

    client = TelegramClient(ss, api_id_int, api_hash)
    try:
        await client.connect()
        print(f"connected:          {client.is_connected()}")
        try:
            print(f"DC сессии:          {client.session.dc_id}")
        except Exception:
            pass
        try:
            authorized = await client.is_user_authorized()
            print(f"is_user_authorized: {authorized}")
            if authorized:
                me = await client.get_me()
                print("\n=== СЕССИЯ АВТОРИЗОВАНА ✓ ===")
                print(f"id={getattr(me, 'id', None)} username={getattr(me, 'username', None)} phone={getattr(me, 'phone', None)}")
                print("Эту строку можно вставлять в UI «Подключить готовой строкой сессии».")
            else:
                print("\n=== НЕ АВТОРИЗОВАНА ===")
                print("Пробую get_me для точной причины...")
                try:
                    await client.get_me()
                except Exception as e:  # noqa: BLE001
                    print(f"get_me: {type(e).__name__}: {e}")
                print(
                    "\nЧастые причины:\n"
                    "  • строка обрезана/с пробелами — скопируйте ЦЕЛИКОМ;\n"
                    "  • api_id/api_hash в .env НЕ те, чем создана сессия (сессия привязана к приложению);\n"
                    "  • сессия отозвана (Завершить сеанс) в другом проекте."
                )
        except Exception as e:  # noqa: BLE001
            print(f"\n=== ОШИБКА проверки ===\n{type(e).__name__}: {e}")
            traceback.print_exc()
    finally:
        await client.disconnect()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage:")
        print("  python -m app.jobs.tg_diag +79991234567        # проверить отправку кода")
        print('  python -m app.jobs.tg_diag --session "1ApW…"   # проверить готовую сессию')
        sys.exit(1)
    if sys.argv[1] == "--session":
        if len(sys.argv) < 3:
            print('usage: python -m app.jobs.tg_diag --session "1ApW…"')
            sys.exit(1)
        asyncio.run(check_session(sys.argv[2].strip()))
    else:
        asyncio.run(main(sys.argv[1].strip()))
