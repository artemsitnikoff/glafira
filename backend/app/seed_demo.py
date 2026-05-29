import asyncio
import logging
import os
import uuid
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import (
    Company, User, Client, Vacancy, VacancyStage, Candidate,
    Application, StageHistory, Consent, Message, Document,
    AiEvaluation, Employee, PulsePlanItem, PulseSurvey,
    CandidateExperience, CandidateSkill
)
from app.schemas.application import MoveRequest
from app.services.application import move_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

COMPANY_ID = uuid.UUID(settings.DEFAULT_COMPANY_ID)
ADMIN_EMAIL = "admin@dclouds.ru"

def generate_resume_text(candidate_index: int, vacancy_idx: int) -> str:
    """Генерирует реалистичное резюме для кандидата под конкретную вакансию"""

    # Шаблоны резюме по типам вакансий
    templates = {
        0: [  # Frontend
            "Frontend-разработчик с опытом {years} лет. Работаю с React, TypeScript, JavaScript ES6+. Имею опыт разработки SPA, знаю Redux, React Router, Webpack. Участвовал в создании корпоративных веб-приложений и пользовательских интерфейсов. Понимаю принципы адаптивной верстки, работал с CSS-препроцессорами и компонентными библиотеками.",

            "Специализируюсь на фронтенд-разработке более {years} лет. Опыт работы с Vue.js, React, Angular. Знаю современные инструменты сборки (Vite, Webpack), работал с REST API и GraphQL. Участвовал в создании интернет-магазинов и панелей администрирования. Понимаю принципы UX/UI, имею навыки кроссбраузерной разработки.",

            "Frontend Developer с {years}-летним опытом. Основной стек: React, TypeScript, Next.js. Работал над микрофронтендами, интеграцией с backend API, оптимизацией производительности. Знаком с методологиями разработки Agile/Scrum. Есть опыт менторства джунов, участвовал в code review и архитектурных решениях.",

            "Фронтенд-разработчик с акцентом на React-экосистему. За {years} лет работы создавал интерактивные веб-приложения, дашборды аналитики, CRM-системы. Знаю состояние менеджмент (Redux, Zustand), тестирование (Jest, RTL), CI/CD. Имею понимание современных практик разработки и архитектурных паттернов."
        ],
        1: [  # B2B Sales
            "Менеджер по продажам B2B с {years}-летним опытом работы с корпоративными клиентами. Специализируюсь на продажах IT-решений и бизнес-услуг. Успешно веду переговоры с ЛПР, строю долгосрочные партнерские отношения. Имею опыт работы с CRM-системами, знаю методики SPIN, BANT. Достигал KPI по объему продаж 105-120% плана.",

            "Sales manager с опытом {years} лет в B2B сегменте. Работал с ключевыми клиентами, развивал существующую базу, привлекал новых партнеров. Знаю специфику продаж в ритейле, логистике, производстве. Умею проводить презентации, переговоры на уровне топ-менеджмента. Владею техниками активных продаж и управления возражениями.",

            "Коммерческий директор/менеджер по продажам с {years}-летним опытом. Специализация: комплексные B2B решения, региональные продажи. Успешно запускал новые направления, внедрял процессы продаж. Имею опыт управления командой, постановки KPI. Знаю CRM AmoCRM, Bitrix24, работал с тендерными площадками.",

            "Regional Sales Manager с фокусом на B2B клиентов. За {years} лет развивал территории, работал с дистрибьюторами и прямыми клиентами. Имею опыт продаж промышленного оборудования, логистических услуг, софта. Знаю основы маркетинга, участвовал в разработке продуктовой стратегии и ценовой политики."
        ],
        2: [  # Кладовщик
            "Кладовщик с {years}-летним опытом работы на складах различного типа. Знаю принципы товарооборота, инвентаризации, ведения складской документации. Работал с системами учета (1С:Склад, WMS), знаком с требованиями охраны труда. Имею навыки работы с погрузочной техникой, организации рабочих процессов на складе.",

            "Специалист складского хозяйства с опытом {years} лет. Работал на распределительных центрах, складах розничных сетей. Знаю технологии приемки, размещения, отгрузки товаров. Умею работать с ТСД, знаком с принципами FIFO. Опыт проведения инвентаризаций, контроля остатков, работы с поставщиками.",

            "Кладовщик-оператор с {years}-летним стажем. Специализируюсь на автоматизированных складских комплексах. Знаю WMS-системы, работал с конвейерным оборудованием. Имею навыки комплектации заказов, контроля качества товаров. Понимаю логистические процессы, работал в режиме высокой интенсивности.",

            "Старший кладовщик с опытом {years} лет. Управлял небольшой командой, организовывал работу смен, контролировал выполнение планов. Знаю требования к хранению различных групп товаров, санитарные нормы. Имею опыт работы с документооборотом, ведения отчетности, взаимодействия с логистами."
        ],
        3: [  # iOS
            "iOS-разработчик с {years}-летним опытом создания мобильных приложений. Работаю на Swift, знаю Objective-C. Имею опыт разработки от MVP до энтерпрайз решений. Знаком с архитектурными паттернами (MVVM, VIPER), работал с Core Data, сетевым взаимодействием. Публиковал приложения в App Store, знаю процесс review.",

            "Senior iOS Developer с {years} годами опыта. Специализируюсь на нативной разработке под iOS/iPadOS. Создавал финтех приложения, социальные сети, e-commerce решения. Знаю UIKit, SwiftUI, Combine. Имею опыт интеграции с REST API, работы с push-уведомлениями, геолокацией, камерой.",

            "Mobile iOS Engineer с фокусом на пользовательский опыт. За {years} лет создал более 15 приложений различной сложности. Знаю принципы Human Interface Guidelines, работаю с анимациями, кастомными UI компонентами. Имею опыт оптимизации производительности, профилирования памяти, работы с многопоточностью.",

            "iOS-разработчик с {years}-летней экспертизой в мобильной разработке. Участвовал в создании приложений для банков, ритейла, медиа. Знаю современные подходы к архитектуре, тестированию, CI/CD для мобильных приложений. Имею опыт code review, менторинга, работы в кроссфункциональных командах."
        ],
        4: [  # Контент
            "Контент-менеджер с {years}-летним опытом создания и управления контентом в digital среде. Работаю с веб-сайтами, социальными сетями, email-рассылками. Знаю принципы SEO-копирайтинга, имею навыки работы с CMS, аналитическими системами. Создаю контент-планы, веду редакторские календари.",

            "Специалист по контенту с опытом {years} лет в области интернет-маркетинга. Создаю тексты для лендингов, социальных сетей, блогов. Знаю основы SMM, email-маркетинга, работал с инфлюенсерами. Имею навыки фотосъемки, базовой обработки изображений, создания креативов для рекламных кампаний.",

            "Content Manager с {years}-летним стажем в digital агентствах и корпорациях. Разрабатываю контент-стратегии, управляю командами копирайтеров и дизайнеров. Знаю инструменты аналитики (Google Analytics, Яндекс.Метрика), работал с различными CMS. Имею опыт запуска медиа-проектов.",

            "Редактор-контент менеджер с опытом {years} лет. Специализируюсь на создании образовательного и развлекательного контента. Работал с YouTube-каналами, подкастами, образовательными платформами. Знаю принципы сторителлинга, имею навыки видеомонтажа. Понимаю алгоритмы социальных платформ."
        ]
    }

    # Определяем количество лет опыта на основе индекса
    years_variants = [2, 3, 4, 5, 6, 3, 4, 2, 5, 3, 4, 6, 2, 3, 5]
    years = years_variants[candidate_index % len(years_variants)]

    # Выбираем шаблон
    template_list = templates.get(vacancy_idx, templates[0])  # fallback на Frontend
    template = template_list[candidate_index % len(template_list)]

    return template.format(years=years)

# Данные кандидатов
CANDIDATES_DATA = [
    # Frontend - Vacancy 1 (8 кандидатов)
    {"full_name": "Дмитрий Романов", "age": 28, "city": "Москва", "position": "Frontend Developer", "company": "Яндекс", "target_stage": "response", "ai_score": 45,
     "resume_text": "Frontend-разработчик с опытом 3 года. Работал в Яндексе над корпоративными приложениями на React и TypeScript. Участвовал в разработке системы аналитики для внутренних команд. Знаю Vue.js, но предпочитаю React-экосистему. Опыт работы с Redux, MobX, Webpack. Есть базовые знания Node.js для написания простых API."},
    {"full_name": "Анна Лебедева", "age": 25, "city": "Подольск", "position": "React Developer", "company": "Mail.ru", "target_stage": "response", "ai_score": 67},
    {"full_name": "Максим Орлов", "age": 32, "city": "Москва", "position": "Senior Frontend", "company": "Тинькофф", "target_stage": "response", "ai_score": 88},
    {"full_name": "Екатерина Соколова", "age": 27, "city": "Зеленоград", "position": "Frontend", "company": "Avito", "target_stage": "selected", "ai_score": 72},
    {"full_name": "Артём Воронов", "age": 30, "city": "Балашиха", "position": "Senior React", "company": "Сбер", "target_stage": "selected", "ai_score": 81},
    {"full_name": "Юлия Морозова", "age": 26, "city": "Москва", "position": "Frontend Developer", "company": "OZON", "target_stage": "recruiter", "ai_score": 76},
    {"full_name": "Никита Захаров", "age": 29, "city": "Реутов", "position": "React/TS Developer", "company": "Wildberries", "target_stage": "interview", "ai_score": 84},
    {"full_name": "Ольга Громова", "age": 31, "city": "Долгопрудный", "position": "Frontend Lead", "company": "X5", "target_stage": "offer", "ai_score": 92},

    # Продажи - Vacancy 2 (8 кандидатов)
    {"full_name": "Игорь Кузнецов", "age": 35, "city": "Санкт-Петербург", "position": "Менеджер B2B", "company": "Гермес", "target_stage": "response", "ai_score": 38},
    {"full_name": "Светлана Белова", "age": 33, "city": "СПб", "position": "Senior Sales", "company": "Wildberries", "target_stage": "response", "ai_score": 55},
    {"full_name": "Андрей Семёнов", "age": 38, "city": "СПб", "position": "Key Account Manager", "company": "Леруа Мерлен", "target_stage": "selected", "ai_score": 64},
    {"full_name": "Татьяна Зайцева", "age": 29, "city": "Колпино", "position": "Менеджер по работе с клиентами", "company": "Магнит", "target_stage": "selected", "ai_score": 70},
    {"full_name": "Сергей Мельников", "age": 41, "city": "СПб", "position": "Региональный менеджер", "company": "X5", "target_stage": "recruiter", "ai_score": 75},
    {"full_name": "Виктория Степанова", "age": 27, "city": "Пушкин", "position": "Sales Manager", "company": "OZON", "target_stage": "recruiter", "ai_score": 80},
    {"full_name": "Олег Котов", "age": 36, "city": "Гатчина", "position": "B2B Sales", "company": "Continental", "target_stage": "manager", "ai_score": 85},
    {"full_name": "Елена Никитина", "age": 30, "city": "СПб", "position": "Account Executive", "company": "Yota", "target_stage": "rejected", "ai_score": 42, "reject_reason": "Несоответствие опыта", "reject_side": "company"},

    # Кладовщик - Vacancy 3 (4 кандидата)
    {"full_name": "Ирина Волкова", "age": 42, "city": "Новосибирск", "position": "Кладовщик", "company": "Магнит", "target_stage": "response", "ai_score": None},
    {"full_name": "Алексей Соловьёв", "age": 38, "city": "Новосибирск", "position": "Комплектовщик", "company": "Wildberries", "target_stage": "response", "ai_score": 50},
    {"full_name": "Марина Павлова", "age": 34, "city": "Бердск", "position": "Старший кладовщик", "company": "X5", "target_stage": "interview", "ai_score": 78},
    {"full_name": "Денис Новиков", "age": 31, "city": "Новосибирск", "position": "Комплектовщик 1С", "company": "OZON", "target_stage": "hired", "ai_score": 89},

    # === +30 кандидатов (порядок соответствует vacancy_assignments) ===
    # Frontend — Vacancy idx 0 (+10)
    {"full_name": "Павел Дроздов", "age": 29, "city": "Москва", "position": "Frontend Developer", "company": "OZON", "target_stage": "added", "ai_score": 58},
    {"full_name": "Алиса Кравцова", "age": 26, "city": "Химки", "position": "React Developer", "company": "Сбер", "target_stage": "added", "ai_score": 63},
    {"full_name": "Григорий Лаптев", "age": 34, "city": "Москва", "position": "Senior Frontend", "company": "Avito", "target_stage": "selected", "ai_score": 79},
    {"full_name": "Вера Шестакова", "age": 28, "city": "Мытищи", "position": "Frontend Engineer", "company": "Тинькофф", "target_stage": "selected", "ai_score": 71},
    {"full_name": "Роман Цветков", "age": 31, "city": "Москва", "position": "React/TS Developer", "company": "VK", "target_stage": "recruiter", "ai_score": 83},
    {"full_name": "Дарья Беляева", "age": 27, "city": "Королёв", "position": "Frontend Developer", "company": "Яндекс", "target_stage": "recruiter", "ai_score": 75},
    {"full_name": "Кирилл Фомин", "age": 33, "city": "Москва", "position": "Senior React", "company": "Kaspersky", "target_stage": "interview", "ai_score": 87},
    {"full_name": "Надежда Ершова", "age": 25, "city": "Люберцы", "position": "Frontend", "company": "Wildberries", "target_stage": "interview", "ai_score": 69},
    {"full_name": "Станислав Гордеев", "age": 36, "city": "Москва", "position": "Frontend Lead", "company": "X5", "target_stage": "offer", "ai_score": 91},
    {"full_name": "Алёна Маркова", "age": 30, "city": "Одинцово", "position": "React Developer", "company": "МТС", "target_stage": "manager", "ai_score": 80},

    # Продажи — Vacancy idx 1 (+8)
    {"full_name": "Виталий Поляков", "age": 37, "city": "Санкт-Петербург", "position": "Менеджер B2B", "company": "Гермес", "target_stage": "added", "ai_score": 44},
    {"full_name": "Оксана Дёмина", "age": 32, "city": "СПб", "position": "Sales Manager", "company": "OZON", "target_stage": "response", "ai_score": 57},
    {"full_name": "Артур Савельев", "age": 40, "city": "Колпино", "position": "Key Account Manager", "company": "Магнит", "target_stage": "selected", "ai_score": 66},
    {"full_name": "Лариса Тихонова", "age": 29, "city": "Пушкин", "position": "Менеджер по продажам", "company": "Yota", "target_stage": "recruiter", "ai_score": 73},
    {"full_name": "Геннадий Блинов", "age": 43, "city": "СПб", "position": "Региональный менеджер", "company": "X5", "target_stage": "interview", "ai_score": 81},
    {"full_name": "Полина Жукова", "age": 28, "city": "Гатчина", "position": "Account Executive", "company": "Леруа Мерлен", "target_stage": "manager", "ai_score": 78},
    {"full_name": "Эдуард Климов", "age": 35, "city": "СПб", "position": "B2B Sales", "company": "Continental", "target_stage": "offer", "ai_score": 88},
    {"full_name": "Жанна Соболева", "age": 31, "city": "Колпино", "position": "Sales Manager", "company": "МегаФон", "target_stage": "rejected", "ai_score": 40, "reject_reason": "Завышенные ожидания по ЗП", "reject_side": "candidate"},

    # Кладовщик — Vacancy idx 2 (+6)
    {"full_name": "Виктор Гусев", "age": 39, "city": "Новосибирск", "position": "Кладовщик", "company": "Магнит", "target_stage": "response", "ai_score": None},
    {"full_name": "Раиса Сорокина", "age": 45, "city": "Бердск", "position": "Комплектовщик", "company": "Лента", "target_stage": "response", "ai_score": 48},
    {"full_name": "Тимур Исаев", "age": 33, "city": "Новосибирск", "position": "Старший кладовщик", "company": "OZON", "target_stage": "selected", "ai_score": 70},
    {"full_name": "Зоя Кудрявцева", "age": 36, "city": "Новосибирск", "position": "Кладовщик-оператор", "company": "X5", "target_stage": "interview", "ai_score": 74},
    {"full_name": "Леонид Панов", "age": 41, "city": "Искитим", "position": "Комплектовщик 1С", "company": "Wildberries", "target_stage": "hired", "ai_score": 86},
    {"full_name": "Галина Фёдорова", "age": 38, "city": "Новосибирск", "position": "Кладовщик", "company": "Магнит", "target_stage": "rejected", "ai_score": 39, "reject_reason": "Не вышел на связь", "reject_side": "candidate"},

    # iOS (архивная idx 3, archive_result=hired) (+3)
    {"full_name": "Артём Лазарев", "age": 30, "city": "Москва", "position": "iOS Developer (Swift)", "company": "Тинькофф", "target_stage": "hired", "ai_score": 90},
    {"full_name": "Светлана Гречко", "age": 28, "city": "Москва", "position": "iOS Engineer", "company": "VK", "target_stage": "rejected", "ai_score": 61, "reject_reason": "Принял другой оффер", "reject_side": "candidate"},
    {"full_name": "Богдан Юдин", "age": 34, "city": "Москва", "position": "Senior iOS", "company": "Сбер", "target_stage": "interview", "ai_score": 77},

    # Контент (архивная idx 4, archive_result=cancelled) (+3)
    {"full_name": "Маргарита Власова", "age": 27, "city": "Санкт-Петербург", "position": "Контент-менеджер", "company": "Avito", "target_stage": "rejected", "ai_score": 52, "reject_reason": "Несоответствие навыков", "reject_side": "company"},
    {"full_name": "Игнат Прохоров", "age": 31, "city": "СПб", "position": "Контент-редактор", "company": "OZON", "target_stage": "interview", "ai_score": 68},
    {"full_name": "Ульяна Зуева", "age": 25, "city": "СПб", "position": "SMM-менеджер", "company": "Магнит", "target_stage": "response", "ai_score": 55},
]

CLIENTS_DATA = [
    {"name": "ООО «Технологии Будущего»", "contact_person": "Иван Петров"},
    {"name": "Торговая сеть «Прогресс»", "contact_person": "Мария Сидорова"},
    {"name": "Логистик Групп", "contact_person": "Алексей Иванов"},
]

VACANCIES_DATA = [
    {"name": "Senior Frontend Developer", "client_idx": 0, "location": "Москва", "salary_from": 200000, "salary_to": 280000},
    {"name": "Менеджер по продажам B2B", "client_idx": 1, "location": "Санкт-Петербург", "salary_from": 80000, "salary_to": 120000},
    {"name": "Кладовщик", "client_idx": 2, "location": "Новосибирск", "salary_from": 45000, "salary_to": 60000},
    # Архивные вакансии (idx 3, 4)
    {"name": "iOS-разработчик (Swift)", "client_idx": 0, "location": "Москва", "salary_from": 250000, "salary_to": 350000,
     "status": "archived", "archive_result": "hired", "closed_at": date.today() - timedelta(days=20)},
    {"name": "Контент-менеджер", "client_idx": 1, "location": "Санкт-Петербург", "salary_from": 70000, "salary_to": 100000,
     "status": "archived", "archive_result": "cancelled", "closed_at": date.today() - timedelta(days=48)},
]


async def cleanup_demo(session: AsyncSession):
    """Удаляет все demo данные для идемпотентности"""
    logger.info("Cleaning up demo data...")

    # Список demo кандидатов для удаления связанных записей
    demo_candidate_ids_query = select(Candidate.id).where(
        Candidate.extra.op("->>")('"demo"') == 'true'
    )

    # Удаляем employees связанные с demo кандидатами
    await session.execute(
        delete(Employee).where(Employee.candidate_id.in_(demo_candidate_ids_query))
    )

    # Удаляем applications для demo кандидатов
    await session.execute(
        delete(Application).where(Application.candidate_id.in_(demo_candidate_ids_query))
    )

    # Удаляем consents для demo кандидатов и старые PD номера
    await session.execute(
        delete(Consent).where(Consent.candidate_id.in_(demo_candidate_ids_query))
    )
    # Также удаляем по номерам для идемпотентности (старые демо данные)
    await session.execute(
        delete(Consent).where(Consent.number.in_(['PD001', 'PD002', 'PD003']))
    )

    # Удаляем documents для demo кандидатов
    await session.execute(
        delete(Document).where(Document.candidate_id.in_(demo_candidate_ids_query))
    )

    # Удаляем messages для demo кандидатов
    await session.execute(
        delete(Message).where(Message.candidate_id.in_(demo_candidate_ids_query))
    )

    # Удаляем evaluations для demo кандидатов
    await session.execute(
        delete(AiEvaluation).where(AiEvaluation.candidate_id.in_(demo_candidate_ids_query))
    )

    # Удаляем demo кандидатов
    await session.execute(
        delete(Candidate).where(
            Candidate.extra.op("->>")('"demo"') == 'true'
        )
    )

    # Удаляем demo вакансии по именам
    demo_vacancy_names = [v["name"] for v in VACANCIES_DATA]
    await session.execute(
        delete(Vacancy).where(Vacancy.name.in_(demo_vacancy_names))
    )

    # Удаляем demo клиентов по именам
    demo_client_names = [c["name"] for c in CLIENTS_DATA]
    await session.execute(
        delete(Client).where(Client.name.in_(demo_client_names))
    )

    logger.info("Demo data cleanup completed")


async def seed_clients(session: AsyncSession) -> list[Client]:
    """Создаёт demo клиентов"""
    logger.info("Creating demo clients...")

    clients = []
    for client_data in CLIENTS_DATA:
        client = Client(
            company_id=COMPANY_ID,
            name=client_data["name"],
            contact_person=client_data["contact_person"]
        )
        session.add(client)
        clients.append(client)

    await session.flush()  # Чтобы получить ID
    logger.info(f"Created {len(clients)} demo clients")
    return clients


async def seed_vacancies(session: AsyncSession, clients: list[Client], admin: User) -> list[Vacancy]:
    """Создаёт demo вакансии с этапами"""
    logger.info("Creating demo vacancies...")

    # Стандартные этапы для всех вакансий
    # 9 этапов 1:1 по эталону (включая системный «Добавлен»)
    stages = [
        {"stage_key": "response", "label": "Отклик", "order_index": 1},
        {"stage_key": "added", "label": "Добавлен", "order_index": 2},
        {"stage_key": "selected", "label": "Отобран", "order_index": 3},
        {"stage_key": "recruiter", "label": "Контакт с рекрутером", "order_index": 4},
        {"stage_key": "interview", "label": "Интервью", "order_index": 5},
        {"stage_key": "manager", "label": "Контакт с менеджером", "order_index": 6},
        {"stage_key": "offer", "label": "Оффер", "order_index": 7},
        {"stage_key": "hired", "label": "Нанят", "order_index": 8, "is_terminal": True},
        {"stage_key": "rejected", "label": "Отказ", "order_index": 9, "is_terminal": True},
    ]

    vacancies = []
    for i, vacancy_data in enumerate(VACANCIES_DATA):
        # Детальные описания вакансий
        vacancy_descriptions = [
            # 0: Senior Frontend Developer
            "Ищем опытного фронтенд-разработчика в команду разработки корпоративных продуктов. "
            "Требования: React 16+, TypeScript, опыт работы с REST API и WebSocket, знание современных инструментов сборки (Webpack/Vite). "
            "Ожидаем: создание переиспользуемых компонентов, оптимизация производительности, участие в code review, менторинг младших разработчиков. "
            "Будет плюсом: опыт работы с микрофронтендами, знание Node.js, опыт настройки CI/CD.",

            # 1: Менеджер по продажам B2B
            "Приглашаем менеджера по продажам для развития B2B направления. "
            "Требования: опыт продаж корпоративным клиентам от 3 лет, знание техник активных продаж, опыт работы с CRM-системами. "
            "Обязанности: поиск и привлечение новых клиентов, ведение переговоров с ЛПР, развитие существующей клиентской базы, участие в тендерах. "
            "Условия: высокая мотивационная часть, корпоративная мобильная связь, социальный пакет.",

            # 2: Кладовщик
            "В связи с расширением ищем ответственного кладовщика на современный автоматизированный склад. "
            "Требования: опыт работы на складе от 2 лет, знание принципов складского учета, опыт работы с ТСД и 1С. "
            "Обязанности: приемка и размещение товаров, комплектация заказов, проведение инвентаризаций, ведение складской документации. "
            "Условия: сменный график 2/2, бесплатное питание, развозка, медицинское страхование.",

            # 3: iOS-разработчик
            "Ищем iOS-разработчика для создания мобильных финтех решений нового поколения. "
            "Требования: Swift, опыт разработки от 3 лет, знание UIKit и SwiftUI, опыт публикации в App Store. "
            "Задачи: разработка новых функций мобильного приложения, оптимизация производительности, интеграция с backend API. "
            "Ожидаем: понимание архитектурных паттернов, опыт работы с Core Data, знание принципов безопасности в финтех.",

            # 4: Контент-менеджер
            "Приглашаем креативного контент-менеджера для развития digital-присутствия компании. "
            "Требования: опыт создания контента от 2 лет, знание принципов SEO, навыки копирайтинга и SMM. "
            "Обязанности: создание контент-планов, написание текстов для сайта и соцсетей, координация фото/видеосъемок, анализ эффективности контента. "
            "Будет плюсом: опыт работы с WordPress, базовые навыки дизайна, знание инструментов аналитики."
        ]

        description = vacancy_descriptions[i] if i < len(vacancy_descriptions) else f"Demo вакансия: {vacancy_data['name']}"

        vacancy = Vacancy(
            company_id=COMPANY_ID,
            client_id=clients[vacancy_data["client_idx"]].id,
            name=vacancy_data["name"],
            description=description,
            city=vacancy_data["location"],
            salary_from=vacancy_data["salary_from"],
            salary_to=vacancy_data["salary_to"],
            currency="RUB",
            employment_type="full_time",
            status=vacancy_data.get("status", "active"),
            archive_result=vacancy_data.get("archive_result"),
            closed_at=vacancy_data.get("closed_at"),
            responsible_user_id=admin.id,
        )
        session.add(vacancy)
        await session.flush()  # Получить ID вакансии

        # Создаём этапы для вакансии
        for stage_data in stages:
            stage = VacancyStage(
                company_id=COMPANY_ID,
                vacancy_id=vacancy.id,
                stage_key=stage_data["stage_key"],
                label=stage_data["label"],
                order_index=stage_data["order_index"],
                is_terminal=stage_data.get("is_terminal", False)
            )
            session.add(stage)

        vacancies.append(vacancy)

    await session.flush()
    logger.info(f"Created {len(vacancies)} demo vacancies with stages")
    return vacancies


async def seed_candidates(session: AsyncSession) -> list[Candidate]:
    """Создаёт demo кандидатов"""
    logger.info("Creating demo candidates...")

    # Соответствие кандидат -> вакансия (такое же как в seed_applications_and_move)
    vacancy_assignments = (
        [0] * 8 + [1] * 8 + [2] * 4        # существующие 20 (vac 0/1/2)
        + [0] * 10 + [1] * 8 + [2] * 6     # +24 новых на активные вакансии
        + [3] * 3 + [4] * 3                # +6 новых на архивные (idx 3,4)
    )  # итого 50 кандидатов

    candidates = []
    for i, candidate_data in enumerate(CANDIDATES_DATA):
        # Разбираем ФИО
        name_parts = candidate_data["full_name"].split(" ")
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Дата рождения на основе возраста
        birth_year = date.today().year - candidate_data["age"]
        birth_date = date(birth_year, 1, 15)  # Примерная дата

        # Телефон — детерминированный псевдослучайный (+7 9XX XXX-XX-XX), помещается в String(20)
        phone = f"+7 9{(13 + i) % 90:02d} {(100 + i * 37) % 900:03d}-{(11 + i * 7) % 90:02d}-{(13 + i * 13) % 90:02d}"
        # Мессенджеры — варьируем как в эталоне (telegram / whatsapp / max)
        messenger_variants = [
            ["telegram"],
            ["telegram", "whatsapp"],
            ["telegram", "max"],
            ["whatsapp", "max"],
            ["telegram", "whatsapp", "max"],
        ]
        messengers = messenger_variants[i % len(messenger_variants)]
        # Зарплатные ожидания — для наполнения колонки ЗП в воронке
        salary_expectation = 150000 + (i * 13000) % 250000

        # Генерируем резюме на основе типа вакансии
        vacancy_idx = vacancy_assignments[i]
        resume_text = generate_resume_text(i, vacancy_idx)

        candidate = Candidate(
            company_id=COMPANY_ID,
            display_number=f"D{i+1:03d}",
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
            city=candidate_data["city"],
            phone=phone,
            salary_expectation=salary_expectation,
            last_position=candidate_data["position"],
            last_company=candidate_data["company"],
            resume_text=resume_text,
            source="manual",
            preferred_channel="telegram",
            messengers=messengers,
            extra={"demo": "true"}
        )
        session.add(candidate)
        candidates.append(candidate)

    await session.flush()
    logger.info(f"Created {len(candidates)} demo candidates")
    return candidates


async def seed_experience(session: AsyncSession, candidates: list[Candidate]):
    """Создаёт опыт работы для demo кандидатов"""
    logger.info("Creating demo candidate experience...")

    # Соответствие кандидат -> вакансия (такое же как в seed_candidates)
    vacancy_assignments = (
        [0] * 8 + [1] * 8 + [2] * 4        # существующие 20 (vac 0/1/2)
        + [0] * 10 + [1] * 8 + [2] * 6     # +24 новых на активные вакансии
        + [3] * 3 + [4] * 3                # +6 новых на архивные (idx 3,4)
    )  # итого 50 кандидатов

    experience_templates = {
        0: [  # Frontend
            [
                ("Junior Frontend Developer", "Веб-студия Digit", "2021-2022", "Верстка лендингов, поддержка корпоративного сайта. HTML, CSS, JavaScript, jQuery."),
                ("Frontend Developer", "Яндекс", "2022-2024", "Разработка корпоративных приложений на React. Создание переиспользуемых компонентов, интеграция с REST API."),
                ("Senior Frontend", "Тинькофф", "2024-н.в.", "Ведущий разработчик в команде интернет-банкинга. Архитектурные решения, ментoring джуниоров.")
            ],
            [
                ("React Developer", "Стартап AI-платформа", "2020-2022", "Создание MVP продукта с нуля. React, TypeScript, Redux. Работа в небольшой команде."),
                ("Frontend Engineer", "Mail.ru", "2022-2024", "Разработка пользовательского интерфейса для социальной сети. Оптимизация производительности, A/B тестирование."),
            ],
            [
                ("Верстальщик", "Фриланс", "2019-2021", "Верстка интернет-магазинов, корпоративных сайтов. HTML, CSS, Bootstrap, базовый JavaScript."),
                ("Frontend Developer", "Avito", "2021-2023", "Разработка фронтенда для сервисов объявлений. React, Redux, микрофронтенды."),
                ("Senior Frontend", "Сбер", "2023-н.в.", "Техлид направления мобильного банкинга. Vue.js, современные инструменты разработки.")
            ]
        ],
        1: [  # B2B Sales
            [
                ("Менеджер по работе с клиентами", "Региональный дистрибьютор", "2020-2022", "Ведение базы корпоративных клиентов, развитие продаж в регионе. CRM AmoCRM."),
                ("Senior Sales Manager", "Гермес", "2022-2024", "Ключевые клиенты, переговоры с ЛПР. Превышение плана продаж на 15-25%."),
                ("Regional Sales Director", "Wildberries", "2024-н.в.", "Развитие B2B направления, управление командой из 8 менеджеров.")
            ],
            [
                ("Sales Manager", "IT-интегратор", "2019-2021", "Продажи ПО и услуг интеграции корпоративным клиентам. Работа с тендерными площадками."),
                ("Key Account Manager", "Леруа Мерлен", "2021-2023", "Развитие ключевых корпоративных клиентов. Переговоры по долгосрочным контрактам."),
                ("B2B Sales Lead", "X5", "2023-н.в.", "Руководство отделом корпоративных продаж, KPI команды, стратегическое планирование.")
            ]
        ],
        2: [  # Кладовщик
            [
                ("Комплектовщик", "Склад Магнит", "2020-2022", "Комплектация заказов, работа с ТСД, соблюдение требований по срокам отгрузки."),
                ("Кладовщик", "Wildberries РЦ", "2022-2024", "Приемка, размещение, отгрузка товаров. Работа с 1С:Склад, проведение инвентаризаций."),
                ("Старший кладовщик", "X5 Distribution", "2024-н.в.", "Организация работы смены, контроль качества, взаимодействие с логистами.")
            ],
            [
                ("Грузчик-комплектовщик", "Лента", "2019-2021", "Разгрузка товаров, комплектация заказов для розничной сети. Опыт работы с погрузчиком."),
                ("Кладовщик", "OZON", "2021-2024", "Обработка заказов интернет-магазина, упаковка, подготовка к отгрузке. WMS-система."),
            ]
        ],
        3: [  # iOS
            [
                ("Junior iOS Developer", "Мобильная студия", "2021-2022", "Разработка простых приложений, изучение Swift, UIKit. Участие в командных проектах."),
                ("iOS Developer", "Тинькофф", "2022-2024", "Разработка банковских приложений, работа с Core Data, push-уведомления, безопасность."),
                ("Senior iOS Engineer", "VK", "2024-н.в.", "Архитектурные решения для соцсетей, performance optimization, менторинг команды.")
            ]
        ],
        4: [  # Контент
            [
                ("Копирайтер", "Маркетинговое агентство", "2020-2022", "Создание текстов для лендингов, email-рассылок, социальных сетей. SEO-оптимизация."),
                ("Контент-менеджер", "Avito", "2022-2024", "Управление контент-стратегией, работа с блогом компании, координация съемочных процессов."),
                ("Content Lead", "OZON", "2024-н.в.", "Руководство командой контент-менеджеров, развитие медиа-направления компании.")
            ]
        ]
    }

    total_experience = 0
    for i, candidate in enumerate(candidates):
        vacancy_idx = vacancy_assignments[i]

        # Получаем шаблон опыта для данного типа вакансии
        templates = experience_templates.get(vacancy_idx, experience_templates[0])
        template = templates[i % len(templates)]

        # Создаем записи опыта для кандидата
        for order_index, (position, company, period, description) in enumerate(template):
            experience = CandidateExperience(
                company_id=COMPANY_ID,
                candidate_id=candidate.id,
                position=position,
                company=company,
                period=period,
                description=description,
                order_index=order_index
            )
            session.add(experience)
            total_experience += 1

    await session.flush()
    logger.info(f"Created {total_experience} experience records for {len(candidates)} candidates")


async def seed_skills(session: AsyncSession, candidates: list[Candidate]):
    """Создаёт навыки для demo кандидатов"""
    logger.info("Creating demo candidate skills...")

    # Соответствие кандидат -> вакансия (такое же как в seed_candidates)
    vacancy_assignments = (
        [0] * 8 + [1] * 8 + [2] * 4        # существующие 20 (vac 0/1/2)
        + [0] * 10 + [1] * 8 + [2] * 6     # +24 новых на активные вакансии
        + [3] * 3 + [4] * 3                # +6 новых на архивные (idx 3,4)
    )  # итого 50 кандидатов

    skills_templates = {
        0: [  # Frontend
            ["JavaScript", "React", "TypeScript", "HTML", "CSS", "Redux", "Webpack", "Git", "REST API", "Node.js", "Jest", "ESLint"],
            ["Vue.js", "React", "JavaScript", "TypeScript", "Vuex", "Nuxt.js", "SCSS", "Vite", "GraphQL", "Docker", "Figma"],
            ["React", "Next.js", "TypeScript", "Styled Components", "Zustand", "React Query", "Storybook", "Cypress", "CI/CD"],
            ["Angular", "RxJS", "TypeScript", "NgRx", "Material UI", "Karma", "Protractor", "Jenkins", "JIRA", "Agile"]
        ],
        1: [  # B2B Sales
            ["CRM AmoCRM", "Excel", "Переговоры", "Продажи B2B", "KPI управление", "SPIN техники", "Презентации", "Аналитика"],
            ["Bitrix24", "Продажи", "Управление клиентами", "Тендеры", "1С", "PowerPoint", "Холодные звонки", "BANT"],
            ["HubSpot", "Account management", "Консультативные продажи", "Работа с возражениями", "Salesforce", "Lead generation"],
            ["Планирование продаж", "Team management", "Forecasting", "Channel sales", "Partner management", "ROI анализ"]
        ],
        2: [  # Кладовщик
            ["1С Склад", "ТСД", "WMS системы", "Инвентаризация", "Товарооборот", "Складской учет", "Погрузчик", "FIFO"],
            ["Комплектация", "Приемка товаров", "SAP WM", "Excel", "Контроль качества", "Логистика", "Упаковка"],
            ["Управление складом", "Планирование", "Охрана труда", "Организация процессов", "Обучение персонала"],
            ["Автоматизированные склады", "Конвейерное оборудование", "RFID", "Barcode сканеры", "Lean"]
        ],
        3: [  # iOS
            ["Swift", "UIKit", "SwiftUI", "Xcode", "Core Data", "iOS SDK", "Objective-C", "Git", "REST API", "Push notifications"],
            ["iOS", "Combine", "MVVM", "Auto Layout", "Core Animation", "TestFlight", "App Store", "CocoaPods", "SPM"],
            ["VIPER", "RxSwift", "Realm", "Fastlane", "Alamofire", "Kingfisher", "Performance optimization", "Memory management"]
        ],
        4: [  # Контент
            ["Копирайтинг", "SEO", "Content strategy", "SMM", "WordPress", "Google Analytics", "Figma", "Photoshop"],
            ["Контент-планирование", "Email marketing", "Targetowanie", "YouTube", "Podcast", "Видеомонтаж"],
            ["Editorial calendar", "Brand voice", "UGC", "Influencer marketing", "A/B testing", "Conversion optimization"]
        ]
    }

    total_skills = 0
    for i, candidate in enumerate(candidates):
        vacancy_idx = vacancy_assignments[i]

        # Получаем шаблон навыков для данного типа вакансии
        all_skills = skills_templates.get(vacancy_idx, skills_templates[0])

        # Выбираем 8-15 навыков из доступных
        base_skills = all_skills[i % len(all_skills)]
        num_skills = 8 + (i % 8)  # от 8 до 15 навыков

        # Берем первые N навыков и перемешиваем немного для разнообразия
        selected_skills = base_skills[:num_skills]
        if len(all_skills) > 1:
            # Добавляем несколько навыков из других шаблонов
            extra_template = all_skills[(i + 1) % len(all_skills)]
            selected_skills.extend(extra_template[:2])

        # Создаем записи навыков для кандидата
        for order_index, skill in enumerate(selected_skills[:15]):  # максимум 15
            candidate_skill = CandidateSkill(
                company_id=COMPANY_ID,
                candidate_id=candidate.id,
                skill=skill,
                order_index=order_index
            )
            session.add(candidate_skill)
            total_skills += 1

    await session.flush()
    logger.info(f"Created {total_skills} skills for {len(candidates)} candidates")


def get_stage_transition_timestamps(target_stage: str, base_date: datetime) -> dict[str, datetime]:
    """Генерирует монотонные timestamps для переходов между этапами"""
    stage_order = ["response", "selected", "recruiter", "interview", "manager", "offer", "hired", "rejected"]

    if target_stage not in stage_order:
        return {"response": base_date}

    target_index = stage_order.index(target_stage)
    timestamps = {}
    current_time = base_date

    # Реалистичные интервалы между переходами (в часах)
    intervals = {
        "response": 0,
        "selected": 24 + (24 * 1),  # 1-2 дня
        "recruiter": 24 * 2 + (24 * 1),  # 2-3 дня
        "interview": 24 * 3 + (24 * 2),  # 3-5 дней
        "manager": 24 * 2 + (24 * 2),  # 2-4 дня
        "offer": 24 * 3 + (24 * 2),  # 3-5 дней
        "hired": 24 * 2 + (24 * 1),  # 2-3 дня
        "rejected": 0,  # может быть на любом этапе
    }

    timestamps["response"] = current_time

    for i in range(1, target_index + 1):
        stage = stage_order[i]
        if stage == "rejected":
            timestamps[stage] = current_time + timedelta(hours=12)  # Отказ через полдня
        else:
            hours_to_add = intervals.get(stage, 24)
            current_time += timedelta(hours=hours_to_add)
            timestamps[stage] = current_time

    return timestamps


async def seed_applications_and_move(session: AsyncSession, candidates: list[Candidate], vacancies: list[Vacancy], admin: User):
    """Создаёт applications и перемещает их через этапы с реалистичными timestamps"""
    logger.info("Creating demo applications...")

    # Распределение кандидатов по вакансиям
    vacancy_assignments = (
        [0] * 8 + [1] * 8 + [2] * 4        # существующие 20 (vac 0/1/2)
        + [0] * 10 + [1] * 8 + [2] * 6     # +24 новых на активные вакансии
        + [3] * 3 + [4] * 3                # +6 новых на архивные (idx 3,4)
    )  # итого 50 кандидатов

    # Базовая дата - 90 дней назад
    base_date = datetime.now(timezone.utc) - timedelta(days=90)

    applications = []
    for i, candidate in enumerate(candidates):
        candidate_data = CANDIDATES_DATA[i]
        vacancy_idx = vacancy_assignments[i]
        vacancy = vacancies[vacancy_idx]
        target_stage = candidate_data["target_stage"]

        # Распределяем отклики по разным датам за последние 90 дней
        days_offset = (i * 4) % 90  # Каждый 4-й день, циклично
        response_date = base_date + timedelta(days=days_offset)

        # Создаём application
        application = Application(
            company_id=COMPANY_ID,
            candidate_id=candidate.id,
            vacancy_id=vacancy.id,
            stage="response",
            ai_score=candidate_data.get("ai_score"),
            source="manual",
            created_at=response_date,
            updated_at=response_date
        )
        session.add(application)
        await session.flush()  # Получить ID

        # «Добавлен» — кандидат заведён вручную, остаётся на входном этапе без переходов
        if target_stage == "added":
            application.stage = "added"
            application.stage_changed_at = response_date
            applications.append(application)
            continue

        # Если нужен rejected, устанавливаем причину
        if target_stage == "rejected":
            application.reject_reason = candidate_data.get("reject_reason")
            application.reject_side = candidate_data.get("reject_side")

        # Получаем timestamps для всех переходов
        timestamps = get_stage_transition_timestamps(target_stage, response_date)

        # Создаём stage_history записи вручную для точных timestamps
        if target_stage != "response":
            # Первый переход: response -> selected
            if "selected" in timestamps:
                stage_history = StageHistory(
                    application_id=application.id,
                    from_stage="response",
                    to_stage="selected",
                    actor_type="human",
                    actor_user_id=admin.id,
                    created_at=timestamps["selected"]
                )
                session.add(stage_history)
                application.stage = "selected"
                application.selected_at = timestamps["selected"]
                application.stage_changed_at = timestamps["selected"]

            # Продолжаем по цепочке до целевого этапа
            stage_order = ["response", "selected", "recruiter", "interview", "manager", "offer", "hired", "rejected"]
            current_stage_idx = stage_order.index("selected")
            target_stage_idx = stage_order.index(target_stage)

            while current_stage_idx < target_stage_idx:
                from_stage = stage_order[current_stage_idx]
                to_stage = stage_order[current_stage_idx + 1]

                if to_stage in timestamps:
                    stage_history = StageHistory(
                        application_id=application.id,
                        from_stage=from_stage,
                        to_stage=to_stage,
                        actor_type="human",
                        actor_user_id=admin.id,
                        created_at=timestamps[to_stage]
                    )
                    session.add(stage_history)
                    application.stage = to_stage
                    application.stage_changed_at = timestamps[to_stage]

                current_stage_idx += 1

        # Если цель hired, создаём Employee через сервис
        if target_stage == "hired":
            # Устанавливаем на offer перед переходом в hired
            application.stage = "offer"
            application.stage_changed_at = timestamps.get("offer", timestamps["response"])
            await session.flush()

            # Теперь двигаем в hired через сервис
            await move_application(session, application.id, MoveRequest(to_stage="hired"), COMPANY_ID, admin.id)

            # После создания Employee через сервис, корректируем timestamps в stage_history
            # Находим самую последнюю запись stage_history для этой заявки
            hired_history = await session.execute(
                select(StageHistory).where(
                    StageHistory.application_id == application.id
                ).order_by(StageHistory.created_at.desc()).limit(1)
            )
            hired_record = hired_history.scalar_one_or_none()
            if hired_record and hired_record.to_stage == "hired":
                hired_record.created_at = timestamps["hired"]

            # Также корректируем start_date у Employee
            employee = await session.execute(
                select(Employee).where(Employee.application_id == application.id)
            )
            employee_record = employee.scalar_one_or_none()
            if employee_record:
                # start_date = 35 дней назад от сегодня
                employee_record.start_date = date.today() - timedelta(days=35)

        applications.append(application)

    await session.flush()
    logger.info(f"Created {len(applications)} demo applications with stage transitions")
    return applications


async def seed_extras(session: AsyncSession, candidates: list[Candidate]):
    """Создаёт дополнительные данные: consents, documents, messages, evaluations"""
    logger.info("Creating demo extras...")

    # Создаём consents для первых 3 кандидатов
    for i in range(3):
        candidate = candidates[i]
        consent = Consent(
            company_id=COMPANY_ID,
            candidate_id=candidate.id,
            number=f"PD{i+1:03d}",
            status="signed",
            signed_at=datetime.now(timezone.utc) - timedelta(days=30 - i*5),
        )
        session.add(consent)

    # Создаём documents для 5 кандидатов
    for i in [0, 1, 2, 8, 16]:  # Романов, Лебедева, Орлов, Кузнецов, Волкова
        candidate = candidates[i]
        candidate_name = CANDIDATES_DATA[i]["full_name"].replace(" ", "_")
        document = Document(
            company_id=COMPANY_ID,
            candidate_id=candidate.id,
            filename=f"resume_{candidate_name}.pdf",
            storage_path=f"/demo/resumes/{candidate_name}.pdf",
            size_bytes=250000 + i*10000,  # 250-290KB
            file_type="pdf",
            source="manual",
        )
        session.add(document)

    # Создаём messages для 3 кандидатов
    message_candidates = [0, 3, 8]  # Романов, Соколова, Кузнецов
    for idx in message_candidates:
        candidate = candidates[idx]

        # Исходящее сообщение
        out_message = Message(
            company_id=COMPANY_ID,
            candidate_id=candidate.id,
            direction="out",
            channel="telegram",
            sender_type="recruiter",
            body=f"Здравствуйте! Мы рассмотрели ваше резюме и хотели бы пригласить на собеседование.",
            sent_at=datetime.now(timezone.utc) - timedelta(days=20 - idx*2),
        )
        session.add(out_message)

        # Входящий ответ
        in_message = Message(
            company_id=COMPANY_ID,
            candidate_id=candidate.id,
            direction="in",
            channel="telegram",
            sender_type="candidate",
            body="Здравствуйте! Спасибо за приглашение. Я заинтересован(а) в вакансии.",
            sent_at=datetime.now(timezone.utc) - timedelta(days=19 - idx*2),
        )
        session.add(in_message)

    # MOK AiEvaluation удален - теперь создаётся реальным скорингом в seed_real_scoring
    logger.info("Created demo extras: 3 consents, 5 documents, 6 messages")


async def seed_surveys(session: AsyncSession):
    """Создаёт pulse surveys для hired employee (Денис Новиков)"""
    logger.info("Creating demo pulse surveys...")

    # Находим hired employee среди demo кандидатов
    employee_query = await session.execute(
        select(Employee).where(
            Employee.candidate_id.in_(
                select(Candidate.id).where(
                    and_(
                        Candidate.first_name == "Денис",
                        Candidate.last_name == "Новиков",
                        Candidate.extra.op("->>")('"demo"') == 'true'
                    )
                )
            )
        )
    )
    employee = employee_query.scalar_one_or_none()

    if not employee:
        logger.warning("Employee not found for pulse surveys")
        return

    start_date = employee.start_date

    # Первый опрос через 14 дней
    survey1_sent = datetime.combine(start_date + timedelta(days=14), datetime.min.time()).replace(tzinfo=timezone.utc)
    survey1_answered = survey1_sent + timedelta(days=1)

    survey1 = PulseSurvey(
        company_id=COMPANY_ID,
        employee_id=employee.id,
        type="weekly",
        sent_at=survey1_sent,
        answered_at=survey1_answered,
        overall_score=Decimal("4.2"),
        answers={
            "items": [
                {"id": "q1", "type": "scale_5", "text": "Довольны ли процессом адаптации?", "answer": "4"},
                {"id": "q2", "type": "scale_5", "text": "Как оцениваете поддержку коллег?", "answer": "4"}
            ]
        }
    )
    session.add(survey1)

    # Второй опрос через 28 дней
    survey2_sent = datetime.combine(start_date + timedelta(days=28), datetime.min.time()).replace(tzinfo=timezone.utc)
    survey2_answered = survey2_sent + timedelta(days=1)

    survey2 = PulseSurvey(
        company_id=COMPANY_ID,
        employee_id=employee.id,
        type="weekly",
        sent_at=survey2_sent,
        answered_at=survey2_answered,
        overall_score=Decimal("4.5"),
        answers={
            "items": [
                {"id": "q1", "type": "scale_5", "text": "Довольны ли процессом адаптации?", "answer": "5"},
                {"id": "q2", "type": "scale_5", "text": "Как оцениваете поддержку коллег?", "answer": "4"}
            ]
        }
    )
    session.add(survey2)

    logger.info("Created 2 demo pulse surveys")


async def seed_real_scoring(session: AsyncSession, candidates: list[Candidate], applications: list[Application], admin: User):
    """Запускает реальный AI-скоринг для всех кандидатов (только если REAL_SCORING=true)"""

    if os.getenv("REAL_SCORING") != "true":
        logger.info("REAL_SCORING not enabled, skipping real AI scoring")
        return

    logger.info("Starting REAL AI scoring for all candidates...")

    # Импортируем скоринг здесь, чтобы избежать circular imports
    from app.services.glafira.scoring import score_candidate

    successful_scores = 0
    failed_scores = 0

    for i, application in enumerate(applications):
        try:
            logger.info(f"Scoring candidate {i+1}/{len(applications)}: {application.candidate.full_name}")

            # Запускаем реальный скоринг
            evaluation = await score_candidate(
                session,
                candidate_id=application.candidate_id,
                vacancy_id=application.vacancy_id,
                company_id=COMPANY_ID,
                actor_user_id=admin.id
            )

            successful_scores += 1
            logger.info(f"✓ Scored: {evaluation.score} points, verdict: {evaluation.verdict}")

            # Пауза между вызовами для предотвращения rate limiting
            await asyncio.sleep(1.2)

        except Exception as e:
            failed_scores += 1
            logger.exception(f"✗ Failed to score candidate {application.candidate.full_name}: {e}")
            continue

    logger.info(f"Real scoring completed: {successful_scores} successful, {failed_scores} failed")


async def main():
    """Главная функция seed_demo"""
    logger.info("Starting demo seed...")

    async with AsyncSessionLocal() as session:
        try:
            # Получаем admin пользователя
            admin_query = await session.execute(select(User).where(User.email == ADMIN_EMAIL))
            admin = admin_query.scalar_one_or_none()

            if not admin:
                raise Exception(f"Admin user {ADMIN_EMAIL} not found. Run 'python -m app.seed' first.")

            # Шаг 1: Очистка
            await cleanup_demo(session)

            # Шаг 2: Создаём клиентов
            clients = await seed_clients(session)

            # Шаг 3: Создаём вакансии
            vacancies = await seed_vacancies(session, clients, admin)

            # Шаг 4: Создаём кандидатов
            candidates = await seed_candidates(session)

            # Шаг 4.1: Создаём опыт работы
            await seed_experience(session, candidates)

            # Шаг 4.2: Создаём навыки
            await seed_skills(session, candidates)

            # Шаг 5: Создаём applications и переходы
            applications = await seed_applications_and_move(session, candidates, vacancies, admin)

            # Шаг 6: Дополнительные данные
            await seed_extras(session, candidates)

            # Шаг 7: Pulse surveys
            await seed_surveys(session)

            # Шаг 8: Реальный скоринг (по флагу)
            await seed_real_scoring(session, candidates, applications, admin)

            # Коммитим все изменения
            await session.commit()

            logger.info("Demo seed completed successfully!")
            logger.info(f"Created: {len(clients)} clients, {len(vacancies)} vacancies, {len(candidates)} candidates, {len(applications)} applications")

        except Exception:
            await session.rollback()
            logger.exception("Demo seed failed")
            raise


if __name__ == "__main__":
    asyncio.run(main())