import { Icon } from '@/components/ui/Icon';

export function CandidateLoader() {
  return (
    <div className="candidate-detail__loader">
      <Icon name="loader" size={32} />
      <p style={{ marginTop: 'var(--space-3)', color: 'var(--fg-2)' }}>
        Загружаем карточку соискателя...
      </p>
    </div>
  );
}