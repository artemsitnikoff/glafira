"""ВРЕМЕННЫЙ диагностический скрипт OSINT-разведки (claude CLI). Удалить после настройки.

Замеряет: статус токена, базовую скорость CLI (без веба), длительность WebSearch на
sonnet и на opus. По числам выбираем модель + GLAFIRA_OSINT_TIMEOUT.

Запуск на VPS (после git pull + автодеплой/пересборка бека):
  docker compose -f docker-compose.prod.yml exec backend python scripts/osint_diag.py

Если ждать пересборку лень — скопировать в работающий контейнер и запустить:
  docker compose -f docker-compose.prod.yml cp backend/scripts/osint_diag.py backend:/tmp/d.py
  docker compose -f docker-compose.prod.yml exec backend python /tmp/d.py
"""

import asyncio
import json
import os
import time

from app.config import settings
from app.services.glafira.claude_cli import resolve_claude_token, claude_cli_complete

QUERY = "Найди профиль Линуса Торвальдса на GitHub через веб-поиск, верни только URL."


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
    if r is None:
        print(f"[{label}] None (сбой/таймаут) за {dur:.1f}с — см. логи backend выше", flush=True)
    else:
        print(f"[{label}] OK за {dur:.1f}с, {len(r)} симв. Первые 400:", flush=True)
        print(r[:400], flush=True)


async def main() -> None:
    _hdr("ТОКЕН / КОНФИГ")
    tok = resolve_claude_token()
    print("resolve_claude_token непустой:", bool(tok), flush=True)
    print("CLAUDE_TOKEN_FILE:", settings.CLAUDE_TOKEN_FILE or "(пусто)", flush=True)
    print("GLAFIRA_OSINT_MODEL:", settings.GLAFIRA_OSINT_MODEL, "| timeout:", settings.GLAFIRA_OSINT_TIMEOUT, flush=True)
    p = settings.CLAUDE_TOKEN_FILE
    if p and os.path.exists(p):
        try:
            d = json.load(open(p))
            exp = d.get("expires_at", 0)
            print("файл: access_token есть:", bool(d.get("access_token")),
                  "| не протух:", bool(exp) and exp > time.time() * 1000, flush=True)
        except Exception as e:  # noqa: BLE001
            print("файл не читается:", e, flush=True)
    if not tok:
        print("Токена нет — дальше смысла нет.", flush=True)
        return

    _hdr("1) БАЗА: без веба, sonnet (timeout 60) — холодный старт CLI")
    await _timed("base", prompt="Ответь одним словом: тест", allowed_tools="", model="sonnet", timeout=60)

    _hdr("2) WebSearch sonnet (timeout 120) — реальная длительность")
    await _timed("web-sonnet", prompt=QUERY, allowed_tools="WebSearch,WebFetch", model="sonnet", timeout=120)

    _hdr("3) WebSearch opus (timeout 120) — для сравнения")
    await _timed("web-opus", prompt=QUERY, allowed_tools="WebSearch,WebFetch", model="opus", timeout=120)

    print("\nГотово. Скинь длительности — выберем модель и GLAFIRA_OSINT_TIMEOUT.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
