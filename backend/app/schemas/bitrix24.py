from pydantic import BaseModel
from typing import Literal


class BitrixDepartment(BaseModel):
    id: str
    name: str
    parent: str | None


class BitrixImportCandidate(BaseModel):
    b24_id: str
    name: str
    last_name: str
    position: str | None
    email: str | None
    department_ids: list[str]
    department_name: str | None
    active: bool


class BitrixImportRequest(BaseModel):
    b24_user_ids: list[str]
    role: str
    delivery: Literal["email"] = "email"


class BitrixImportResult(BaseModel):
    created: list[dict]
    emailed: list[str]
    shown: list[dict]
    skipped: list[dict]