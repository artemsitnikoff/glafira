# ТЗ-9. Аналитика (Экран 06) + детальные контракты отчётов

> **Кому:** FastAPI-агент (расчёты) И React-агент (графики).
> **Зависит от:** ТЗ-2 (§13 список эндпойнтов), ТЗ-3 (компоненты).
> **Источник UX:** прототипы `Analytics.jsx`, `AnalyticsReports.jsx`, `AnalyticsCharts.jsx` + описание Экрана 06.
> **Роут:** `/analytics?report={key}`.

Этот документ ДОБИВАЕТ контракты данных отчётов, которые в ТЗ-2 §13 были оставлены под детализацию (т.к. структура графиков завязана на визуализацию).

7 отчётов: overview, speed, funnel, sources, rejections, turnover, recruiters. Аналитика не редактируется — готовый набор с фильтрами.

---

## 0. Графики — общий подход (фронт)

Использовать **recharts** (есть в стеке артефактов и хорошо ложится на React). Графики: линии, бары (верт/гориз), funnel, box-plot, heatmap, pie, scatter, radar, survival-curve, cohort-heatmap, stacked-bar. Все — SVG, без 3D, без теней. Подписи осей серым 11px моно.

Числа в таблицах — `--font-mono`. Дельты: `+12%` зелёным, `−5%` красным. Цвета графиков — палитра воронки (STAGES) + нейтральные синий/зелёный/красный для бенчмарков. Фон страницы `--bg-1`, карточки `--bg-2`.

---

## 1. Структура раздела

```
┌─────────────────────────────────────────────────┐
│  Шапка: заголовок + глобальные фильтры           │
│  ───────────────────────────────────────         │
│  [Подменю отчётов — горизонтальные табы          │
│   ИЛИ в сайдбаре уже есть вертикальный список]    │
│  ───────────────────────────────────────         │
│  Контент отчёта: KPI-полоса · графики · таблицы   │
└─────────────────────────────────────────────────┘
```

Подменю отчётов уже живёт в сайдбаре (ТЗ-3 §7.5). На экране — горизонтальные табы дублируют выбор (опционально) ИЛИ только заголовок активного отчёта. Активный отчёт — из `?report=`.

---

## 2. Глобальные фильтры (шапка)

Над всеми отчётами, маппятся в query всех `/analytics/*`:
- **Период** — сегментный: `Неделя · Месяц · Квартал · Год · Произвольный` (произвольный → date-picker). query `period` / `date_from`+`date_to`.
- **Вакансия / Клиент / Рекрутёр** — мульти-селекты (опц., не во всех отчётах). query `vacancy_ids`, `recruiter_ids`.
- **Сравнение с прошлым периодом** — toggle (дефолт on). query `compare`.
- **Экспорт** — кнопка «Скачать XLSX / PNG» → `GET /analytics/export?report=X&format=xlsx`.

---

## 3. Общий конверт ответа (бек)

```python
class ChartData(BaseModel):
    type: str          # line|bar|hbar|funnel|boxplot|heatmap|pie|scatter|radar|survival|cohort|stacked
    title: str
    data: dict         # структура зависит от type (см. ниже)

class TableData(BaseModel):
    title: str
    columns: list[dict]    # [{key, label, type:"text|mono|delta|badge", sortable:bool}]
    rows: list[dict]

class AnalyticsResponse(BaseModel):
    report: str
    period: str
    kpis: list[KpiCard] | None
    charts: list[ChartData]
    tables: list[TableData]
```

```typescript
export interface ChartData { type: string; title: string; data: Record<string, unknown>; }
export interface TableColumn { key: string; label: string; type: "text"|"mono"|"delta"|"badge"; sortable: boolean; }
export interface TableData { title: string; columns: TableColumn[]; rows: Record<string, unknown>[]; }
export interface AnalyticsResponse {
  report: string; period: string; kpis: KpiCard[] | null;
  charts: ChartData[]; tables: TableData[];
}
```

---

## 4. Отчёт 1. Обзор (`/analytics/overview`)

**KPI-полоса (5):** Активных вакансий · Откликов за период · Закрыто вакансий · Средний срок закрытия (дни) · Стоимость найма (₽). Каждая — число + дельта vs прошлый.

**Графики:**
1. `line` «Динамика откликов» — `data: {points: [{date, value}]}`.
2. `stacked` «Карта активности воронки» — `data: {stages: [{stage_key, label, color, count}]}` (агрегат по всем вакансиям).
3. `hbar` «Top-5 вакансий по откликам» — `data: {items: [{label, value}]}`.

---

## 5. Отчёт 2. Скорость (`/analytics/speed`)

Где зависают кандидаты.

**Графики:**
1. `boxplot` по этапам — `data: {stages: [{stage_key, label, median, q1, q3, min, max, outliers:[...]}]}` (время в днях).
2. `heatmap` «вакансия × этап» — `data: {x_labels:[этапы], y_labels:[вакансии], cells:[{x,y,value_days}]}`.

**Таблицы:**
- «time-to-hire по вакансиям» — columns: вакансия, p50, p90, среднее (mono).
- Сравнение со среднерыночным (если бенч включён).

---

## 6. Отчёт 3. Воронка (`/analytics/funnel`)

**График:** `funnel` — `data: {stages: [{stage_key, label, color, count, conversion_from_prev_pct}], terminals: {hired:{n,pct}, rejected:{n,pct}}}`. Высота полосы ∝ количеству, под каждым — число + конверсия.

**Таблица:** конверсии в разрезах источника / вакансии / рекрутёра. columns динамические, rows с % конверсии по этапам.

---

## 7. Отчёт 4. Источники (`/analytics/sources`)

**Таблица «Эффективность источников»:**
columns: Источник · Откликов · Прошли скрининг (абс+%) · Дошли до интервью (абс+%) · Нанято (абс+%) · Стоимость (₽) · ROI. Сортировка по любой, цветовые маркеры на ROI.

**Графики:**
1. `stacked` «отклики→найм» по источникам.
2. `scatter` «качество (avg AI-скоринг) × объём» — `data: {points:[{label, x:quality, y:volume}]}`.

---

## 8. Отчёт 5. Отказы (`/analytics/rejections`)

2 колонки: **Отказы с нашей стороны** (компания+рекрутёры) и **Отказы кандидатов**.

**Графики:**
1. `pie` ×2 — `data: {our: [{reason, value}], candidate: [{reason, value}]}`.
2. `line` динамика отказов во времени.

**Таблица:** топ-вакансии по отказам.

Категории причин — из справочника `reject_reasons` (side=company / side=candidate).

---

## 9. Отчёт 6. Текучка / Адаптация (`/analytics/turnover`)

Читает данные из Пульса.

**Метрики:** доля «прошли испытательный» / «ушли в 30/60/90 дней». Средний срок жизни нового сотрудника по вакансии/руководителю/источнику.

**Графики:**
1. `cohort` heatmap — `data: {cohorts:[{month, sizes:[{day:30, retained_pct}, {day:60,...}, {day:90,...}]}]}`.
2. `survival` curve — `data: {points:[{day, retained_pct}]}`.

**Таблица:** топ-руководителей по текучке.

---

## 10. Отчёт 7. Рекрутёры (`/analytics/recruiters`)

**Таблица «Лидерборд»:**
columns: Рекрутёр (avatar+ФИО) · Активных вакансий · Откликов обработано · Скринингов · Интервью (назначено/проведено) · Найма · Среднее время до найма · Доля автономии Глафиры (%). Сортировка по любой. Топ-3 — золото/серебро/бронза бейджами.

**Графики:**
1. `bar` «найма по рекрутёрам».
2. `radar` «сравнение топ-3» — `data: {axes:[...], series:[{name, values:[...]}]}`.

---

## 11. Состояния

- Нет данных за период → illustration + «За выбранный период данных недостаточно. Попробуйте увеличить период».
- Загрузка отчёта → скелетоны на KPI и графиках.
- Экспорт → toast «Отчёт сохранён».

---

## 12. Связи
- KPI с Главной (01) ведут сюда с пресетом периода.
- Клик по вакансии в отчётах → воронка (03).
- «Текучка» использует данные Пульса (07).

---

## 13. ЧЕК-ЛИСТ ПРИЁМКИ

### Бек (расчёты)
- [ ] Все 7 эндпойнтов возвращают `AnalyticsResponse` с корректными kpis/charts/tables.
- [ ] Глобальные фильтры (period/vacancy_ids/recruiter_ids/compare) применяются ко всем отчётам.
- [ ] Произвольный период через date_from/date_to.
- [ ] Turnover читает данные из employees/surveys (Пульс).
- [ ] Sources считает конверсии по реальным applications.
- [ ] Export отдаёт XLSX (используется xlsx-скилл на стороне бека или библиотека openpyxl).

### Фронт (графики)
- [ ] Все типы графиков рендерятся (recharts): line, bar, hbar, funnel, boxplot, heatmap, pie, scatter, radar, cohort, survival, stacked.
- [ ] Глобальные фильтры в шапке, маппинг в query, рефетч при изменении.
- [ ] Переключение отчётов через сайдбар (analyticsReportId) + `?report=`.
- [ ] Числа в таблицах моно, дельты зелёным/красным, сортировка колонок.
- [ ] Топ-3 рекрутёров с бейджами.
- [ ] Графики SVG, без 3D/теней, подписи осей серым 11px моно.
- [ ] Состояния: нет данных / загрузка / экспорт-toast.
- [ ] Пиксель-перфект с Analytics.jsx / AnalyticsReports.jsx / AnalyticsCharts.jsx.
