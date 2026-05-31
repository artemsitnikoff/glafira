"""Tests for LocalStorageService (асинхронный дисковый I/O через asyncio.to_thread)"""
import uuid
from pathlib import Path

from app.services.storage import LocalStorageService


async def test_local_storage_save_and_delete(tmp_path: Path):
    """save пишет файл и возвращает относительный путь; delete удаляет; повторный delete — no-op."""
    svc = LocalStorageService(tmp_path)
    company_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    content = b"hello world content"

    rel = await svc.save(
        content,
        company_id=company_id,
        candidate_id=candidate_id,
        filename="cv.pdf",
    )

    full = svc.get_path(rel)
    assert full.exists()
    assert full.read_bytes() == content
    # путь скоупится по company/candidate и сохраняет имя файла
    assert str(company_id) in rel
    assert str(candidate_id) in rel
    assert rel.endswith("cv.pdf")

    await svc.delete(rel)
    assert not full.exists()

    # delete несуществующего пути — без ошибки (no-op)
    await svc.delete(rel)
