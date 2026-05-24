from fastapi import APIRouter

from .auth import router as auth_router
from .users import router as users_router
from .vacancies import router as vacancies_router
from .applications import router as applications_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(vacancies_router, prefix="/vacancies", tags=["vacancies"])
api_router.include_router(applications_router, tags=["applications"])