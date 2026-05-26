import { useEffect } from 'react';
import { Icon } from '@/components/ui/Icon';

type Props = {
  candidateId: string;
  onClose: () => void;
};

export default function DetailHost({ candidateId, onClose }: Props) {

  // Global Esc handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <aside className="detail-host">
      <button className="detail-host__close" onClick={onClose} title="Закрыть (Esc)">
        <Icon name="x" size={20} />
      </button>

      <div className="detail-host__placeholder">
        <div className="detail-placeholder-content">
          <div className="detail-placeholder-icon">
            <Icon name="users" size={48} />
          </div>
          <h3>Карточка соискателя</h3>
          <p>candidate_id: {candidateId}</p>
          <p className="detail-placeholder-note">ТЗ-6 (следующий шаг)</p>
          <div className="detail-placeholder-info">
            <p>Здесь будет:</p>
            <ul>
              <li>7 табов: Резюме, AI-оценка, Верификация, Чат, Документы, Комментарии, Действия</li>
              <li>Кнопки перевода и отклонения</li>
              <li>Полная история взаимодействий</li>
            </ul>
          </div>
        </div>
      </div>
    </aside>
  );
}