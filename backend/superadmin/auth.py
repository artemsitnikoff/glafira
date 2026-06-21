from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt
from jose.exceptions import JWTError
from fastapi import HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.security import verify_password
from .config import config

# In-memory lockout для суперадминки.
# ⚠️ Ограничение: при 2+ воркерах счётчик не шарится между процессами.
# Суперадминка используется редко (администратор сервиса) и обычно 1 воркер,
# поэтому in-memory достаточно как базовая защита.
_MAX_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15
# Структура: {username: {"fails": int, "locked_until": datetime | None}}
_lockout_state: dict[str, dict] = {}


def _check_and_record_lockout(username: str, success: bool) -> None:
    """
    Регистрирует результат попытки входа.
    При success=True — сбрасывает счётчик.
    Raise HTTPException 429 если аккаунт залочен (вызывается ДО verify_credentials).
    """
    state = _lockout_state.setdefault(username, {"fails": 0, "locked_until": None})
    now = datetime.now(timezone.utc)

    if state["locked_until"] is not None:
        if state["locked_until"] > now:
            remaining = state["locked_until"] - now
            minutes_left = max(1, int(remaining.total_seconds() // 60) + 1)
            raise HTTPException(
                status_code=429,
                detail=f"Слишком много неудачных попыток. Повторите через {minutes_left} мин."
            )
        else:
            # Окно истекло — сбрасываем
            state["fails"] = 0
            state["locked_until"] = None

    if success:
        state["fails"] = 0
        state["locked_until"] = None
    else:
        state["fails"] += 1
        if state["fails"] >= _MAX_ATTEMPTS:
            state["locked_until"] = now + timedelta(minutes=_LOCKOUT_MINUTES)


class LoginRequest(BaseModel):
    username: str
    password: str


class SuperAdminAuth:
    """Authentication for superadmin service"""

    COOKIE_NAME = "super_session"
    ALGORITHM = "HS256"
    TOKEN_EXPIRE_HOURS = 12

    def verify_credentials(self, username: str, password: str) -> bool:
        """Verify superadmin credentials with in-memory lockout.

        Сначала проверяет lockout (кидает 429 если залочен), затем проверяет
        учётные данные и обновляет счётчик.
        """
        # Проверяем lockout ДО проверки пароля (fail-fast)
        # Флаг success выставим после реальной проверки
        _check_and_record_lockout(username, success=False)

        if not config.is_configured:
            # Не можем проверить — засчитываем как неудачу (уже записана выше)
            return False

        if username != config.SUPERADMIN_USER:
            # Неверный username — неудача уже записана
            return False

        # Кривой (не-bcrypt) SUPERADMIN_PASSWORD_HASH не должен валить 500 — это «неверно».
        try:
            ok = verify_password(password, config.SUPERADMIN_PASSWORD_HASH)
        except Exception:
            ok = False

        if ok:
            # Пароль верный — сбрасываем счётчик
            _check_and_record_lockout(username, success=True)

        return ok

    def create_token(self) -> str:
        """Create JWT token for authenticated session"""
        if not config.SUPERADMIN_JWT_SECRET:
            raise HTTPException(status_code=500, detail="JWT secret not configured")

        now = datetime.now(timezone.utc)
        expire = now + timedelta(hours=self.TOKEN_EXPIRE_HOURS)
        # int-таймстампы (не datetime) — единообразно для jose, без зависимости от авто-конверсии
        payload = {
            "sub": config.SUPERADMIN_USER,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
        }

        return jwt.encode(payload, config.SUPERADMIN_JWT_SECRET, algorithm=self.ALGORITHM)

    def verify_token(self, token: str) -> Optional[str]:
        """Verify JWT token and return username if valid"""
        if not config.SUPERADMIN_JWT_SECRET:
            return None

        try:
            payload = jwt.decode(
                token,
                config.SUPERADMIN_JWT_SECRET,
                algorithms=[self.ALGORITHM]
            )
            username = payload.get("sub")
            return username if username == config.SUPERADMIN_USER else None
        except JWTError:
            return None

    def get_token_from_cookie(self, request: Request) -> Optional[str]:
        """Extract token from HTTP cookie"""
        return request.cookies.get(self.COOKIE_NAME)

    def create_cookie_response(self, token: str, response_class=RedirectResponse):
        """Create response with authentication cookie"""
        response = response_class("/super/", status_code=303)
        response.set_cookie(
            key=self.COOKIE_NAME,
            value=token,
            httponly=True,
            secure=True,  # HTTPS only
            samesite="lax",
            path="/super",
            max_age=self.TOKEN_EXPIRE_HOURS * 3600
        )
        return response

    def clear_cookie_response(self, response_class=RedirectResponse):
        """Create response that clears authentication cookie"""
        response = response_class("/super/login", status_code=303)
        response.delete_cookie(key=self.COOKIE_NAME, path="/super")
        return response


auth_service = SuperAdminAuth()


def require_super_admin(request: Request) -> str:
    """Dependency to require superadmin authentication.

    For HTML pages: redirects to login on failure
    For POST/API: returns 401 on failure
    """
    if not config.is_configured:
        if request.method == "GET":
            return RedirectResponse("/super/login?error=not_configured", status_code=303)
        raise HTTPException(status_code=401, detail="Superadmin not configured")

    token = auth_service.get_token_from_cookie(request)
    if not token:
        if request.method == "GET":
            return RedirectResponse("/super/login", status_code=303)
        raise HTTPException(status_code=401, detail="Not authenticated")

    username = auth_service.verify_token(token)
    if not username:
        if request.method == "GET":
            return RedirectResponse("/super/login?error=invalid_session", status_code=303)
        raise HTTPException(status_code=401, detail="Invalid session")

    return username