# ТЗ-3. Каркас фронта + Сайдбар (Экран 10)

> **Кому:** React-агент.
> **Зависит от:** ТЗ-0 (стек, токены), ТЗ-2 (типы, эндпойнты `/auth/me`, `/vacancies/sidebar`, `/pulse/alerts`).
> **Результат:** работающий каркас приложения — роутинг, layout, постоянный сайдбар, базовые переиспользуемые компоненты. На этот каркас монтируются экраны из ТЗ-4..10.
> **Источник UX:** прототип `Sidebar.jsx` из хэндоффа + описание Экрана 10.

---

## 0. Что строим в этом ТЗ

Каркас, который умеет:
1. Авторизовать пользователя (login → токен → редирект).
2. Показывать постоянный левый сайдбар (240px) на всех экранах, кроме login.
3. Роутить между всеми разделами.
4. Предоставлять базовые компоненты (Icon, Avatar, ScoreBadge, StageChip, кнопки), которые используют все экраны.
5. Подключённый axios-клиент + TanStack Query + Zustand-сторы.

Экраны-разделы пока — заглушки (`<div>Главная</div>`), их наполнят следующие ТЗ. **Сайдбар реализуем полностью.**

---

## 1. Точка входа и провайдеры (src/main.tsx)

```tsx
// QueryClientProvider (TanStack) + BrowserRouter + App
// QueryClient: defaultOptions { queries: { staleTime: 30_000, retry: 1 } }
```

Импортировать `styles/tokens.css` и `styles/global.css` в `main.tsx`.

### global.css (минимум)
- `* { box-sizing: border-box }`, сброс маргинов.
- `body { font-family: var(--font-sans); color: var(--fg-1); background: var(--bg-1) }`.
- Подключить шрифты Inter / Inter Tight (Google Fonts или локально).
- Утилита `.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums }`.

---

## 2. API-клиент (src/api/client.ts)

```typescript
import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL, // /api/v1
  withCredentials: true,                       // для refresh-cookie
});

// REQUEST interceptor: подставляет Bearer из authStore
// RESPONSE interceptor:
//   - 401 → попытка /auth/refresh → повтор; при провале → logout + redirect /login
//   - любую ошибку маппит в ApiError (тип из types.ts)
```

Все доменные хуки (`src/api/hooks/*`) используют `api` + TanStack Query. Пример скелета — `useSidebar.ts`:
```typescript
export const useSidebar = () =>
  useQuery({ queryKey: ["vacancies", "sidebar"], queryFn: () =>
    api.get<VacancySidebar>("/vacancies/sidebar").then(r => r.data) });
```

---

## 3. Сторы Zustand (src/store/)

### authStore.ts
```typescript
interface AuthState {
  accessToken: string | null;
  user: UserMe | null;
  setToken: (t: string) => void;
  setUser: (u: UserMe) => void;
  logout: () => void;
}
```
Токен держим в памяти (не localStorage — ТЗ-0 запрещает чувствительное в сторадже для безопасности; refresh-cookie восстанавливает сессию). При старте приложения — попытка `/auth/refresh` + `/auth/me`.

### uiStore.ts
```typescript
interface UiState {
  vacanciesOpen: boolean;      // раскрытие подменю "Вакансии"
  analyticsOpen: boolean;      // раскрытие подменю "Аналитика"
  analyticsReportId: string;   // активный отчёт
  vacancySearch: string;       // поиск в подменю вакансий
  toggleVacancies: () => void;
  toggleAnalytics: () => void;
  // ...
}
```

---

## 4. Роутинг (src/App.tsx)

React Router v6. Структура:

```
/login                          → LoginScreen (без layout)
/  (AppLayout, защищён)
  ├ /                           → redirect /home
  ├ /home                       → Home (Экран 01)
  ├ /vacancies                  → VacanciesEmpty (Экран 02 empty state)
  ├ /vacancies/archive          → VacanciesArchive
  ├ /vacancies/new              → NewVacancy (форма создания)
  ├ /vacancies/:id              → Funnel (Экран 03 — воронка)
  ├ /vacancies/:id/edit         → NewVacancy (editMode)
  ├ /vacancies/:id/candidates/:cid → Funnel + открытая карточка (Экран 04 в контексте)
  ├ /candidates                 → Candidates (Экран 05 — общая база)
  ├ /candidates/:id             → CandidateDetail (Экран 04 на весь экран)
  ├ /analytics                  → Analytics (Экран 06), report по query ?report=overview
  ├ /pulse                      → Pulse (Экран 07)
  ├ /pulse/:id                  → PulseDetail (Экран 08 — overlay/панель)
  └ /settings                   → Settings (Экран 09), таб по query ?tab=profile
```

**Защита роутов:** `AppLayout` проверяет `authStore.user`. Если нет — пытается восстановить сессию; при провале → `Navigate to="/login"`.

В этом ТЗ все экраны (кроме Login и Sidebar) — заглушки-плейсхолдеры. Реализуются в следующих ТЗ.

---

## 5. Layout (src/components/AppLayout.tsx)

```
┌──────────┬──────────────────────────────────┐
│ Sidebar  │  <Outlet />  (контент экрана)     │
│ 240px    │  flex: 1, overflow-y: auto         │
│ fixed    │                                    │
└──────────┴──────────────────────────────────┘
```

- Grid/flex: сайдбар `width: var(--sidebar-width)` фиксирован, контент занимает остаток.
- Сайдбар `position: sticky; height: 100vh; top: 0`.
- Контент скроллится независимо.
- Десктоп-first: ниже 1280px ничего не адаптируем (ТЗ-0 / Экран 10 §10).

---

## 6. Базовые компоненты (src/components/)

Эти компоненты используют ВСЕ экраны. Реализовать в этом ТЗ.

### 6.1 Icon.tsx
Набор SVG-иконок (outline-стиль). Минимальный набор из Экрана 10 §9 + общие:
`home, briefcase, users, chart, heart, settings, plus, search, archive, chevD (chevron-down), chevR (chevron-right), bell, x, check, phone, paperPlane, dots (⋯), arrowRight (→), arrowLeft (←), filter, sort`.

```tsx
interface IconProps { name: IconName; size?: number; className?: string; }
// <Icon name="home" size={20} />
```
Точные пути SVG — взять из прототипа `Sidebar.jsx`/общего набора в хэндоффе. Если в прототипе нет — использовать lucide-подобные аккуратные outline-иконки (stroke 1.5).

### 6.2 Avatar.tsx
Инициалы в цветном круге. Цвет — детерминированный хеш от ФИО.
```tsx
interface AvatarProps { name: string; src?: string | null; size?: number; }
// "Анна Седова" → "АС", фон из палитры по хешу
```
Размеры: 22 (мессенджеры/мелкие), 28 (user-card), 64 (карточки детально).

### 6.3 ScoreBadge.tsx
AI-скоринг. Цвет по градации (токены `--score-*`).
```tsx
interface ScoreBadgeProps {
  score: number | null;          // null → серый "—" + тултип "Скоринг ещё не посчитан"
  size?: "sm" | "md" | "lg" | "xl";
}
// ≥80 green, 50–79 yellow, <50 red
```
На hover (lg/xl) — тултип «Почему такая оценка» (текст приходит позже из evaluation; в этом ТЗ — заглушка).

### 6.4 StageChip.tsx
Пилюля этапа воронки с цветной точкой.
```tsx
interface StageChipProps {
  stage: StageKey;
  label?: string;        // если не задан — берётся из STAGES-константы
  variant?: "chip" | "dot"; // полная пилюля или только точка+текст
}
```
Цвет точки — из локальной константы `STAGES` (зеркало ТЗ-1 §6), храним в `src/lib/stages.ts`:
```typescript
export const STAGES: Record<StageKey, {label: string; color: string; terminal: boolean}> = {
  response:  {label: "Отклик", color: "var(--stage-response)", terminal: false},
  added:     {label: "Добавлен", color: "var(--stage-added)", terminal: false},
  selected:  {label: "Отобран", color: "var(--stage-selected)", terminal: false},
  recruiter: {label: "Контакт с рекрутером", color: "var(--stage-recruiter)", terminal: false},
  interview: {label: "Интервью", color: "var(--stage-interview)", terminal: false},
  manager:   {label: "Контакт с менеджером", color: "var(--stage-manager)", terminal: false},
  offer:     {label: "Оффер", color: "var(--stage-offer)", terminal: false},
  hired:     {label: "Нанят", color: "var(--stage-hired)", terminal: true},
  rejected:  {label: "Отказ", color: "var(--stage-rejected)", terminal: true},
};
```

### 6.5 Button.tsx
Варианты из дизайна: `primary`, `secondary`, `success` (btn-success — зелёная «Перевести»), `ghost`, `icon` (icon-btn). Размеры `sm`/`md`. Состояние `disabled`.

### 6.6 MessIconRound.tsx
Круглая иконка мессенджера фирменного цвета.
```tsx
interface MessIconRoundProps { channel: "telegram"|"whatsapp"|"max"|"viber"; size?: number; }
// цвета из токенов --src-*; размер 18 (таблица) / 22 (карточка)
```

### 6.7 Прочие мелкие
`Tooltip`, `Badge` (счётчики/пилюли), `EmptyState` (иллюстрация + заголовок + текст + CTA), `Skeleton` (для лоадеров). Реализовать базово.

---

## 7. САЙДБАР (src/components/Sidebar.tsx) — главная цель ТЗ

Полная реализация по Экрану 10. Источник пиксель-перфекта — прототип `Sidebar.jsx`.

### 7.1 Структура (сверху вниз)

```
┌─────────────────────────────┐
│ BRAND: [👩🏻] Глафира   💃    │  brand-mark + wordmark + brand-dancer, клик → /home
├─────────────────────────────┤
│ NAV:                        │
│  🏠 Главная                 │  → /home
│  💼 Вакансии          ▾    │  → раскрытие sub-block (vacanciesOpen)
│     [+ Новая вакансия]      │  → /vacancies/new
│     [🔍 Поиск…]             │  фильтрует список ниже
│     • Frontend …    12 +3   │  → /vacancies/:id
│     • DevOps …      8       │
│     ── 📦 Архив (47)        │  → /vacancies/archive
│  👥 Кандидаты               │  → /candidates
│  📊 Аналитика         ▾    │  → раскрытие списка отчётов (analyticsOpen)
│     • Обзор                 │  → /analytics?report=overview
│     • Скорость              │
│     • …                     │
│  💗 Пульс-Онбординг     [2] │  → /pulse, бейдж = число алертов
│  ⚙ Настройки                │  → /settings
├─────────────────────────────┤
│ (растяжка flex:1)           │
├─────────────────────────────┤
│ USER-CARD: [АС] Анна Седова │  аватар + имя + роль + 🔔(pip)
│            Старший рекрутер  │
└─────────────────────────────┘
```

### 7.2 Данные
- **Список вакансий + архив:** `useSidebar()` → `GET /vacancies/sidebar` (`VacancySidebar`).
- **Алерты Пульса (бейдж):** `GET /pulse/alerts` → число недизмиссленных. Polling `refetchInterval: 30000`.
- **Юзер:** `authStore.user`.
- **Отчёты аналитики:** статический список (зеркало `AN_REPORTS`): Обзор, Скорость, Воронка, Источники, Отказы, Текучка, Рекрутёры (с ключами `overview/speed/funnel/sources/rejections/turnover/recruiters` и иконками 📋⏱🔻🌐❌📉👤).

### 7.3 Поведение пунктов навигации
- **Высота пункта 40px**, иконка 20px слева + лейбл (14px, средний вес).
- **Активный пункт:** фон `--bg-active` + левая полоска 4px `--brand-accent`. Активность определяется по текущему роуту (`useLocation`).
- **Hover:** фон `--bg-3`.
- **Бейдж справа** (Пульс) — мелкая плашка `nav-row-pip`; красный для алертов.

### 7.4 Раскрытие «Вакансии» (vacanciesOpen в uiStore)
- Клик по пункту «Вакансии» или по шеврону → toggle `vacanciesOpen`.
- Шеврон анимируется ▸→▾ (класс `.open`, CSS-transition transform).
- Если активный раздел НЕ вакансии → клик делает раздел активным, открывает блок, навигирует на `/vacancies` (empty state) ИЛИ первую вакансию/архив по тыку `defaultSelected` (в MVP: `/vacancies` empty).
- Если УЖЕ в вакансиях → повторный клик только сворачивает/разворачивает блок, контент справа не меняется.

**Содержимое sub-block:**
- Кнопка «+ Новая вакансия» (`sub-add`) → navigate `/vacancies/new`.
- Поиск (`vacancySearch` в uiStore) — фильтрует список по `name.toLowerCase().includes(query)` на клиенте.
- Список: каждый item — `unread-dot` (если `has_unread`) + название + `sub-count` (моно, `count`) + `sub-new` (пилюля `+{new_count}` если >0). Активная вакансия (совпадает с `:id` в роуте) — фон `--bg-active` + левая полоска.
- Если поиск пуст → empty «Ничего не найдено».
- Разделитель.
- Строка «Архив» (иконка archive + `archived_count`) → navigate `/vacancies/archive`.

### 7.5 Раскрытие «Аналитика» (analyticsOpen)
- Аналогично: toggle, шеврон, плоский список из 7 отчётов.
- Каждая строка: иконка отчёта + лейбл. Активный (`analyticsReportId`) подсвечен.
- Клик → set `analyticsReportId` + navigate `/analytics?report={key}`.

### 7.6 User-card (низ, `user-card-wide`)
- Avatar 28px (инициалы из `user.full_name`).
- Имя + роль/`position` двумя строками.
- Иконка-кнопка `bell` справа с `pip` (индикатор непрочитанных — в MVP статичный/заглушка).
- Поповер профиля — НЕ реализуем (Экран 10 §7 «нет в текущей реализации»).

### 7.7 Дизайн-токены сайдбара
- Ширина `var(--sidebar-width)` (240px), фон `--bg-2`, правая граница 1px `--border-1`.
- Лейблы 14px `--font-sans`, средний вес.
- Счётчики моно `--font-mono` ~12px серым `--fg-3`.
- Бренд-полоска активного — `--brand-accent`.

---

## 8. LoginScreen (src/screens/Login.tsx)

Простой экран входа (в дизайне отдельного описания нет — делаем минималистично в брендовом стиле):
- Брендовая шапка (👩🏻 Глафира 💃) по центру.
- Поля email + пароль, кнопка «Войти».
- `useMutation` → `POST /auth/login` → сохранить токен + `/auth/me` → navigate `/home`.
- Ошибка → показать сообщение из `ApiError.error.message`.

---

## 9. Состояния и заглушки

- Пока бек не готов — хуки могут возвращать мок-данные (флаг `VITE_USE_MOCKS`), но структура моков ОБЯЗАНА совпадать с TS-типами из ТЗ-2.
- Лоадеры — компонент `Skeleton`.
- Сайдбар при загрузке списка вакансий — скелетоны строк.

---

## 10. Что НЕ в этом ТЗ
- Наполнение экранов (Home, Funnel, и т.д.) — следующие ТЗ.
- Свёрнутый/мобильный режим сайдбара (десктоп-first).
- Командная палитра, поповер профиля, лента уведомлений.

---

## 11. ЧЕК-ЛИСТ ПРИЁМКИ (ревьювер)

### Каркас
- [ ] `npm run dev` поднимает приложение, `npm run build` собирается без TS-ошибок (strict).
- [ ] tokens.css подключён, переменные применяются; шрифты Inter/Inter Tight грузятся.
- [ ] axios-клиент: 401 триггерит refresh, при провале — редирект на /login.
- [ ] TanStack Query и Zustand подключены, провайдеры на месте.

### Роутинг и layout
- [ ] Все роуты из §4 объявлены (экраны-заглушки допустимы).
- [ ] Неавторизованный пользователь редиректится на /login.
- [ ] Сайдбар виден на всех защищённых роутах, контент скроллится независимо, сайдбар sticky 240px.

### Базовые компоненты
- [ ] Icon рендерит все имена из §6.1.
- [ ] Avatar даёт стабильный цвет по ФИО, корректные инициалы (кириллица).
- [ ] ScoreBadge: ≥80 зелёный, 50–79 жёлтый, <50 красный, null → серый «—».
- [ ] StageChip берёт цвета из STAGES-константы, совпадает с токенами.
- [ ] MessIconRound — правильные фирменные цвета каналов.

### Сайдбар (главное)
- [ ] Бренд-шапка с 👩🏻 + «Глафира» + 💃, клик → /home.
- [ ] Активный пункт подсвечен по текущему роуту (фон + левая полоска).
- [ ] «Вакансии» раскрывается inline, шеврон анимируется, список из `/vacancies/sidebar`.
- [ ] Поиск в подменю фильтрует список в реальном времени на клиенте.
- [ ] Каждая вакансия: unread-dot, count (моно), пилюля +N для новых.
- [ ] Активная вакансия подсвечена при совпадении с :id роута.
- [ ] Строка «Архив» с числом → /vacancies/archive.
- [ ] «Аналитика» раскрывается, 7 отчётов, активный подсвечен, клик меняет роут + analyticsReportId.
- [ ] Бейдж на «Пульс» = число активных алертов из `/pulse/alerts`, polling работает.
- [ ] User-card: аватар 28px, имя + роль, колокольчик с pip.

### Login
- [ ] Вход работает, токен сохраняется, редирект на /home.
- [ ] Ошибка входа показывает message из ApiError.

### Пиксель-перфект
- [ ] Сайдбар визуально соответствует прототипу Sidebar.jsx (отступы, цвета, шрифты, высоты пунктов).
