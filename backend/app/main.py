import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.v1.router import api_router
from .config import settings
from .core.errors import AppError, app_error_handler, validation_error_handler, http_exception_handler, generic_exception_handler
from .services.smart_search import sweep_orphaned_runs
from .services.base_search import sweep_orphaned_base_search_runs
from .services.embeddings import warmup_embedding_model
from .services.call_sync import sweep_orphaned_call_sync_jobs
from .services.auto_search import sweep_orphaned_auto_runs

# Фоновые задачи для защиты от GC
_bg_tasks: set = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await sweep_orphaned_runs()
    await sweep_orphaned_base_search_runs()
    await sweep_orphaned_call_sync_jobs()
    await sweep_orphaned_auto_runs()

    # Прогрев эмбеддинг-модели в фоне (НЕ блокируя старт)
    _warmup_task = asyncio.create_task(warmup_embedding_model())
    _bg_tasks.add(_warmup_task)
    _warmup_task.add_done_callback(_bg_tasks.discard)

    yield
    # Shutdown - можно добавить cleanup если понадобится


app = FastAPI(title="Глафира Рекрутёр ATS", version="1.0.0", redirect_slashes=False, lifespan=lifespan)

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