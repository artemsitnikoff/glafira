"""ВРЕМЕННЫЙ диагностический скрипт OSINT-разведки (claude CLI). Удалить после настройки.

Без аргумента — замеры токена/таймингов (база, sonnet, opus) + реальный промпт на дефолте.
С аргументом — гонит ТОЛЬКО реальный промпт разведки на твоих данных и печатает СЫРОЙ вывод
(видно: пусто {"profiles":[],...} = опус осторожничает, или реально находит).

Запуск на VPS:
  docker compose -f docker-compose.prod.yml exec backend env PYTHONPATH=/app \
    python scripts/osint_diag.py "ФИО: Иван Петров. Город: Москва. Должность: Python-разработчик. Компания: X"
"""

import asyncio
import json
import os
import sys
import time

from app.config import settings
from app.services.glafira.claude_cli import resolve_claude_token, claude_cli_complete
from app.services.glafira.verify import _OSINT_SYSTEM_PROMPT

DEFAULT_Q = "ФИО: Линус Торвальдс. Должность: создатель ядра Linux и Git"


def _hdr(t: str) -> None:
    print("\n" + "=" * 8 + " " + t + " " + "=" * 8, flush=True)


async def _timed(label: str, **kwargs) -> None:
    s = time.time()
    try:
        r = await claude_cli_complete(**kwargs)
    except Exception as e:  # noqa: BLE001
        print(f"[{label}] ИСКЛЮЧЕНИЕ за {time.time() - s:.1f}с: {type(e).__name__}: {e}", flush=True)
        return
    dur = time.time() - s
    print(f"[{label}] {'OK' if r else 'None'} за {dur:.1f}с, {len(r or '')} симв:", flush=True)
    print((r or "(None)")[:600], flush=True)


async def real_recon(query: str) -> None:
    _hdr("РЕАЛЬНЫЙ промпт разведки (СЫРОЙ вывод opus)")
    print("запрос:", query, flush=True)
    s = time.time()
    raw = await claude_cli_complete(
        prompt=f"Данные кандидата (только публично-неконтактные):\n{query}\n\nВерни ТОЛЬКО JSON.",
        system=_OSINT_SYSTEM_PROMPT,
        allowed_tools="WebSearch,WebFetch",
        model=settings.GLAFIRA_OSINT_MODEL or "opus",
        timeout=150,
    )
    print(f"[real] {time.time() - s:.1f}с, {len(raw or '')} симв", flush=True)
    print("---- RAW ----", flush=True)
    print(raw or "(None — сбой/таймаут, см. логи)", flush=True)


async def main() -> None:
    _hdr("ТОКЕН / КОНФИГ")
    tok = resolve_claude_token()
    print("токен есть:", bool(tok), "| модель:", settings.GLAFIRA_OSINT_MODEL,
          "| timeout:", settings.GLAFIRA_OSINT_TIMEOUT, flush=True)
    p = settings.CLAUDE_TOKEN_FILE
    if p and os.path.exists(p):
        try:
            d = json.load(open(p))
            print("файл: access_token есть:", bool(d.get("access_token")),
                  "| не протух:", bool(d.get("expires_at")) and d["expires_at"] > time.time() * 1000, flush=True)
        except Exception as e:  # noqa: BLE001
            print("файл не читается:", e, flush=True)
    if not tok:
        print("Токена нет — стоп.", flush=True)
        return

    arg_q = " ".join(sys.argv[1:]).strip()
    if arg_q:
        # Передали кандидата — гоним только реальный промпт на нём
        await real_recon(arg_q)
        return

    _hdr("1) БАЗА без веба, sonnet")
    await _timed("base", prompt="Ответь одним словом: тест", allowed_tools="", model="sonnet", timeout=60)
    _hdr("2) WebSearch sonnet")
    await _timed("web-sonnet", prompt="Найди GitHub Линуса Торвальдса, верни URL.",
                 allowed_tools="WebSearch,WebFetch", model="sonnet", timeout=120)
    await real_recon(DEFAULT_Q)
    print("\nЗапусти с реальным кандидатом: ... osint_diag.py \"ФИО: ... Город: ... Должность: ...\"", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
