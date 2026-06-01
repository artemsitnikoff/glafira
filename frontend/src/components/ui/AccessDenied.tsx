import { EmptyState } from './EmptyState';
import type { IconName } from './Icon';

interface AccessDeniedProps {
  title?: string;
  description?: string;
  icon?: IconName;
}

/**
 * Экран "Нет доступа" для ролевых ограничений.
 * Используется когда manager пытается попасть в настройки или другие запрещённые разделы.
 */
export function AccessDenied({
  title = 'Нет доступа',
  description = 'У вас нет прав для просмотра этого раздела. Обратитесь к администратору.',
  icon = 'shield',
}: AccessDeniedProps) {
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