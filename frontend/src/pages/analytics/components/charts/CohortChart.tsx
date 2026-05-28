/**
 * Cohort matrix chart для turnover-отчёта.
 * Источник: backend/app/services/analytics/turnover.py
 * Форма data: { cohorts: [{ month: string, sizes: [{ day: number, retained_pct: number }] }] }
 */

import React from 'react';

interface CohortData {
  cohorts: Array<{
    month: string;
    sizes: Array<{ day: number; retained_pct: number }>;
  }>;
}

interface CohortChartProps {
  title: string;
  data: CohortData;
  onDataClick?: (data: any) => void;
}

export function CohortChart({ title, data, onDataClick }: CohortChartProps) {
  if (!data?.cohorts || data.cohorts.length === 0) {
    return (
      <div className="analytics-chart-card">
        <div className="analytics-chart-header">
          <h3 className="analytics-chart-title">{title}</h3>
        </div>
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--fg-3)' }}>
          Нет данных для отображения
        </div>
      </div>
    );
  }

  // Get all unique days across all cohorts
  const allDays = Array.from(new Set(
    data.cohorts.flatMap(cohort => cohort.sizes.map(size => size.day))
  )).sort((a, b) => a - b);

  // Color scale function
  const getColor = (retainedPct: number | null): string => {
    if (retainedPct === null || retainedPct === undefined) {
      return 'var(--bg-3)';
    }

    // Color scale: red (low retention) to green (high retention)
    if (retainedPct >= 90) {
      return '#16A34A'; // Green
    } else if (retainedPct >= 80) {
      return '#59A861'; // Light green
    } else if (retainedPct >= 70) {
      return '#E0A21A'; // Yellow
    } else if (retainedPct >= 60) {
      return '#E08A3C'; // Orange
    } else {
      return '#DC4646'; // Red
    }
  };

  const getTextColor = (retainedPct: number | null): string => {
    if (retainedPct === null || retainedPct === undefined) {
      return 'var(--fg-3)';
    }
    return retainedPct >= 70 ? 'white' : 'var(--fg-1)';
  };

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
        <p className="analytics-chart-subtitle">
          Матрица удержания: строки = когорты (месяц найма), столбцы = дни после найма. Зелёное = хорошо.
        </p>
      </div>

      <div className="analytics-chart-container" style={{ overflowX: 'auto' }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: `150px repeat(${allDays.length}, 80px)`,
          gap: '1px',
          background: 'var(--border-2)',
          padding: '1px',
          borderRadius: '8px',
          minWidth: `${150 + allDays.length * 81}px`
        }}>
          {/* Header row */}
          <div style={{
            padding: '8px 12px',
            background: 'var(--bg-3)',
            fontWeight: '500',
            fontSize: '12px',
            color: 'var(--fg-3)',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}>
            Когорта
          </div>
          {allDays.map(day => (
            <div
              key={day}
              style={{
                padding: '8px 12px',
                background: 'var(--bg-3)',
                fontWeight: '500',
                fontSize: '12px',
                color: 'var(--fg-3)',
                textAlign: 'center',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}
            >
              {day}д
            </div>
          ))}

          {/* Data rows */}
          {data.cohorts.map((cohort) => (
            <React.Fragment key={cohort.month}>
              {/* Month label */}
              <div style={{
                padding: '12px',
                background: 'var(--bg-2)',
                fontWeight: '500',
                fontSize: '13px',
                color: 'var(--fg-1)',
                display: 'flex',
                alignItems: 'center'
              }}>
                {cohort.month}
              </div>

              {/* Retention cells */}
              {allDays.map(day => {
                const sizeData = cohort.sizes.find(size => size.day === day);
                const retainedPct = sizeData?.retained_pct ?? null;
                const backgroundColor = getColor(retainedPct);
                const textColor = getTextColor(retainedPct);

                return (
                  <div
                    key={`${cohort.month}-${day}`}
                    style={{
                      padding: '12px 8px',
                      background: backgroundColor,
                      color: textColor,
                      textAlign: 'center',
                      fontSize: '12px',
                      fontFamily: 'var(--font-mono)',
                      fontWeight: '500',
                      cursor: onDataClick && retainedPct !== null ? 'pointer' : 'default',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      minHeight: '40px'
                    }}
                    onClick={() => onDataClick?.({ cohort: cohort.month, day, retainedPct })}
                    title={retainedPct !== null ? `${cohort.month}, ${day}д: ${retainedPct.toFixed(1)}%` : 'Нет данных'}
                  >
                    {retainedPct !== null ? `${retainedPct.toFixed(0)}%` : '—'}
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>

        {/* Color legend */}
        <div style={{ marginTop: '20px', display: 'flex', alignItems: 'center', gap: '16px', fontSize: '12px' }}>
          <span style={{ color: 'var(--fg-3)', fontWeight: '500' }}>Удержание:</span>
          {[
            { min: 90, max: 100, color: '#16A34A', label: '90-100%' },
            { min: 80, max: 89, color: '#59A861', label: '80-89%' },
            { min: 70, max: 79, color: '#E0A21A', label: '70-79%' },
            { min: 60, max: 69, color: '#E08A3C', label: '60-69%' },
            { min: 0, max: 59, color: '#DC4646', label: '<60%' },
          ].map(range => (
            <div key={range.label} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <div style={{
                width: '12px',
                height: '12px',
                borderRadius: '2px',
                backgroundColor: range.color
              }} />
              <span style={{ color: 'var(--fg-3)' }}>{range.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}