import { useState } from 'react';
import type { TableData, TableColumn } from '@/api/aliases';
import { AnCard } from './AnCard';
import { Icon } from '@/components/ui/Icon';

interface AnTableProps {
  table: TableData;
  /** Колонки этого типа выравниваем вправо (mono). */
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return value.toLocaleString('ru-RU');
  const s = String(value);
  return s.length === 0 ? '—' : s;
}

/** Числовое значение для сортировки (учитывает строки вида "42.5%"). */
function numericValue(value: unknown): number {
  if (typeof value === 'number') return value;
  const parsed = parseFloat(String(value).replace(/[^\d.-]/g, ''));
  return Number.isNaN(parsed) ? NaN : parsed;
}

export function AnTable({ table }: AnTableProps) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  if (!table.columns || table.columns.length === 0) {
    return (
      <AnCard title={table.title}>
        <div className="an-table-empty">Нет данных для отображения</div>
      </AnCard>
    );
  }

  const handleSort = (col: TableColumn) => {
    if (!col.sortable) return;
    if (sortKey === col.key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(col.key);
      setSortDir('desc');
    }
  };

  const rows = [...(table.rows || [])];
  if (sortKey) {
    rows.sort((a, b) => {
      const an = numericValue(a[sortKey]);
      const bn = numericValue(b[sortKey]);
      let cmp: number;
      if (!Number.isNaN(an) && !Number.isNaN(bn)) {
        cmp = an - bn;
      } else {
        cmp = String(a[sortKey] ?? '').localeCompare(String(b[sortKey] ?? ''));
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }

  const isNum = (col: TableColumn) => col.type === 'mono' || col.type === 'delta';

  return (
    <AnCard title={table.title}>
      <div className="an-table">
        <div className="an-thead">
          {table.columns.map((col) => (
            <div
              key={col.key}
              className={isNum(col) ? 'th-num' : ''}
              style={{
                flex: isNum(col) ? '0 0 auto' : '1 1 0',
                width: isNum(col) ? 110 : undefined,
                cursor: col.sortable ? 'pointer' : 'default',
                userSelect: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                justifyContent: isNum(col) ? 'flex-end' : 'flex-start',
              }}
              onClick={() => handleSort(col)}
            >
              {col.label}
              {col.sortable && sortKey === col.key && (
                <Icon name={sortDir === 'asc' ? 'chevron-up' : 'chevron-down'} size={12} />
              )}
            </div>
          ))}
        </div>

        {rows.length === 0 ? (
          <div className="an-table-empty">Нет данных за период</div>
        ) : (
          rows.map((row, i) => (
            <div key={i} className="an-trow">
              {table.columns.map((col) => (
                <div
                  key={col.key}
                  className={isNum(col) ? 'td-num' : 'td-text'}
                  style={{
                    flex: isNum(col) ? '0 0 auto' : '1 1 0',
                    width: isNum(col) ? 110 : undefined,
                  }}
                >
                  {cellText(row[col.key])}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </AnCard>
  );
}
