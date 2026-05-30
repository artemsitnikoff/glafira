import { ComingSoon } from '@/components/ui/ComingSoon';

/**
 * Временная заглушка раздела «Пульс-Онбординг» — выключен из релиза до пересборки по эталону.
 * Рабочие PulsePage/PulseEmployeePage сохранены в репозитории, просто отвязаны от роутов.
 */
export function PulseComingSoon() {
  return (
    <ComingSoon
      icon="heart"
      title="Пульс-Онбординг — скоро"
      description="Модуль адаптации сотрудников в разработке. Запускаем систему без него — появится в одном из ближайших обновлений."
    />
  );
}
