import { EmptyState } from './EmptyState';
import type { IconName } from './Icon';

interface ComingSoonProps {
  title: string;
  description?: string;
  icon?: IconName;
}

/**
 * Полноэкранная заглушка «Скоро» для разделов, которые временно выключены из релиза
 * (Аналитика, Пульс-Онбординг). Переиспользует EmptyState — реальные токены, без своей вёрстки.
 */
export function ComingSoon({
  title,
  description = 'Раздел в разработке. Запускаем систему без него — появится в одном из ближайших обновлений.',
  icon = 'sparkle',
}: ComingSoonProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '70vh',
        width: '100%',
      }}
    >
      <EmptyState title={title} description={description} icon={icon} />
    </div>
  );
}
