/**
 * Cohort retention matrix — выживаемость по месяцам найма.
 * Источник: turnover.py:_build_cohort_chart
 * Форма data: { cohorts: [{ month: string, sizes: [{ day: number, retained_pct: number | null }] }] }
 * Пусто без Employee → AnChart покажет empty-state.
 * Content-only: карточку даёт AnChart. CSS-идиом .cohort-* из эталона.
 */

import { Fragment } from 'react';

interface CohortChartProps {
  data: {
    cohorts: Array<{ month: string; sizes: Array<{ day: number; retained_pct: number | null }> }>;
  };
}

// Цвета данных (легитимные hex, не UI-токены): зелёный→красный по retention.
function colorFor(pct: number | null): string {
  if (pct === null || pct === undefined) return 'transparent';
  if (pct >= 90) return '#16A34A';
  if (pct >= 80) return '#59A861';
  if (pct >= 70) return '#E0A21A';
  if (pct >= 60) return '#E08A3C';
  return '#DC4646';
}

export function CohortChart({ data }: CohortChartProps) {
  const allDays = Array.from(new Set(data.cohorts.flatMap((c) => c.sizes.map((s) => s.day)))).sort((a, b) => a - b);

  const gridCols = `130px 80px repeat(${allDays.length}, 1fr)`;

  // total hired per cohort (sum не доступен с бека напрямую; показываем число дней-точек нет —
  // вместо «Нанято» показываем самую раннюю точку retention как 100%-базу нельзя; убираем колонку Нанято,
  // оставляем месяц + дни. Эталон имел «Нанято», но бек его не отдаёт → не выдумываем.)
  return (
    <div className="cohort-table">
      <div className="cohort-row cohort-head" style={{ gridTemplateColumns: gridCols }}>
        <div className="ch-cell ch-month">Месяц найма</div>
        <div className="ch-cell" />
        {allDays.map((day) => (
          <div key={day} className="ch-cell ch-pct">
            {day} дн.
          </div>
        ))}
      </div>
      {data.cohorts.map((cohort) => (
        <div key={cohort.month} className="cohort-row" style={{ gridTemplateColumns: gridCols }}>
          <div className="ch-cell ch-month">{cohort.month}</div>
          <div className="ch-cell" />
          {allDays.map((day) => {
            const size = cohort.sizes.find((s) => s.day === day);
            const pct = size?.retained_pct ?? null;
            const c = colorFor(pct);
            return (
              <Fragment key={`${cohort.month}-${day}`}>
                <div className="ch-cell ch-pct">
                  {pct === null ? (
                    <span className="ch-empty">—</span>
                  ) : (
                    <span className="ch-pill" style={{ background: `${c}22`, color: c, borderColor: `${c}44` }}>
                      {pct.toFixed(0)}%
                    </span>
                  )}
                </div>
              </Fragment>
            );
          })}
        </div>
      ))}
    </div>
  );
}
