#!/usr/bin/env bash
# Бэкап прод-БД Глафиры: pg_dump из контейнера `db` (docker-compose.prod.yml) → backups/glafira_*.sql
# Версионируется в репо → деплой привозит на VPS. Запускать на VPS (где есть Docker + контейнер db + .env).
#
# Использование:
#   ./scripts/backup_db.sh                 # дамп в ./backups/
#   BACKUP_DIR=/abs/path ./scripts/backup_db.sh
#
# Восстановление (⚠️ ПЕРЕЗАПИШЕТ текущую БД — дамп идёт с --clean --if-exists):
#   cat backups/glafira_<...>.sql | docker compose -f docker-compose.prod.yml exec -T \
#     -e PGPASSWORD="$POSTGRES_PASSWORD" db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
#
# Cron на VPS (ежедневно 03:30, под flock):
#   30 3 * * * /usr/bin/flock -n /tmp/glafira-backup.lock /var/www/glafira/scripts/backup_db.sh >> /var/www/glafira/backup.log 2>&1
#
# ⚠️ Дамп содержит ВСЕ данные, включая ПдН. Папка backups/ — в .gitignore. НЕ коммитить (репозиторий публичный).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

COMPOSE="docker compose -f docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"

# Креды БД из .env (POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB)
if [ -f "$ROOT_DIR/.env" ]; then
  set -a; . "$ROOT_DIR/.env"; set +a
fi
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-glafira}"
DB_PASS="${POSTGRES_PASSWORD:-}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
OUT="$BACKUP_DIR/glafira_${DB_NAME}_${TS}.sql"

echo "→ pg_dump БД '$DB_NAME' (пользователь '$DB_USER') → $OUT"

# -T: без TTY (нужно для редиректа). Дамп пишется на ХОСТ в backups/.
if ! $COMPOSE exec -T -e PGPASSWORD="$DB_PASS" db \
      pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner --no-privileges > "$OUT"; then
  echo "✗ ОШИБКА: pg_dump завершился с ошибкой — удаляю частичный файл $OUT" >&2
  rm -f "$OUT"
  exit 1
fi

if [ ! -s "$OUT" ]; then
  echo "✗ ОШИБКА: дамп пустой — удаляю $OUT" >&2
  rm -f "$OUT"
  exit 1
fi

SIZE="$(du -h "$OUT" | cut -f1)"
echo "✓ Готово: $OUT ($SIZE)"
