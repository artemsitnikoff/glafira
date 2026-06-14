import os
import re
from pathlib import Path
from typing import Optional, Union
from uuid import UUID

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError as PydanticValidationError

from app.provision_company import ProvisionError
from app.core.errors import ValidationError
from app.services.glafira.models import ALLOWED_MODEL_VALUES

from .auth import (
    require_super_admin,
    auth_service,
    LoginRequest,
)
from .service import company_service
from .test_results import parse_test_results
from .config import config

app = FastAPI(title="Glafira Superadmin", version="1.0.0")

templates = Jinja2Templates(directory="superadmin/templates")


def _read_app_version() -> str:
    """Версия Глафиры из примонтированного frontend/src/lib/version.ts — единый
    источник правды. Читается на каждый рендер → актуальна после git pull, без
    пересборки суперадминки. Файла нет/не распарсился → «—» (не падаем)."""
    path = os.getenv("APP_VERSION_FILE", "/app/app_version.ts")
    try:
        text = Path(path).read_text(encoding="utf-8")
        m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "—"


# Доступно во всех шаблонах как {{ app_version() }}
templates.env.globals["app_version"] = _read_app_version


# Error handlers
@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    if request.url.path.startswith("/super/companies/"):
        # Form error - redirect with error message
        if "new" in request.url.path:
            return RedirectResponse(f"/super/companies/new?error={exc.message}", status_code=303)
        return RedirectResponse(f"/super/?error={exc.message}", status_code=303)
    raise HTTPException(status_code=400, detail=exc.message)


# Auth routes
@app.get("/super/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(request, "login.html", {
        "request": request,
        "error": error
    })


@app.post("/super/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if auth_service.verify_credentials(username, password):
        token = auth_service.create_token()
        return auth_service.create_cookie_response(token)
    else:
        return templates.TemplateResponse(request, "login.html", {
            "request": request,
            "error": "invalid_credentials",
            "username": username
        })


@app.post("/super/logout")
async def logout():
    return auth_service.clear_cookie_response()


# Dashboard
@app.get("/super/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    username: str = Depends(require_super_admin),
    error: Optional[str] = None
):
    # Handle redirects from require_super_admin
    if isinstance(username, RedirectResponse):
        return username

    companies = await company_service.list_companies()
    test_results = parse_test_results(config.TEST_RESULTS_PATH)

    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "username": username,
        "companies": companies,
        "test_results": test_results,
        "test_results_path": config.TEST_RESULTS_PATH,
        "error": error
    })


# Company management
@app.get("/super/companies/new", response_class=HTMLResponse)
async def new_company_page(
    request: Request,
    username: str = Depends(require_super_admin),
    error: Optional[str] = None,
    success: Optional[str] = None
):
    if isinstance(username, RedirectResponse):
        return username

    return templates.TemplateResponse(request, "company_form.html", {
        "request": request,
        "username": username,
        "company": None,
        "form_data": {},
        "error": error,
        "success": success
    })


@app.post("/super/companies/new")
async def create_company(
    request: Request,
    username: str = Depends(require_super_admin),
    name: str = Form(...),
    admin_email: str = Form(...),
    admin_full_name: str = Form(...),
    admin_password: str = Form(...),
    openrouter_api_key: Optional[str] = Form("")
):
    if isinstance(username, RedirectResponse):
        return username

    try:
        # Basic validation
        if not name.strip():
            raise ValidationError("Название компании не может быть пустым")
        if not admin_email.strip() or "@" not in admin_email:
            raise ValidationError("Некорректный email администратора")
        if not admin_full_name.strip():
            raise ValidationError("ФИО администратора не может быть пустым")
        if not admin_password.strip():
            raise ValidationError("Пароль не может быть пустым")

        # Validate OpenRouter key if provided
        if openrouter_api_key and openrouter_api_key.strip():
            key = openrouter_api_key.strip()
            if len(key) < 10:  # Basic length check
                raise ValidationError("API-ключ слишком короткий")
            # Gentle warning for non-standard format (don't enforce)
            if not key.startswith(('sk-or-v1-', 'sk-')):
                # Just log but don't fail
                pass

        await company_service.create_company(
            name=name.strip(),
            admin_email=admin_email.strip(),
            admin_password=admin_password.strip(),
            admin_full_name=admin_full_name.strip(),
            openrouter_api_key=openrouter_api_key.strip() if openrouter_api_key else None
        )

        return RedirectResponse(
            f"/super/companies/new?success=Компания «{name}» создана успешно",
            status_code=303
        )

    except ProvisionError as e:
        # Handle duplicate email etc
        if "already exists" in str(e) or "duplicate" in str(e).lower():
            error_msg = f"Пользователь с email {admin_email} уже существует"
        else:
            error_msg = f"Ошибка создания: {str(e)}"

        return templates.TemplateResponse(request, "company_form.html", {
            "request": request,
            "username": username,
            "company": None,
            "form_data": {
                "name": name,
                "admin_email": admin_email,
                "admin_full_name": admin_full_name,
                "openrouter_api_key": openrouter_api_key
            },
            "error": error_msg
        })
    except Exception as e:
        return templates.TemplateResponse(request, "company_form.html", {
            "request": request,
            "username": username,
            "company": None,
            "form_data": {
                "name": name,
                "admin_email": admin_email,
                "admin_full_name": admin_full_name,
                "openrouter_api_key": openrouter_api_key
            },
            "error": f"Неожиданная ошибка: {str(e)}"
        })


@app.get("/super/companies/{company_id}/edit", response_class=HTMLResponse)
async def edit_company_page(
    request: Request,
    company_id: UUID,
    username: str = Depends(require_super_admin),
    error: Optional[str] = None,
    success: Optional[str] = None
):
    if isinstance(username, RedirectResponse):
        return username

    company_settings = await company_service.get_company_settings(company_id)
    if not company_settings:
        return RedirectResponse("/super/?error=Компания не найдена", status_code=303)

    return templates.TemplateResponse(request, "company_form.html", {
        "request": request,
        "username": username,
        "company": company_settings,
        "form_data": {},
        "error": error,
        "success": success
    })


@app.post("/super/companies/{company_id}")
async def update_company(
    request: Request,
    company_id: UUID,
    username: str = Depends(require_super_admin),
    name: str = Form(...),
    openrouter_api_key: Optional[str] = Form(""),
    llm_model: Optional[str] = Form("")
):
    if isinstance(username, RedirectResponse):
        return username

    try:
        # Basic validation
        if not name.strip():
            raise ValidationError("Название компании не может быть пустым")

        # Validate LLM model if provided
        if llm_model and llm_model.strip():
            if ALLOWED_MODEL_VALUES and llm_model.strip() not in ALLOWED_MODEL_VALUES:
                raise ValidationError(f"Недопустимая LLM-модель: {llm_model}")

        # Prepare update data
        update_data = {"name": name.strip()}

        # Only update key if field is not empty (empty = keep current)
        if openrouter_api_key and openrouter_api_key.strip():
            key = openrouter_api_key.strip()
            if len(key) < 10:
                raise ValidationError("API-ключ слишком короткий")
            update_data["openrouter_api_key"] = key

        # Update model (can be empty to clear)
        update_data["llm_model"] = llm_model.strip() if llm_model else None

        success = await company_service.update_company(company_id, **update_data)
        if not success:
            raise ValidationError("Компания не найдена")

        return RedirectResponse(
            f"/super/companies/{company_id}/edit?success=Компания обновлена",
            status_code=303
        )

    except Exception as e:
        # Get company settings again for form
        company_settings = await company_service.get_company_settings(company_id)
        return templates.TemplateResponse(request, "company_form.html", {
            "request": request,
            "username": username,
            "company": company_settings,
            "form_data": {
                "name": name,
                "openrouter_api_key": openrouter_api_key,
                "llm_model": llm_model
            },
            "error": str(e)
        })