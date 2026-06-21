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


def mask_config(config: dict) -> dict:
    """For GET responses: shows ••••LAST4 for sensitive keys (only when len>=8; shorter → ••••)."""
    result = {}
    for k, v in config.items():
        if _is_sensitive_key(k) and v is not None:
            try:
                decrypted = decrypt_text(v)
                if len(decrypted) >= 8:
                    # Показываем последние 4 символа только для длинных секретов
                    result[k] = f"••••{decrypted[-4:]}"
                else:
                    # Короткие (< 8) — никогда не раскрываем символы
                    result[k] = "••••"
            except Exception:
                result[k] = "••••"
        else:
            result[k] = v
    return result