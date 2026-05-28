"""Команда массовой регенерации AI-сводок сотрудников"""

import asyncio
import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import selectinload

import sys
import os

# Добавляем корень проекта в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.database import AsyncSessionLocal
from app.models.pulse import Employee
from app.services.glafira.employee_summary import generate_employee_summary


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def regenerate_all_summaries():
    """Регенерирует AI-сводки для всех сотрудников в статусе 'onboarding'"""

    async with AsyncSessionLocal() as session:
        try:
            # Получаем всех сотрудников в статусе onboarding с предзагрузкой surveys
            query = (
                select(Employee)
                .options(selectinload(Employee.surveys))
                .where(Employee.status == 'onboarding')
            )
            result = await session.execute(query)
            employees = result.scalars().all()

            logger.info(f"Found {len(employees)} employees in onboarding status")

            processed = 0
            skipped = 0
            failed = 0

            for employee in employees:
                try:
                    # Проверяем guard на уровне сервиса для быстрого skip
                    answered_surveys = [s for s in employee.surveys if s.answered_at is not None]
                    if len(answered_surveys) == 0:
                        logger.debug(f"Skipping {employee.full_name} (no answered surveys)")
                        skipped += 1
                        continue

                    result = await generate_employee_summary(
                        session=session,
                        employee_id=employee.id,
                        company_id=employee.company_id,
                        actor_user_id=None  # AI actor
                    )

                    if result is not None:
                        processed += 1
                        logger.info(f"Generated summary for {employee.full_name}")
                    else:
                        skipped += 1
                        logger.debug(f"Skipped {employee.full_name} (insufficient data)")

                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to generate summary for {employee.full_name}: {e}")

            # Commit all changes at once
            await session.commit()

            logger.info(f"Summary generation completed: processed={processed}, skipped={skipped}, failed={failed}")
            print(f"Summary generation completed: processed={processed}, skipped={skipped}, failed={failed}")

        except Exception as e:
            logger.error(f"Critical error during summary regeneration: {e}")
            await session.rollback()
            raise


async def main():
    """Точка входа для команды"""
    await regenerate_all_summaries()


if __name__ == '__main__':
    asyncio.run(main())