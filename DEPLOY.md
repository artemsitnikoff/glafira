# Деплой ATS «Глафира Рекрутёр» на VPS

> **Конфигурация:** домен `ats.mydomain.ru` (замени на свой), HTTPS через certbot, Docker (postgres+бек+фронт в compose), nginx — общий на VPS (НЕ ставим с нуля, дорабатываем существующий).
> **Важно:** гайд НЕ трогает другие сервисы на VPS. Все порты ATS слушают только localhost, наружу выходит через твой общий nginx.

---

## 0. Перед началом (на маке)

Убедись, что в репозитории НЕТ `.env` (только `.env.example`):
```bash
git ls-files | grep -E '(^|/)\.env$'   # должно быть пусто
grep -n "\.env$" .gitignore            # .env должен быть в .gitignore
```
Если `.env` отслеживается — убери (`git rm --cached .env`) и закоммить до переноса.

---

## 1. Секреты — сгенерировать НА VPS (не на маке, не в git)

На VPS, в папке проекта, сгенерируй три значения:

```bash
# JWT_SECRET (подпись токенов)
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# FERNET_KEY (шифрование токенов интеграций hh/Avito)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**OPENROUTER_API_KEY:**
1. Зайди на openrouter.ai → дашборд ключей.
2. **Отзови (revoke) тот ключ, что был в локальном `.env`** — он мог светиться в истории разработки.
3. Создай новый ключ.
4. Положи новый ТОЛЬКО в `.env` на VPS (шаг 2). Никогда — в git.

---

## 2. `.env` на VPS

В корне проекта (`/var/www/glafira/` или твой путь) скопируй шаблон и заполни реальными значениями:

```bash
cp .env.example .env
nano .env
```

Полный список переменных (имена сверены с `backend/app/config.py`, проект читает их через `pydantic-settings`):

```bash
# --- БД (postgres) ---
# Эти три читает docker-compose для инициализации postgres-контейнера:
POSTGRES_USER=glafira
POSTGRES_PASSWORD=<придумай надёжный, 24+ символов>
POSTGRES_DB=glafira
# DATABASE_URL читает бек. В compose host=db (имя сервиса), порт 5432.
DATABASE_URL=postgresql+asyncpg://glafira:<тот же пароль>@db:5432/glafira

# --- Аутентификация ---
JWT_SECRET=<сгенерированный token_urlsafe(64) из шага 1>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=14
DEFAULT_COMPANY_ID=00000000-0000-0000-0000-000000000001

# --- AI (Глафира через OpenRouter) ---
OPENROUTER_API_KEY=<новый ключ с openrouter.ai>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
GLAFIRA_MODEL=anthropic/claude-sonnet-4-6
# Только mock на проде (real → 501 пока интеграция с госреестрами не сделана)
GLAFIRA_VERIFY_MODE=mock
# legacy, не используется — оставь пустым:
ANTHROPIC_API_KEY=

# --- Источники (заполнишь позже в UI Настройки → Интеграции, можно оставить пустыми) ---
HH_CLIENT_ID=
HH_CLIENT_SECRET=
AVITO_CLIENT_ID=
AVITO_CLIENT_SECRET=

# --- Шифрование токенов интеграций ---
FERNET_KEY=<сгенерированный Fernet ключ из шага 1>

# --- Деплой ---
# Список origin'ов фронта через запятую (без слеша в конце!)
CORS_ORIGINS=https://ats.mydomain.ru
# True если HTTPS поднят (Secure-cookie). Если http (тестово) — оставь False.
SESSION_COOKIE_SECURE=True

# --- Frontend (читает Vite на этапе build) ---
VITE_API_BASE_URL=https://ats.mydomain.ru/api/v1
```

> `VITE_API_BASE_URL` зашивается в статику при сборке фронта. Если потом поменяешь домен — нужно пересобрать фронт.

---

## 3. docker-compose для прода

> Если у тебя уже есть `docker-compose.yml` для локалки — сделай отдельный `docker-compose.prod.yml`, чтобы не путать. Все порты — на `127.0.0.1` (наружу только через nginx).

Ориентир (приведи под свою реальную структуру):

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - glafira_pgdata:/var/lib/postgresql/data
    # порт наружу НЕ публикуем — доступ только внутри compose-сети
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      retries: 10

  backend:
    build: ./backend
    restart: unless-stopped
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "127.0.0.1:8000:8000"   # только localhost; nginx проксирует
    # команда запуска — uvicorn (приведи под свой Dockerfile)

  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_BASE_URL: https://ats.mydomain.ru/api/v1
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:80"     # статика фронта; nginx проксирует

volumes:
  glafira_pgdata:
```

> Порты `8000`/`8080` — пример; выбери свободные на VPS (проверь `ss -tlnp`, чтобы не пересеклись с другими сервисами). Привязка к `127.0.0.1` обязательна — наружу выходим только через общий nginx.

---

## 4. Запуск БД + миграции + seed (порядок важен)

```bash
# 1. Поднять только БД
docker compose -f docker-compose.prod.yml up -d db

# 2. Дождаться healthy
docker compose -f docker-compose.prod.yml ps

# 3. Прогнать миграции (внутри backend-контейнера или одноразовым run)
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# 4. Seed (компания, admin Анна Седова, справочник причин, glafira_settings)
docker compose -f docker-compose.prod.yml run --rm backend python -m app.seed
#   ^ имя seed-команды сверь с фактическим в проекте

# 5. Поднять всё
docker compose -f docker-compose.prod.yml up -d
```

Проверка, что бек жив (изнутри VPS):
```bash
curl -s http://127.0.0.1:8000/api/v1/health  # или любой публичный GET; ожидаем 200
```

---

## 5. Ночной крон для AI-сводок

AI-сводки сотрудников генерятся ночным батчем. Добавь в системный cron на VPS:

```bash
crontab -e
```
Строка (каждую ночь в 3:00):
```
0 3 * * * cd /path/to/project && docker compose -f docker-compose.prod.yml run --rm backend python -m app.jobs.regenerate_employee_summaries >> /var/log/glafira_summaries.log 2>&1
```
> Путь к проекту и имя compose-файла подставь свои. Команда идемпотентна — повторный запуск безопасен.

---

## 6. HTTPS + nginx (ОБЩИЙ nginx — отдельный шаг)

> **Здесь НЕ ставим nginx с нуля и НЕ трогаем твои существующие конфиги.** Добавляем ОДИН server-блок для `ats.mydomain.ru` к существующему nginx.

Порядок:

1. **DNS:** убедись, что `ats.mydomain.ru` A-записью указывает на IP VPS.

2. **Покажи мне свой текущий nginx-конфиг** — выполни и пришли вывод:
   ```bash
   nginx -T 2>/dev/null | head -200          # сводка всех конфигов
   ls /etc/nginx/sites-available/ /etc/nginx/sites-enabled/ 2>/dev/null
   ```
   По нему я подгоню server-блок под твою структуру (sites-available/enabled vs conf.d, как у тебя оформлены другие сайты, нет ли конфликтов).

3. **Черновик server-блока** (доработаю под твой конфиг после шага 2):
   ```nginx
   server {
       server_name ats.mydomain.ru;

       # фронт (статика)
       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       # API (бек)
       location /api/ {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       listen 80;
   }
   ```

4. **HTTPS через certbot** (после того как HTTP-блок работает):
   ```bash
   sudo certbot --nginx -d ats.mydomain.ru
   ```
   Certbot сам допишет `listen 443 ssl`, сертификаты и редирект 80→443 в этот блок, не трогая остальные сайты.

5. **Перезагрузка nginx** (с проверкой, чтобы не уронить другие сайты):
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```

> `X-Forwarded-Proto $scheme` важен: бек по нему понимает, что запрос пришёл по HTTPS, и корректно ставит Secure-cookie.

---

## 7. Pre-flight чек-лист (перед первым заходом в браузер)

- [ ] `.env` на VPS заполнен, реальные секреты, НЕ в git.
- [ ] Старый OPENROUTER_API_KEY отозван, новый в `.env`.
- [ ] `GLAFIRA_VERIFY_MODE=mock`, `SESSION_COOKIE_SECURE=True`, `CORS_ORIGINS=https://ats.mydomain.ru`.
- [ ] CORS в main.py читает из env (не хардкод localhost).
- [ ] `VITE_API_BASE_URL=https://ats.mydomain.ru/api/v1` (фронт пересобран с этим).
- [ ] Порты бек/фронт привязаны к `127.0.0.1`, не пересекаются с другими сервисами.
- [ ] `alembic upgrade head` прошёл, seed выполнен.
- [ ] DNS `ats.mydomain.ru` → IP VPS.
- [ ] nginx server-блок добавлен, `nginx -t` ок, certbot выдал сертификат.
- [ ] Другие сайты на VPS работают (reload nginx их не задел).

---

## 8. Smoke в браузере (после деплоя — отдельный чек-лист)

Когда всё поднято и `https://ats.mydomain.ru` открывается — пройди smoke-чек-лист по всем 10 экранам (дам отдельно). Первый заход: логин под seed-юзером (Анна Седова), проверка что данные грузятся через реальный API, что нет белых экранов и CORS-ошибок в консоли браузера.

---

## 9. Известные пост-деплой долги (не блокеры)

- Биллинг `is_demo` баннер в UI (поле приходит, не показывается).
- Реальная верификация по госреестрам (сейчас mock; `real` → 501 — не включать без интеграции).
- docx-парсинг резюме (сейчас pdf/txt).
- Реальные клиенты hh/Avito (config расшифровывается Fernet; ключи добавишь в Настройках → Интеграции).
