import { useState } from 'react';
import type { TableData, TableColumn } from '@/api/aliases';
import { Icon } from '@/components/ui/Icon';

interface TableRendererProps {
  table: TableData;
}

export function TableRenderer({ table }: TableRendererProps) {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');

  const handleSort = (column: TableColumn) => {
    if (!column.sortable) return;

    if (sortColumn === column.key) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column.key);
      setSortDirection('desc');
    }
  };

  const sortedRows = [...(table.rows || [])];
  if (sortColumn) {
    sortedRows.sort((a, b) => {
      const aValue = a[sortColumn];
      const bValue = b[sortColumn];

      // Handle numeric values
      const aNumeric = typeof aValue === 'number' ? aValue : parseFloat(String(aValue).replace(/[^\d.-]/g, ''));
      const bNumeric = typeof bValue === 'number' ? bValue : parseFloat(String(bValue).replace(/[^\d.-]/g, ''));

      let comparison = 0;

      if (!isNaN(aNumeric) && !isNaN(bNumeric)) {
        comparison = aNumeric - bNumeric;
      } else {
        comparison = String(aValue).localeCompare(String(bValue));
      }

      return sortDirection === 'asc' ? comparison : -comparison;
    });
  }

  const formatCellValue = (value: any, column: TableColumn) => {
    if (value === null || value === undefined) {
      return '—';
    }

    switch (column.type) {
      case 'mono':
        return (
          <span className="analytics-table-cell mono">
            {typeof value === 'number' ? value.toLocaleString('ru-RU') : String(value)}
          </span>
        );

      case 'delta':
        const deltaStr = String(value);
        const isPositive = deltaStr.startsWith('+') || (!deltaStr.startsWith('-') && parseFloat(deltaStr) > 0);
        return (
          <span className={`analytics-table-cell delta ${isPositive ? 'positive' : 'negative'}`}>
            {deltaStr}
          </span>
        );

      case 'badge':
        // Simple badge styling - can be enhanced based on value
        const badgeClass = typeof value === 'number' && value > 50 ? 'success' : 'default';
        return (
          <span className={`badge badge-${badgeClass}`}>
            {String(value)}
          </span>
        );

      default:
        return String(value);
    }
  };

  if (!table.columns || table.columns.length === 0) {
    return (
      <div className="analytics-chart-card">
        <div className="analytics-chart-header">
          <h3 className="analytics-chart-title">{table.title}</h3>
        </div>
        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--fg-3)' }}>
          Нет данных для отображения
        </div>
      </div>
    );
  }

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{table.title}</h3>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="analytics-table">
          <thead className="analytics-table-header">
            <tr>
              {table.columns.map((column) => (
                <th
                  key={column.key}
                  className={column.sortable ? 'sortable' : ''}
                  onClick={() => handleSort(column)}
                  style={{
                    cursor: column.sortable ? 'pointer' : 'default',
                    userSelect: 'none',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    {column.label}
                    {column.sortable && (
                      <Icon
                        name={
                          sortColumn === column.key
                            ? sortDirection === 'asc'
                              ? 'chevron-up'
                              : 'chevron-down'
                            : 'chevron-up-down'
                        }
                        size={12}
                        style={{
                          opacity: sortColumn === column.key ? 1 : 0.4,
                        }}
                      />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {sortedRows.length === 0 ? (
              <tr>
                <td
                  colSpan={table.columns.length}
                  style={{
                    padding: '40px',
                    textAlign: 'center',
                    color: 'var(--fg-3)',
                  }}
                >
                  Нет данных для отображения
                </td>
              </tr>
            ) : (
              sortedRows.map((row, index) => (
                <tr key={index} className="analytics-table-row">
                  {table.columns.map((column) => (
                    <td
                      key={column.key}
                      className={`analytics-table-cell ${
                        column.type === 'mono' ? 'text-right' : ''
                      }`}
                    >
                      {formatCellValue(row[column.key], column)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}