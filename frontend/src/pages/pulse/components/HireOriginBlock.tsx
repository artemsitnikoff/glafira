import { Icon } from '@/components/ui/Icon';
import type { EmployeeDetail } from '@/api/aliases';

type Props = {
  employee: EmployeeDetail;
};

export function HireOriginBlock({ employee }: Props) {
  return (
    <div style={{
      padding: 'var(--space-4)',
      backgroundColor: 'var(--bg-panel-2)',
      borderRadius: 'var(--radius-md)',
      border: '1px solid var(--border-1)',
      marginTop: 'var(--space-4)'
    }}>
      <div style={{
        fontSize: '12px',
        fontWeight: 600,
        color: 'var(--fg-3)',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        marginBottom: 'var(--space-2)'
      }}>
        Откуда пришёл
      </div>

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-3)',
        marginBottom: 'var(--space-3)'
      }}>
        <div style={{ flex: 1 }}>
          <div style={{
            fontSize: '13px',
            color: 'var(--fg-2)',
            marginBottom: '2px'
          }}>
            <span style={{ fontWeight: 500 }}>Источник:</span> {employee.hire_source || '—'}
          </div>
          <div style={{
            fontSize: '13px',
            color: 'var(--fg-2)'
          }}>
            <span style={{ fontWeight: 500 }}>Рекрутёр:</span> {employee.recruiter_full_name || '—'}
          </div>
        </div>
      </div>

      {employee.candidate_id && (
        <a
          href={`/candidates/${employee.candidate_id}`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            padding: '6px 12px',
            fontSize: '12px',
            fontWeight: 500,
            color: 'var(--accent)',
            backgroundColor: 'var(--bg-2)',
            border: '1px solid var(--border-1)',
            borderRadius: 'var(--radius-sm)',
            textDecoration: 'none',
            transition: 'all 0.2s ease'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-3)';
            e.currentTarget.style.borderColor = 'var(--accent)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-2)';
            e.currentTarget.style.borderColor = 'var(--border-1)';
          }}
        >
          <Icon name="external-link" size={12} />
          Открыть исходную карточку соискателя
        </a>
      )}
    </div>
  );
}