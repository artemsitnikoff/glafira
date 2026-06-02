from fastapi import APIRouter, Depends, Query

from ...deps import get_current_user
from ...models import User
from ...services.dadata import suggest_cities

router = APIRouter()


@router.get("/cities")
async def get_city_suggestions(
    query: str = Query("", max_length=100),
    current_user: User = Depends(get_current_user),
):
    """Онлайн-подсказки городов (DaData) для автокомплита в форме вакансии."""
    return await suggest_cities(query)
