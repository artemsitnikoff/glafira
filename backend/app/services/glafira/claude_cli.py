"""Обёртка над claude CLI для интернет-разведки (WebSearch/WebFetch).

Аналог ArkadyJarvis: stateless prompt→answer через `claude --print`, инструменты по
умолчанию запрещены, разрешаем только то, что передали в allowed_tools. Авторизация —
долгоживущий OAuth-токен CLAUDE_CODE_OAUTH_TOKEN из `claude setup-token` (без рефреша).

Любой сбой (CLI не установлен, токен пуст/невалиден, таймаут, пустой ответ) → возвращаем
None. Вызывающий код обязан честно показать «разведка недоступна», НЕ фейк.
"""

import asyncio
import json
import logging
import os
import time

from ...config import settings

logger = logging.getLogger(__name__)


def resolve_claude_token() -> str:
    """Токен для claude CLI. ПРИОРИТЕТ — долгоживущий «большой» токен из env
    (CLAUDE_CODE_OAUTH_TOKEN, `claude setup-token`, ~1 год).

    ⚠️ Раньше приоритет был у общего токен-файла (CLAUDE_TOKEN_FILE) — это ломало
    разведку: файл шарится симлинком с ДРУГИМИ проектами (ArkadyJarvis и др.), которые
    перезаписывают/ротируют его под себя → у нас протухший/чужой токен → 401 «разведка
    недоступна». Урок ArkadyJarvis («сосед клобберит токен»): большой токен из env
    держим сами, никто его не трогает. Файл оставлен как ФОЛБЭК (legacy), если env пуст.
    Пусто и там, и там → разведка не выполняется.
    """
    env_token = settings.CLAUDE_CODE_OAUTH_TOKEN.strip()
    if env_token:
        return env_token

    # Фолбэк — общий токен-файл (только если big-token в env не задан).
    path = settings.CLAUDE_TOKEN_FILE
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = (data.get("access_token") or "").strip()
            if token:
                exp = data.get("expires_at", 0)
                if exp and exp < time.time() * 1000:
                    logger.warning(
                        "[claude_cli] токен из %s просрочен (ArkadyJarvis не обновил?) — пробуем как есть",
                        path,
                    )
                return token
            logger.warning("[claude_cli] в %s нет access_token", path)
        except (OSError, ValueError) as e:
            logger.warning("[claude_cli] не прочитать токен-файл %s: %s", path, e)
    return ""

async def claude_cli_complete(
    *,
    prompt: str,
    system: str | None = None,
    allowed_tools: str = "WebSearch,WebFetch",
    model: str | None = None,
    timeout: int | None = None,
) -> str | None:
    """Выполнить prompt через claude CLI. Возвращает текст ответа или None при сбое."""
    token = resolve_claude_token()
    if not token:
        logger.info("[claude_cli] токен не найден (ни файл, ни env) — разведка пропущена")
        return None

    timeout = timeout or settings.GLAFIRA_OSINT_TIMEOUT

    # Allowlist через --tools (НЕ денайлист): передаём ТОЛЬКО нужные инструменты, "" — все
    # выключены (prompt-only, без shell/файлов/веба → нет RCE, если текст промпта похож на
    # команду). Денайлист (--disallowed-tools) падает с кодом 1 «matches no known tool», как
    # только CLI переименует/удалит инструмент (напр. MultiEdit) — убивая ВСЮ разведку на
    # новом билде CLI. Allowlist устойчив к версиям. Урок ArkadyJarvis.
    tools = ",".join(t.strip() for t in allowed_tools.split(",") if t.strip())
    args = [
        settings.CLAUDE_CLI_PATH,
        "--print",
        "--output-format", "text",
        "--tools", tools,
    ]

    chosen_model = model or settings.GLAFIRA_OSINT_MODEL
    if chosen_model:
        args.extend(["--model", chosen_model])
    if system:
        args.extend(["--append-system-prompt", system])

    # env с токеном; CLAUDECODE убираем, чтобы CLI не считал себя вложенным.
    # Least-privilege: НЕ отдаём секреты приложения дочернему процессу (claude — доверенный
    # бинарь, но это лишняя поверхность при отладочном дампе env / компрометации пакета).
    # Чистим явные секреты по имени; PATH/HOME/локаль и пр. оставляем — нужны CLI.
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    for _k in list(env):
        _ku = _k.upper()
        if ("SECRET" in _ku or "PASSWORD" in _ku or _ku.endswith("_KEY")
                or _ku.endswith("_TOKEN") or _ku.endswith("_HASH")
                or _ku in ("DATABASE_URL", "FERNET_KEY", "JWT_SECRET")):
            env.pop(_k, None)
    env["CLAUDE_CODE_OAUTH_TOKEN"] = token  # ставим ПОСЛЕ чистки

    logger.info("[claude_cli] запуск разведки (model=%s, timeout=%ss)", chosen_model or "default", timeout)

    try:
        # cwd=/tmp — чтобы CLI не подхватил CLAUDE.md проекта как контекст
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd="/tmp",
        )
    except (FileNotFoundError, OSError) as e:
        logger.warning("[claude_cli] CLI не запустился (%s): %s", type(e).__name__, e)
        return None

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("[claude_cli] таймаут разведки за %sс", timeout)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[claude_cli] сбой связи с CLI: %s", e)
        return None

    if proc.returncode != 0:
        err = (stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip())[:300]
        logger.warning("[claude_cli] код %s: %s", proc.returncode, err)
        return None

    result = stdout.decode(errors="replace").strip()
    if not result:
        logger.warning("[claude_cli] пустой ответ")
        return None
    return result
