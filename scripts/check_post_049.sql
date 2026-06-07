-- Post-v0.4.9 проверка (read-only): индексы messages + oauth_states cleanup + кандидат с пустым ФИО.
\echo '--- индексы messages (ждём ix_messages_application_id и ix_messages_company_id) ---'
SELECT indexname FROM pg_indexes WHERE tablename = 'messages' ORDER BY indexname;

\echo '--- oauth_states (после cleanup ждём expired = 0) ---'
SELECT count(*) AS total, count(*) FILTER (WHERE expires_at < now()) AS expired FROM hh_oauth_states;

\echo '--- кандидат(ы) с пустым ФИО (пункт 4) ---'
SELECT c.id,
       '[' || c.first_name || ']' AS fn,
       '[' || c.last_name || ']' AS ln,
       c.email, c.phone, c.source, c.external_source,
       c.created_at, c.deleted_at,
       count(a.id) AS apps,
       string_agg(DISTINCT v.name || ' / ' || a.stage, '; ') AS funnel
FROM candidates c
LEFT JOIN applications a ON a.candidate_id = c.id
LEFT JOIN vacancies v ON v.id = a.vacancy_id
WHERE TRIM(COALESCE(c.first_name, '')) = '' OR TRIM(COALESCE(c.last_name, '')) = ''
GROUP BY c.id;
