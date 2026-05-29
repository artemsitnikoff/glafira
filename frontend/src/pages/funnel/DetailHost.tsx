import { Icon } from '@/components/ui/Icon';
import type { components } from '@/api/types';

type ApplicationRow = components['schemas']['ApplicationRow'];

type Props = {
  application: ApplicationRow | null;
  onClose: () => void;
  isResolving?: boolean;
};

export default function DetailHost({ onClose }: Props) {
  return (
    <div className="cand-detail">
      <button className="icon-btn" onClick={onClose} style={{ position: 'absolute', top: 16, right: 16, zIndex: 10 }}>
        <Icon name="x" size={18} />
      </button>

      <div style={{ padding: 40, textAlign: 'center' }}>
        <Icon name="user" size={48} style={{ color: 'var(--fg-4)', marginBottom: 16 }} />
        <h3 style={{ margin: '0 0 8px 0', fontSize: 18, fontWeight: 600, color: 'var(--fg-1)' }}>
          Заглушка детали кандидата
        </h3>
        <p style={{ margin: '0 0 4px 0', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
          ЗАХОД 1: Каркас воронки
        </p>
        <p style={{ margin: 0, color: 'var(--brand-accent)', fontWeight: 500, fontSize: 12 }}>
          DetailMode работает, карточка в ЗАХОДЕ 2
        </p>

        <div style={{ marginTop: 24, padding: 16, background: 'var(--bg-2)', borderRadius: 8, textAlign: 'left' }}>
          <p style={{ fontFamily: 'inherit', fontSize: 14, color: 'var(--fg-2)', marginBottom: 8 }}>
            <strong>Готово в Заходе 1:</strong>
          </p>
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 13, color: 'var(--fg-3)' }}>
            <li>Шапка вакансии (sticky)</li>
            <li>Чипы этапов (sticky)</li>
            <li>Таблица с sticky профилем 378px</li>
            <li>Сортировка ФИО/AI/колонки</li>
            <li>Bulk actions + фильтры</li>
            <li>DetailMode переключение</li>
          </ul>
        </div>
      </div>
    </div>
  );
}