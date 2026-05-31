from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.v1.router import api_router
from .config import settings
from .core.errors import AppError, app_error_handler, validation_error_handler, http_exception_handler, generic_exception_handler

app = FastAPI(title="Глафира Рекрутёр ATS", version="1.0.0", redirect_slashes=False)

# CORS для фронтенда (origins из env CORS_ORIGINS, comma-separated)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers - order matters: specific first, general last
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "Глафира Рекрутёр ATS API v1"}