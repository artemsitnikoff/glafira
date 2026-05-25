from cryptography.fernet import Fernet, InvalidToken
from ...config import settings
from ...core.errors import ValidationError

SENSITIVE_KEYS = ("api_key", "secret", "token", "password", "client_secret", "access_token", "refresh_token")


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
    return {k: (encrypt_text(str(v)) if k in SENSITIVE_KEYS and v is not None else v) for k, v in config.items()}


def decrypt_config(config: dict) -> dict:
    return {k: (decrypt_text(v) if k in SENSITIVE_KEYS and v is not None else v) for k, v in config.items()}


def mask_config(config: dict) -> dict:
    """For GET responses: shows ••••LAST4 for sensitive keys."""
    result = {}
    for k, v in config.items():
        if k in SENSITIVE_KEYS and v is not None:
            try:
                decrypted = decrypt_text(v)
                if len(decrypted) >= 8:
                    # Show last 4 chars for long strings
                    result[k] = f"••••{decrypted[-4:]}"
                elif len(decrypted) >= 4:
                    # Show last 2 chars for medium strings
                    result[k] = f"••••{decrypted[-2:]}"
                else:
                    # Show full string for very short strings
                    result[k] = f"••••{decrypted}"
            except Exception:
                result[k] = "••••"
        else:
            result[k] = v
    return result