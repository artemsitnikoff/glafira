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
from app.services.glafira.verify import _OSINT_PROMPT_TMPL

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


async def real_recon(query: str, model: str) -> None:
    _hdr(f"ТЕКУЩИЙ прод-промпт (строгий JSON), модель={model}")
    s = time.time()
    raw = await claude_cli_complete(
        prompt=_OSINT_PROMPT_TMPL.replace("{query}", query),
        system=None,
        allowed_tools="WebSearch,WebFetch",
        model=model,
        timeout=150,
    )
    print(f"[json-{model}] {time.time() - s:.1f}с, {len(raw or '')} симв", flush=True)
    print(raw or "(None)", flush=True)


# Свободный нарратив как в ArkadyJarvis (stirlitz_person.md): без строгого JSON, агрессивно,
# с хеджированием — НЕ бинарный «не уверен → выкинул». Тест: находит ли он человека вообще.
_NARRATIVE_PROMPT = """Ты — AI-разведчик для рекрутера. Тебе дали человека (ФИО + контекст: компания, город, должность, контакты). Найди в ОТКРЫТОМ интернете его публичную профессиональную активность — используй WebSearch и WebFetch, сделай 4–6 РАЗНЫХ запросов (ФИО+компания, ФИО+город, ФИО+должность, по нику, по платформам GitHub / Habr / Stack Overflow / Telegram / vc.ru / ВКонтакте / LinkedIn). Не сдавайся после одного запроса.

Человек:
{query}

Собери карточку: кто это, профили (со ССЫЛКАМИ), telegram-каналы, доклады/статьи/интервью/упоминания (короткая цитата + ССЫЛКА). Что нашёл с высокой вероятностью того же человека — включай (можно с пометкой «вероятно»). Что не нашёл — прямо пиши «не нашёл». Ссылки обязательны, не выдумывай факты/числа. Ответ — свободным текстом."""


async def narrative_recon(query: str, model: str) -> None:
    _hdr(f"НАРРАТИВ как в ArkadyJarvis (свободный текст), модель={model}")
    s = time.time()
    raw = await claude_cli_complete(
        prompt=_NARRATIVE_PROMPT.replace("{query}", query),
        system=None,
        allowed_tools="WebSearch,WebFetch",
        model=model,
        timeout=180,
    )
    print(f"[narr-{model}] {time.time() - s:.1f}с, {len(raw or '')} симв", flush=True)
    print("---- RAW ----", flush=True)
    print(raw or "(None — сбой/таймаут)", flush=True)


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
        print("\nЗАПРОС:", arg_q, flush=True)
        # Сравниваем: строгий JSON (текущий прод) vs свободный нарратив (ArkadyJarvis), opus vs sonnet.
        await real_recon(arg_q, "opus")
        await narrative_recon(arg_q, "sonnet")
        await narrative_recon(arg_q, "opus")
        print("\nИтог: если НАРРАТИВ нашёл, а JSON пусто → причина в строгом промпте, перевожу на двухшаг.", flush=True)
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
