#!/usr/bin/env bash
# Cron-обёртка: очистка протухших hh_oauth_states (app/jobs/cleanup_oauth_states.py).
# Версионируется в репо → деплой привозит на VPS. Вызывается из crontab под flock.
#
# Добавить в crontab на VPS (ОДНА строка, раз в сутки в 04:00):
#   0 4 * * * /usr/bin/flock -n /tmp/glafira-oauth-cleanup.lock /var/www/glafira/scripts/cron_oauth_cleanup.sh >> /var/www/glafira/oauth-cleanup.log 2>&1
set -euo pipefail
cd /var/www/glafira
docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.cleanup_oauth_states
