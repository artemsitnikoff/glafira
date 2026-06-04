"""Обёртка над claude CLI для интернет-разведки (WebSearch/WebFetch).

Аналог ArkadyJarvis: stateless prompt→answer через `claude --print`, инструменты по
умолчанию запрещены, разрешаем только то, что передали в allowed_tools. Авторизация —
долгоживущий OAuth-токен CLAUDE_CODE_OAUTH_TOKEN из `claude setup-token` (без рефреша).

Любой сбой (CLI не установлен, токен пуст/невалиден, таймаут, пустой ответ) → возвращаем
None. Вызывающий код обязан честно показать «разведка недоступна», НЕ фейк.
"""

import asyncio
import logging

from ...config import settings

logger = logging.getLogger(__name__)

# По умолчанию все инструменты выключены — иначе CLI может выполнять shell/файлы по
# тексту промпта. Из этого списка вычитаем то, что явно разрешили (allowed_tools).
_DISALLOWED_TOOLS = (
    "Bash,BashOutput,KillShell,"
    "Read,Write,Edit,MultiEdit,NotebookEdit,"
    "Glob,Grep,"
    "WebFetch,WebSearch,"
    "Task,Agent,SlashCommand,TodoWrite,ExitPlanMode"
)


async def claude_cli_complete(
    *,
    prompt: str,
    system: str | None = None,
    allowed_tools: str = "WebSearch,WebFetch",
    model: str | None = None,
    timeout: int | None = None,
) -> str | None:
    """Выполнить prompt через claude CLI. Возвращает текст ответа или None при сбое."""
    if not settings.CLAUDE_CODE_OAUTH_TOKEN:
        logger.info("[claude_cli] CLAUDE_CODE_OAUTH_TOKEN пуст — разведка пропущена")
        return None

    timeout = timeout or settings.GLAFIRA_OSINT_TIMEOUT

    # Разрешённые инструменты вычитаем из запрещённых
    allowed_set = {t.strip() for t in allowed_tools.split(",") if t.strip()}
    disallowed = ",".join(t for t in _DISALLOWED_TOOLS.split(",") if t not in allowed_set)

    args = [
        settings.CLAUDE_CLI_PATH,
        "--print",
        "--output-format", "text",
        "--disallowed-tools", disallowed,
    ]
    if allowed_set:
        args.extend(["--allowed-tools", ",".join(sorted(allowed_set))])

    chosen_model = model or settings.GLAFIRA_OSINT_MODEL
    if chosen_model:
        args.extend(["--model", chosen_model])
    if system:
        args.extend(["--append-system-prompt", system])

    # env с токеном; CLAUDECODE убираем, чтобы CLI не считал себя вложенным
    import os
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env["CLAUDE_CODE_OAUTH_TOKEN"] = settings.CLAUDE_CODE_OAUTH_TOKEN

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
