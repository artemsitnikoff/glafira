from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class InvalidCredentialsError(AppError):
    def __init__(self):
        super().__init__(
            code="INVALID_CREDENTIALS",
            message="Неверный email или пароль",
            status_code=401
        )


class UserInactiveError(AppError):
    def __init__(self):
        super().__init__(
            code="USER_INACTIVE",
            message="Пользователь заблокирован",
            status_code=403
        )


class NotFoundError(AppError):
    def __init__(self, entity: str = "Объект"):
        super().__init__(
            code="NOT_FOUND",
            message=f"{entity} не найден",
            status_code=404
        )


class ForbiddenError(AppError):
    def __init__(self, message: str = "Недостаточно прав"):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403
        )


class ValidationError(AppError):
    def __init__(self, message: str = "Ошибка валидации", details: dict | None = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=400,
            details=details
        )


class ConflictError(AppError):
    def __init__(self, message: str = "Конфликт данных"):
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=409
        )


class ConsentRequiredError(AppError):
    def __init__(self):
        super().__init__(
            code="CONSENT_REQUIRED",
            message="Требуется согласие на обработку персональных данных",
            status_code=403
        )


class InvalidMentionError(AppError):
    def __init__(self, details: list[dict] | None = None):
        super().__init__(
            code="INVALID_MENTION",
            message="Некорректное упоминание",
            status_code=422,
            details=details
        )


class AlreadySignedError(AppError):
    def __init__(self):
        super().__init__(
            code="ALREADY_SIGNED",
            message="Согласие уже подписано",
            status_code=409
        )


class FileTooLargeError(AppError):
    def __init__(self):
        super().__init__(
            code="FILE_TOO_LARGE",
            message="Файл превышает допустимый размер",
            status_code=413
        )


class UnsupportedFileTypeError(AppError):
    def __init__(self):
        super().__init__(
            code="UNSUPPORTED_FILE_TYPE",
            message="Неподдерживаемый тип файла",
            status_code=415
        )


class GlafiraParseError(AppError):
    def __init__(self, details: dict | None = None):
        super().__init__(
            code="GLAFIRA_PARSE_ERROR",
            message="Ошибка парсинга ответа от Глафиры",
            status_code=502,
            details=details
        )


class FeatureNotImplementedError(AppError):
    def __init__(self, details: dict | None = None):
        super().__init__(
            code="FEATURE_NOT_IMPLEMENTED",
            message="Функция не реализована",
            status_code=501,
            details=details
        )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for error in exc.errors():
        field = ".".join(str(x) for x in error["loc"]) if error["loc"] else "root"
        details.append({
            "field": field,
            "message": error["msg"]
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Ошибка валидации данных",
                "details": details
            }
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException | StarletteHTTPException) -> JSONResponse:
    """Convert FastAPI/Starlette HTTPException to unified error format"""
    # Map HTTP status codes to error codes
    code_mapping = {
        401: "NOT_AUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR"
    }

    error_code = code_mapping.get(exc.status_code, "HTTP_ERROR")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": error_code,
                "message": str(exc.detail),
                "details": None
            }
        }
    )