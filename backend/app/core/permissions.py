"""Permission utilities"""

from fastapi import Depends
from ..models import User
from ..deps import get_current_user
from ..core.errors import ForbiddenError


async def require_admin(current_user: User = Depends(get_current_user)) -> None:
    """Require user to have admin role"""
    if current_user.role != "admin":
        raise ForbiddenError("Требуется роль администратора")