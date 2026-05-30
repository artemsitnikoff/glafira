import { ComingSoon } from '@/components/ui/ComingSoon';

// Раздел «Аналитика» временно выключен из релиза (пересборка по эталону — позже).
// Рабочая страница './analytics/AnalyticsPage' сохранена в репозитории, отвязана от роута.
export default function MainAnalyticsPage() {
  return (
    <ComingSoon
      icon="chart"
      title="Аналитика — скоро"
      description="Отчёты по подбору в разработке. Запускаем систему без них — появятся в одном из ближайших обновлений."
    />
  );
}