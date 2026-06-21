from cryptography.fernet import Fernet, InvalidToken
from ...config import settings
from ...core.errors import ValidationError

# Токены-подстроки для определения чувствительных ключей (регистронезависимо, по вхождению).
# Расширен по сравнению с исходным точным списком — ловит webhook/salt/bearer/auth и т.п.
_SENSITIVE_SUBSTRINGS = (
    "secret", "token", "key", "password", "salt", "webhook",
    "auth", "bearer", "private", "credential", "signature", "pwd",
)


def _is_sensitive_key(k: str) -> bool:
    """Ключ считается секретным, если его lower() содержит хотя бы одну из чувствительных подстрок."""
    lower = k.lower()
    return any(sub in lower for sub in _SENSITIVE_SUBSTRINGS)


def _get_fernet() -> Fernet:
    if not settings.FERNET_KEY:
        raise ValidationError("FERNET_KEY not configured — set FERNET_KEY in env to encrypt integration secrets")
    try:
        return Fernet(settings.FERNET_KEY.encode())
    except Exception as e:
        raise ValidationError(f"FERNET_KEY invalid: {e}")


def encrypt_text(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_text(token: str) -> str:
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValidationError("Cannot decrypt — wrong FERNET_KEY or corrupted data")


def encrypt_config(config: dict) -> dict:
    return {k: (encrypt_text(str(v)) if _is_sensitive_key(k) and v is not None else v) for k, v in config.items()}


# Ключи, безопасные к показу в GET-ответах (несекретные/непарольные/не-PII display-поля).
# Всё, чего здесь НЕТ, маскируется в "••••" (включая session/tg_user/phone/пароли/токены).
_SAFE_DISPLAY_KEYS = frozenset({
    "vpbx_api_url", "client_id", "employer_id", "employer_name",
    "host", "port", "from_email", "from_name", "use_tls", "use_ssl",
    "enabled", "state", "last_test_at", "last_test_status",
    "last_sync_at", "last_error",
})


def mask_config(config: dict) -> dict:
    """For GET responses: только whitelist-ключи отдаются как есть; всё остальное → "••••"
    (индикатор наличия). Секреты/сессии/PII НИКОГДА не расшифровываются и не раскрываются."""
    result = {}
    for k, v in config.items():
        if v is None:
            result[k] = None
        elif k in _SAFE_DISPLAY_KEYS:
            result[k] = v
        else:
            result[k] = "••••"
    return result