-- ===============================================
-- АУДИТ БД ATS «Глафира» (READ-ONLY)
-- Команда запуска на VPS:
--   docker compose -f docker-compose.prod.yml exec -T db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} < audit.sql
-- ===============================================

\echo '===== 1. МИГРАЦИИ И СХЕМА ====='

-- CLI команды для выполнения в backend-контейнере:
\echo 'CLI команды (выполнять в backend-контейнере):'
\echo '  docker compose -f docker-compose.prod.yml run --rm backend alembic current'
\echo '  docker compose -f docker-compose.prod.yml run --rm backend alembic heads'
\echo '  docker compose -f docker-compose.prod.yml run --rm backend alembic history | head'
\echo '  docker compose -f docker-compose.prod.yml run --rm backend alembic check'

\echo 'Текущая версия миграции в БД:'
SELECT version_num AS current_migration_head FROM alembic_version;

\echo 'Ожидается: b7c8d9e0f1a2'

\echo ''
\echo '===== 2. ИНДЕКСЫ ====='

\echo 'Индексы на основных таблицах:'
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
    AND tablename IN ('applications', 'stage_history', 'candidates', 'messages', 'vacancies', 'employees', 'pulse_surveys')
ORDER BY tablename, indexname;

\echo ''
\echo '===== 3. ЦЕЛОСТНОСТЬ ДАННЫХ ====='

\echo 'Осиротевшие applications (без vacancy):'
SELECT COUNT(*) as orphaned_count FROM applications a
LEFT JOIN vacancies v ON a.vacancy_id = v.id
WHERE v.id IS NULL;

\echo 'Примеры осиротевших applications (первые 5):'
SELECT a.id, a.vacancy_id, a.candidate_id FROM applications a
LEFT JOIN vacancies v ON a.vacancy_id = v.id
WHERE v.id IS NULL
LIMIT 5;

\echo 'Осиротевшие applications (без candidate):'
SELECT COUNT(*) as orphaned_count FROM applications a
LEFT JOIN candidates c ON a.candidate_id = c.id
WHERE c.id IS NULL;

\echo 'Осиротевшие messages (без candidate):'
SELECT COUNT(*) as orphaned_count FROM messages m
LEFT JOIN candidates c ON m.candidate_id = c.id
WHERE c.id IS NULL;

\echo 'Осиротевшие messages (без application, где application_id заполнен):'
SELECT COUNT(*) as orphaned_count FROM messages m
LEFT JOIN applications a ON m.application_id = a.id
WHERE m.application_id IS NOT NULL AND a.id IS NULL;

\echo 'Осиротевшие stage_history (без application):'
SELECT COUNT(*) as orphaned_count FROM stage_history sh
LEFT JOIN applications a ON sh.application_id = a.id
WHERE a.id IS NULL;

\echo 'Осиротевшие employees (без candidate, для ATS-наймов):'
SELECT COUNT(*) as orphaned_count FROM employees e
LEFT JOIN candidates c ON e.candidate_id = c.id
WHERE e.candidate_id IS NOT NULL AND c.id IS NULL;

\echo 'Осиротевшие employees (без application, для ATS-наймов):'
SELECT COUNT(*) as orphaned_count FROM employees e
LEFT JOIN applications a ON e.application_id = a.id
WHERE e.application_id IS NOT NULL AND a.id IS NULL;

\echo 'Записи с NULL company_id по мультитенантным таблицам:'

\echo 'candidates без company_id:'
SELECT COUNT(*) as null_company_count FROM candidates WHERE company_id IS NULL;

\echo 'vacancies без company_id:'
SELECT COUNT(*) as null_company_count FROM vacancies WHERE company_id IS NULL;

\echo 'applications без company_id:'
SELECT COUNT(*) as null_company_count FROM applications WHERE company_id IS NULL;

\echo 'employees без company_id:'
SELECT COUNT(*) as null_company_count FROM employees WHERE company_id IS NULL;

\echo 'messages без company_id:'
SELECT COUNT(*) as null_company_count FROM messages WHERE company_id IS NULL;

\echo 'documents без company_id:'
SELECT COUNT(*) as null_company_count FROM documents WHERE company_id IS NULL;

\echo 'users без company_id:'
SELECT COUNT(*) as null_company_count FROM users WHERE company_id IS NULL;

\echo 'comments без company_id:'
SELECT COUNT(*) as null_company_count FROM comments WHERE company_id IS NULL;

\echo 'ai_evaluations без company_id:'
SELECT COUNT(*) as null_company_count FROM ai_evaluations WHERE company_id IS NULL;

\echo 'Application.stage: распределение по этапам:'
SELECT stage, COUNT(*) as count
FROM applications
GROUP BY stage
ORDER BY count DESC;

\echo 'Проверка осиротевших этапов (не в дефолтных и не в vacancy_stages):'
WITH default_stages AS (
    SELECT unnest(ARRAY['response', 'added', 'selected', 'recruiter', 'interview', 'manager', 'offer', 'hired', 'rejected']) AS stage_key
),
vacancy_stages_keys AS (
    SELECT DISTINCT stage_key FROM vacancy_stages
),
all_valid_stages AS (
    SELECT stage_key FROM default_stages
    UNION
    SELECT stage_key FROM vacancy_stages_keys
)
SELECT
    a.stage as orphaned_stage,
    COUNT(*) as applications_count
FROM applications a
LEFT JOIN all_valid_stages vs ON a.stage = vs.stage_key
WHERE vs.stage_key IS NULL
GROUP BY a.stage;

\echo 'Дубли applications (>1 НЕтерминального на пару candidate+vacancy):'
SELECT
    candidate_id,
    vacancy_id,
    COUNT(*) as duplicates_count
FROM applications
WHERE stage NOT IN ('hired', 'rejected')
GROUP BY candidate_id, vacancy_id
HAVING COUNT(*) > 1;

\echo ''
\echo '===== 4. СОСТОЯНИЕ ДАННЫХ ====='

\echo 'Общие счётчики:'
SELECT 'companies' as table_name, COUNT(*) as count FROM companies
UNION ALL
SELECT 'users', COUNT(*) FROM users
UNION ALL
SELECT 'clients', COUNT(*) FROM clients
UNION ALL
SELECT 'vacancies', COUNT(*) FROM vacancies
UNION ALL
SELECT 'candidates', COUNT(*) FROM candidates
UNION ALL
SELECT 'applications', COUNT(*) FROM applications
UNION ALL
SELECT 'employees', COUNT(*) FROM employees
UNION ALL
SELECT 'messages', COUNT(*) FROM messages
UNION ALL
SELECT 'pulse_surveys', COUNT(*) FROM pulse_surveys
UNION ALL
SELECT 'pulse_plan_items', COUNT(*) FROM pulse_plan_items
UNION ALL
SELECT 'documents', COUNT(*) FROM documents
UNION ALL
SELECT 'consents', COUNT(*) FROM consents
UNION ALL
SELECT 'verifications', COUNT(*) FROM verifications;

\echo 'Вакансии по статусу:'
SELECT status, COUNT(*) as count
FROM vacancies
GROUP BY status
ORDER BY count DESC;

\echo 'HH интеграция - candidates с source=hh:'
SELECT COUNT(*) as hh_candidates_count FROM candidates WHERE source = 'hh';

\echo 'HH интеграция - applications с hh_negotiation_id:'
SELECT COUNT(*) as hh_negotiation_count FROM applications WHERE hh_negotiation_id IS NOT NULL;

\echo 'HH интеграция - messages с external_id и channel=hh:'
SELECT COUNT(*) as hh_messages_count FROM messages WHERE external_id IS NOT NULL AND channel = 'hh';

\echo 'Demo vs реальные данные (по candidates.extra):'
SELECT
    CASE
        WHEN extra->>'demo' = 'true' THEN 'demo'
        ELSE 'real'
    END as data_type,
    COUNT(*) as count
FROM candidates
GROUP BY (extra->>'demo' = 'true')
ORDER BY count DESC;

\echo ''
\echo '===== 5. АНОМАЛИИ ====='

\echo 'Записи с created_at в будущем:'

\echo 'candidates с created_at > now():'
SELECT COUNT(*) as future_count FROM candidates WHERE created_at > now();

\echo 'applications с created_at > now():'
SELECT COUNT(*) as future_count FROM applications WHERE created_at > now();

\echo 'messages с created_at > now():'
SELECT COUNT(*) as future_count FROM messages WHERE created_at > now();

\echo 'employees с created_at > now():'
SELECT COUNT(*) as future_count FROM employees WHERE created_at > now();

\echo 'events с created_at > now():'
SELECT COUNT(*) as future_count FROM events WHERE created_at > now();

\echo 'Пустые обязательные поля:'

\echo 'candidates с пустым full_name (через свойство):'
SELECT COUNT(*) as empty_name_count FROM candidates
WHERE TRIM(first_name) = '' OR first_name IS NULL OR TRIM(last_name) = '' OR last_name IS NULL;

\echo 'vacancies с пустым name:'
SELECT COUNT(*) as empty_name_count FROM vacancies WHERE TRIM(name) = '' OR name IS NULL;

\echo 'HH negotiation без сообщений:'
SELECT COUNT(*) as negotiations_without_messages
FROM applications a
WHERE a.hh_negotiation_id IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM messages m
    WHERE m.application_id = a.id
);

\echo 'Примеры negotiations без сообщений (первые 5):'
SELECT a.id, a.hh_negotiation_id
FROM applications a
WHERE a.hh_negotiation_id IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM messages m
    WHERE m.application_id = a.id
)
LIMIT 5;

\echo 'HH токены (проверка шифрования):'
SELECT
    CASE
        WHEN access_token IS NULL THEN 'NULL'
        WHEN access_token LIKE 'gAAAAA%' THEN 'Fernet_encrypted'
        ELSE 'PLAIN_TEXT_WARNING'
    END as token_status,
    CASE
        WHEN access_token IS NOT NULL THEN
            substring(access_token from 1 for 12) || '... (length: ' || length(access_token) || ')'
        ELSE 'NULL'
    END as token_preview,
    COUNT(*) as count
FROM hh_integrations
GROUP BY
    (CASE
        WHEN access_token IS NULL THEN 'NULL'
        WHEN access_token LIKE 'gAAAAA%' THEN 'Fernet_encrypted'
        ELSE 'PLAIN_TEXT_WARNING'
    END),
    (CASE
        WHEN access_token IS NOT NULL THEN
            substring(access_token from 1 for 12) || '... (length: ' || length(access_token) || ')'
        ELSE 'NULL'
    END);

\echo 'OAuth state записи (висящие старые):'
SELECT
    COUNT(*) as total_oauth_states,
    COUNT(CASE WHEN created_at < now() - interval '1 hour' THEN 1 END) as old_states
FROM hh_oauth_states;

\echo 'Примеры старых OAuth state (>1 часа, первые 5):'
SELECT id, state, created_at, expires_at
FROM hh_oauth_states
WHERE created_at < now() - interval '1 hour'
ORDER BY created_at
LIMIT 5;

\echo ''
\echo '===== АУДИТ ЗАВЕРШЁН ====='