#!/usr/bin/env bash
# ПОЛНЫЙ бэкап Глафиры («бекап всего»): прод-БД + .env (секреты) + том backend_storage.
# Код приложения НЕ бэкапим — он в git (GitHub). Запускать на VPS (Docker + контейнер db + .env).
#
# Использование:
#   ./scripts/backup_all.sh                 # всё в ./backups/<timestamp>/
#   BACKUP_DIR=/abs/path ./scripts/backup_all.sh
#
# Что кладёт в backups/<ts>/:
#   db_<DB>.sql.gz      — дамp БД (pg_dump --clean --if-exists, gzip)
#   env.bak            — копия .env (секреты! chmod 600)
#   storage.tgz        — содержимое тома backend_storage (/app/storage: логи, файлы)
#   MANIFEST.txt       — что внутри + как восстановить
#
# Восстановление БД (⚠️ ПЕРЕЗАПИШЕТ текущую — дамп с --clean):
#   gunzip -c backups/<ts>/db_<DB>.sql.gz | docker compose -f docker-compose.prod.yml exec -T \
#     -e PGPASSWORD="$POSTGRES_PASSWORD" db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
# Восстановление storage:  docker run --rm -v <vol>:/data -v "$PWD/backups/<ts>":/b alpine \
#     sh -c 'cd /data && tar xzf /b/storage.tgz'
#
# ⚠️ Бэкап содержит ВСЕ данные (ПдН) и СЕКРЕТЫ (.env). Папка backups/ — в .gitignore. НЕ коммитить
#    (репозиторий публичный). Хранить в защищённом месте; по возможности — копировать с VPS вовне.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

COMPOSE="docker compose -f docker-compose.prod.yml"
TS="$(date +%Y-%m-%d_%H%M%S)"
DEST="${BACKUP_DIR:-$ROOT_DIR/backups}/$TS"
mkdir -p "$DEST"

# Креды БД из .env
if [ -f "$ROOT_DIR/.env" ]; then
  set -a; . "$ROOT_DIR/.env"; set +a
fi
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-glafira}"
DB_PASS="${POSTGRES_PASSWORD:-}"

echo "==> ПОЛНЫЙ бэкап Глафиры → $DEST"

# --- 1. База данных (pg_dump → gzip на хост) ---
DB_OUT="$DEST/db_${DB_NAME}.sql.gz"
echo "  [1/3] pg_dump БД '$DB_NAME'…"
if ! $COMPOSE exec -T -e PGPASSWORD="$DB_PASS" db \
      pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner --no-privileges \
      | gzip > "$DB_OUT"; then
  echo "  ✗ pg_dump упал — удаляю частичный файл" >&2; rm -f "$DB_OUT"; exit 1
fi
[ -s "$DB_OUT" ] || { echo "  ✗ дамп БД пустой" >&2; rm -f "$DB_OUT"; exit 1; }
echo "      ✓ $(du -h "$DB_OUT" | cut -f1)  $DB_OUT"

# --- 2. .env (секреты) ---
if [ -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env" "$DEST/env.bak"
  chmod 600 "$DEST/env.bak"
  echo "  [2/3] ✓ .env → $DEST/env.bak (chmod 600)"
else
  echo "  [2/3] ⚠ .env не найден — пропуск" >&2
fi

# --- 3. Том backend_storage (логи/файлы /app/storage) ---
STORAGE_VOL="$(docker volume ls --format '{{.Name}}' 2>/dev/null | grep -E 'backend_storage$' | head -1 || true)"
if [ -n "$STORAGE_VOL" ]; then
  echo "  [3/3] архив тома '$STORAGE_VOL'…"
  docker run --rm -v "$STORAGE_VOL":/data:ro -v "$DEST":/backup alpine \
    tar czf /backup/storage.tgz -C /data . \
    && echo "      ✓ $(du -h "$DEST/storage.tgz" | cut -f1)  $DEST/storage.tgz" \
    || echo "      ⚠ не удалось архивировать том (не критично)" >&2
else
  echo "  [3/3] ⚠ том backend_storage не найден — пропуск" >&2
fi

# --- Манифест ---
{
  echo "Глафира — полный бэкап $TS"
  echo "git HEAD: $(git rev-parse --short HEAD 2>/dev/null || echo n/a)"
  echo "Состав:"
  ls -lh "$DEST"
  echo ""
  echo "Восстановление БД (ПЕРЕЗАПИШЕТ текущую):"
  echo "  gunzip -c $DEST/db_${DB_NAME}.sql.gz | $COMPOSE exec -T -e PGPASSWORD=\"\$POSTGRES_PASSWORD\" db psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\""
} > "$DEST/MANIFEST.txt"

echo "==> ГОТОВО. Полный бэкап: $DEST"
echo "    Итого: $(du -sh "$DEST" | cut -f1). ⚠ Содержит ПдН и секреты — храните безопасно, скопируйте с VPS вовне."
