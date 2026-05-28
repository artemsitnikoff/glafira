"""
Одноразовый cleanup-скрипт для удаления старых ручных тестовых данных.
Удаляет только старые вакансии "Senior Backend Engineer (Python/FastAPI)" и связанные данные.
НЕ ТРОГАЕТ demo-данные (extra.demo=true) и базовые seed-данные.

Использование:
    python -m app.cleanup_old_test_data                   # PREVIEW (безопасно)
    python -m app.cleanup_old_test_data --confirm-delete  # реальное удаление
"""

import asyncio
import logging
import sys
import uuid
from typing import List, Set, Dict, Any
from sqlalchemy import select, delete, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import (
    Company, User, Vacancy, VacancyStage, Candidate, Application, StageHistory,
    Message, Document, Consent, AiEvaluation, Event
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

COMPANY_ID = uuid.UUID(settings.DEFAULT_COMPANY_ID)

# Защищенные demo-имена вакансий (из seed_demo.py и актуальных данных БД)
DEMO_VACANCY_NAMES = [
    "Senior Frontend-разработчик",
    "Senior Frontend Developer",
    "Менеджер по продажам B2B",
    "Кладовщик-комплектовщик",
    "Кладовщик",
    "Senior Python Dev",
    "QA Engineer"
]

class CleanupResult:
    """Результаты сканирования для удаления"""
    def __init__(self):
        self.target_vacancies: List[Dict[str, Any]] = []
        self.target_applications: List[Dict[str, Any]] = []
        self.candidates_full_delete: List[Dict[str, Any]] = []
        self.candidates_partial: List[Dict[str, Any]] = []

        # Связанные записи
        self.stage_history_count = 0
        self.messages_count = 0
        self.documents_count = 0
        self.consents_count = 0
        self.ai_evaluations_count = 0
        self.events_count = 0


async def find_cleanup_targets(db: AsyncSession) -> CleanupResult:
    """Найти все данные для удаления"""
    result = CleanupResult()

    # Шаг A: Найти старые тестовые вакансии
    logger.info("🔍 Поиск старых тестовых вакансий...")

    query = select(Vacancy).where(
        and_(
            Vacancy.company_id == COMPANY_ID,
            Vacancy.name.ilike('%Senior Backend Engineer%')
        )
    )
    vacancies = await db.execute(query)
    target_vacancies = vacancies.scalars().all()

    if not target_vacancies:
        logger.info("✅ Нет старых тестовых вакансий для удаления")
        return result

    # Проверка защиты: убедиться что не затронуты demo-вакансии
    for vacancy in target_vacancies:
        if any(demo_name in vacancy.name for demo_name in DEMO_VACANCY_NAMES):
            logger.error(f"❌ ОПАСНОСТЬ: Найдена demo-вакансия в выборке: {vacancy.name}")
            logger.error("❌ Остановка скрипта для предотвращения повреждения demo-данных")
            sys.exit(1)

    result.target_vacancies = [
        {"id": v.id, "name": v.name, "created_at": v.created_at}
        for v in target_vacancies
    ]

    target_vacancy_ids = [v.id for v in target_vacancies]
    logger.info(f"📌 Найдено {len(target_vacancies)} вакансий для удаления:")
    for v in target_vacancies:
        logger.info(f"   • {v.name} (id: {v.id})")

    # Шаг B: Найти applications в этих вакансиях
    logger.info("🔍 Поиск applications в целевых вакансиях...")

    app_query = select(Application).where(
        Application.vacancy_id.in_(target_vacancy_ids)
    )
    applications = await db.execute(app_query)
    target_applications = applications.scalars().all()

    result.target_applications = [
        {
            "id": app.id,
            "candidate_id": app.candidate_id,
            "vacancy_id": app.vacancy_id,
            "stage": app.stage,
            "created_at": app.created_at
        }
        for app in target_applications
    ]

    logger.info(f"📌 Найдено {len(target_applications)} applications для удаления")

    if not target_applications:
        return result

    # Шаг C: Анализ кандидатов
    logger.info("🔍 Анализ кандидатов...")

    candidate_ids_in_target = set(app.candidate_id for app in target_applications)

    for candidate_id in candidate_ids_in_target:
        # Получить кандидата
        cand_query = select(Candidate).where(Candidate.id == candidate_id)
        cand_result = await db.execute(cand_query)
        candidate = cand_result.scalar_one_or_none()

        if not candidate:
            continue

        # Проверка на demo-кандидата
        is_demo = False
        if candidate.extra and isinstance(candidate.extra, dict):
            is_demo = candidate.extra.get('demo') == 'true'

        if is_demo:
            logger.info(f"🛡️  Demo-кандидат {candidate.full_name} - НЕ удаляем, только applications")
            result.candidates_partial.append({
                "id": candidate.id,
                "full_name": candidate.full_name,
                "reason": "demo_candidate"
            })
            continue

        # Проверить есть ли у кандидата applications вне целевых вакансий
        other_apps_query = select(Application).where(
            and_(
                Application.candidate_id == candidate_id,
                ~Application.vacancy_id.in_(target_vacancy_ids)
            )
        )
        other_apps = await db.execute(other_apps_query)
        other_applications = other_apps.scalars().all()

        if other_applications:
            logger.info(f"🔄 Кандидат {candidate.full_name} участвует в других вакансиях - частичное удаление")
            result.candidates_partial.append({
                "id": candidate.id,
                "full_name": candidate.full_name,
                "reason": f"has_other_applications ({len(other_applications)})"
            })
        else:
            logger.info(f"🗑️  Кандидат {candidate.full_name} - полное удаление")
            result.candidates_full_delete.append({
                "id": candidate.id,
                "full_name": candidate.full_name,
                "email": candidate.email,
                "created_at": candidate.created_at
            })

    # Подсчёт связанных записей
    await count_related_records(db, result)

    return result


async def count_related_records(db: AsyncSession, result: CleanupResult) -> None:
    """Подсчитать связанные записи для удаления"""

    target_app_ids = [app["id"] for app in result.target_applications]
    candidates_full_delete_ids = [c["id"] for c in result.candidates_full_delete]
    target_vacancy_ids = [v["id"] for v in result.target_vacancies]

    # StageHistory (по application_id)
    if target_app_ids:
        sh_query = select(StageHistory).where(
            StageHistory.application_id.in_(target_app_ids)
        )
        sh_result = await db.execute(sh_query)
        result.stage_history_count = len(sh_result.scalars().all())

    # Messages (только для полностью удаляемых кандидатов)
    if candidates_full_delete_ids:
        msg_query = select(Message).where(
            Message.candidate_id.in_(candidates_full_delete_ids)
        )
        msg_result = await db.execute(msg_query)
        result.messages_count = len(msg_result.scalars().all())

    # Documents (только для полностью удаляемых кандидатов)
    if candidates_full_delete_ids:
        doc_query = select(Document).where(
            Document.candidate_id.in_(candidates_full_delete_ids)
        )
        doc_result = await db.execute(doc_query)
        result.documents_count = len(doc_result.scalars().all())

    # Consents (только для полностью удаляемых кандидатов)
    if candidates_full_delete_ids:
        consent_query = select(Consent).where(
            Consent.candidate_id.in_(candidates_full_delete_ids)
        )
        consent_result = await db.execute(consent_query)
        result.consents_count = len(consent_result.scalars().all())

    # AiEvaluations (по application_id или candidate_id)
    ai_eval_count = 0
    if target_app_ids:
        ai_eval_query_app = select(AiEvaluation).where(
            AiEvaluation.application_id.in_(target_app_ids)
        )
        ai_eval_result_app = await db.execute(ai_eval_query_app)
        ai_eval_count += len(ai_eval_result_app.scalars().all())

    if candidates_full_delete_ids:
        ai_eval_query_cand = select(AiEvaluation).where(
            AiEvaluation.candidate_id.in_(candidates_full_delete_ids)
        )
        ai_eval_result_cand = await db.execute(ai_eval_query_cand)
        ai_eval_count += len(ai_eval_result_cand.scalars().all())

    result.ai_evaluations_count = ai_eval_count

    # Events (по candidate_id и vacancy_id)
    events_count = 0
    if candidates_full_delete_ids:
        events_query_cand = select(Event).where(
            Event.candidate_id.in_(candidates_full_delete_ids)
        )
        events_result_cand = await db.execute(events_query_cand)
        events_count += len(events_result_cand.scalars().all())

    if target_vacancy_ids:
        events_query_vac = select(Event).where(
            Event.vacancy_id.in_(target_vacancy_ids)
        )
        events_result_vac = await db.execute(events_query_vac)
        events_count += len(events_result_vac.scalars().all())

    result.events_count = events_count


def print_preview_report(result: CleanupResult) -> None:
    """Вывести отчёт PREVIEW"""

    print("\n" + "="*80)
    print("🔍 PREVIEW ОТЧЁТ - ЧТО БУДЕТ УДАЛЕНО")
    print("="*80)

    if not result.target_vacancies:
        print("✅ Нет старых тестовых данных для удаления")
        return

    print(f"\n📋 ВАКАНСИИ ({len(result.target_vacancies)}):")
    for v in result.target_vacancies:
        print(f"   • {v['name']} (id: {v['id']}, created: {v['created_at']})")

    print(f"\n📝 APPLICATIONS ({len(result.target_applications)}):")
    stage_stats = {}
    for app in result.target_applications:
        stage = app['stage']
        stage_stats[stage] = stage_stats.get(stage, 0) + 1

    for stage, count in stage_stats.items():
        print(f"   • {stage}: {count}")

    print(f"\n👤 КАНДИДАТЫ:")
    print(f"   🗑️  Полное удаление: {len(result.candidates_full_delete)}")
    for c in result.candidates_full_delete:
        print(f"      • {c['full_name']} ({c['email']}) [id: {str(c['id'])[:8]}...]")

    print(f"   🔄 Частичное (остаются): {len(result.candidates_partial)}")
    for c in result.candidates_partial:
        print(f"      • {c['full_name']} - {c['reason']}")

    print(f"\n🔗 СВЯЗАННЫЕ ЗАПИСИ:")
    print(f"   • StageHistory: {result.stage_history_count}")
    print(f"   • Messages: {result.messages_count}")
    print(f"   • Documents: {result.documents_count}")
    print(f"   • Consents: {result.consents_count}")
    print(f"   • AiEvaluations: {result.ai_evaluations_count}")
    print(f"   • Events: {result.events_count}")

    total_records = (
        len(result.target_vacancies) +
        len(result.target_applications) +
        len(result.candidates_full_delete) +
        result.stage_history_count +
        result.messages_count +
        result.documents_count +
        result.consents_count +
        result.ai_evaluations_count +
        result.events_count
    )

    print(f"\n📊 ИТОГО ЗАПИСЕЙ К УДАЛЕНИЮ: {total_records}")
    print("\n" + "="*80)
    print("⚠️  Для реального удаления запустите с флагом --confirm-delete")
    print("="*80)


async def perform_deletion(db: AsyncSession, result: CleanupResult) -> None:
    """Выполнить реальное удаление в транзакции"""

    logger.info("🗑️  Начинаем удаление в транзакции...")

    target_app_ids = [app["id"] for app in result.target_applications]
    candidates_full_delete_ids = [c["id"] for c in result.candidates_full_delete]
    target_vacancy_ids = [v["id"] for v in result.target_vacancies]

    deleted_counts = {}

    try:
        # Порядок удаления: от зависимых к основным

        # 1. Messages (для полностью удаляемых кандидатов)
        if candidates_full_delete_ids:
            msg_delete = delete(Message).where(
                Message.candidate_id.in_(candidates_full_delete_ids)
            )
            msg_result = await db.execute(msg_delete)
            deleted_counts['messages'] = msg_result.rowcount
            logger.info(f"✅ Удалено Messages: {msg_result.rowcount}")

        # 2. Documents (для полностью удаляемых кандидатов)
        if candidates_full_delete_ids:
            doc_delete = delete(Document).where(
                Document.candidate_id.in_(candidates_full_delete_ids)
            )
            doc_result = await db.execute(doc_delete)
            deleted_counts['documents'] = doc_result.rowcount
            logger.info(f"✅ Удалено Documents: {doc_result.rowcount}")

        # 3. Consents (для полностью удаляемых кандидатов)
        if candidates_full_delete_ids:
            consent_delete = delete(Consent).where(
                Consent.candidate_id.in_(candidates_full_delete_ids)
            )
            consent_result = await db.execute(consent_delete)
            deleted_counts['consents'] = consent_result.rowcount
            logger.info(f"✅ Удалено Consents: {consent_result.rowcount}")

        # 4. AiEvaluations (по application_id и candidate_id)
        ai_eval_count = 0
        if target_app_ids:
            ai_eval_delete_app = delete(AiEvaluation).where(
                AiEvaluation.application_id.in_(target_app_ids)
            )
            ai_eval_result_app = await db.execute(ai_eval_delete_app)
            ai_eval_count += ai_eval_result_app.rowcount

        if candidates_full_delete_ids:
            ai_eval_delete_cand = delete(AiEvaluation).where(
                AiEvaluation.candidate_id.in_(candidates_full_delete_ids)
            )
            ai_eval_result_cand = await db.execute(ai_eval_delete_cand)
            ai_eval_count += ai_eval_result_cand.rowcount

        deleted_counts['ai_evaluations'] = ai_eval_count
        logger.info(f"✅ Удалено AiEvaluations: {ai_eval_count}")

        # 5. Events (по candidate_id и vacancy_id)
        events_count = 0
        if candidates_full_delete_ids:
            events_delete_cand = delete(Event).where(
                Event.candidate_id.in_(candidates_full_delete_ids)
            )
            events_result_cand = await db.execute(events_delete_cand)
            events_count += events_result_cand.rowcount

        if target_vacancy_ids:
            events_delete_vac = delete(Event).where(
                Event.vacancy_id.in_(target_vacancy_ids)
            )
            events_result_vac = await db.execute(events_delete_vac)
            events_count += events_result_vac.rowcount

        deleted_counts['events'] = events_count
        logger.info(f"✅ Удалено Events: {events_count}")

        # 6. StageHistory (по application_id)
        if target_app_ids:
            sh_delete = delete(StageHistory).where(
                StageHistory.application_id.in_(target_app_ids)
            )
            sh_result = await db.execute(sh_delete)
            deleted_counts['stage_history'] = sh_result.rowcount
            logger.info(f"✅ Удалено StageHistory: {sh_result.rowcount}")

        # 7. Applications (целевые)
        if target_app_ids:
            app_delete = delete(Application).where(
                Application.id.in_(target_app_ids)
            )
            app_result = await db.execute(app_delete)
            deleted_counts['applications'] = app_result.rowcount
            logger.info(f"✅ Удалено Applications: {app_result.rowcount}")

        # 8. VacancyStages (для целевых вакансий)
        if target_vacancy_ids:
            vs_delete = delete(VacancyStage).where(
                VacancyStage.vacancy_id.in_(target_vacancy_ids)
            )
            vs_result = await db.execute(vs_delete)
            deleted_counts['vacancy_stages'] = vs_result.rowcount
            logger.info(f"✅ Удалено VacancyStages: {vs_result.rowcount}")

        # 9. Vacancies (целевые)
        if target_vacancy_ids:
            vac_delete = delete(Vacancy).where(
                Vacancy.id.in_(target_vacancy_ids)
            )
            vac_result = await db.execute(vac_delete)
            deleted_counts['vacancies'] = vac_result.rowcount
            logger.info(f"✅ Удалено Vacancies: {vac_result.rowcount}")

        # 10. Candidates (только полностью удаляемые)
        if candidates_full_delete_ids:
            cand_delete = delete(Candidate).where(
                Candidate.id.in_(candidates_full_delete_ids)
            )
            cand_result = await db.execute(cand_delete)
            deleted_counts['candidates'] = cand_result.rowcount
            logger.info(f"✅ Удалено Candidates: {cand_result.rowcount}")

        # Коммит транзакции
        await db.commit()
        logger.info("🎉 Транзакция успешно завершена")

        return deleted_counts

    except Exception as e:
        logger.error(f"❌ Ошибка при удалении: {e}")
        await db.rollback()
        logger.info("🔄 Транзакция отменена (rollback)")
        raise


async def verify_cleanup(db: AsyncSession) -> None:
    """Само-проверка после удаления"""

    logger.info("🔍 Финальная проверка...")

    # 1. Не должно остаться старых Backend вакансий
    backend_query = select(Vacancy).where(
        Vacancy.name.ilike('%Senior Backend%')
    )
    backend_result = await db.execute(backend_query)
    backend_count = len(backend_result.scalars().all())

    # 2. Demo-кандидаты должны остаться
    demo_query = select(Candidate).where(
        text("extra->>'demo' = 'true'")
    )
    demo_result = await db.execute(demo_query)
    demo_count = len(demo_result.scalars().all())

    # 3. Admin должен остаться
    admin_query = select(User).where(
        User.email == 'admin@dclouds.ru'
    )
    admin_result = await db.execute(admin_query)
    admin_count = len(admin_result.scalars().all())

    print(f"\n🔍 ФИНАЛЬНАЯ ПРОВЕРКА:")
    print(f"   • Backend вакансии: {backend_count} (должно быть 0)")
    print(f"   • Demo кандидаты: {demo_count} (должно быть ~20)")
    print(f"   • Admin пользователи: {admin_count} (должно быть 1)")

    if backend_count == 0:
        print("   ✅ Backend вакансии успешно удалены")
    else:
        print("   ❌ Остались Backend вакансии!")

    if demo_count > 0:
        print("   ✅ Demo кандидаты сохранены")
    else:
        print("   ⚠️  Demo кандидаты не найдены")

    if admin_count == 1:
        print("   ✅ Admin пользователь сохранён")
    else:
        print("   ❌ Проблема с admin пользователем!")


async def main():
    """Главная функция"""

    # Проверка CLI аргументов
    confirm_delete = '--confirm-delete' in sys.argv

    if confirm_delete:
        logger.info("🔥 РЕЖИМ РЕАЛЬНОГО УДАЛЕНИЯ")
    else:
        logger.info("🔍 РЕЖИМ PREVIEW (безопасный)")

    async with AsyncSessionLocal() as db:
        # Фаза 1: Разведка
        result = await find_cleanup_targets(db)

        if not result.target_vacancies:
            logger.info("✅ Нет данных для удаления. Завершение.")
            return

        # Вывод отчёта
        print_preview_report(result)

        if not confirm_delete:
            logger.info("ℹ️  PREVIEW завершён. Для удаления используйте --confirm-delete")
            return

        # Фаза 2: Реальное удаление
        print(f"\n⚠️  Это удалит {len(result.target_vacancies)} вакансий, "
              f"{len(result.target_applications)} applications, "
              f"{len(result.candidates_full_delete)} кандидатов.")

        confirmation = input("Продолжить? (yes/no): ").strip().lower()
        if confirmation != 'yes':
            logger.info("❌ Удаление отменено пользователем")
            return

        # Выполнить удаление
        deleted_counts = await perform_deletion(db, result)

        # Итоги
        print(f"\n🎉 УДАЛЕНИЕ ЗАВЕРШЕНО:")
        for entity, count in deleted_counts.items():
            print(f"   • {entity}: {count}")

        # Финальная проверка
        await verify_cleanup(db)


if __name__ == "__main__":
    asyncio.run(main())