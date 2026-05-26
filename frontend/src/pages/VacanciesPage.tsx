import { EmptyState } from '@/components/ui/EmptyState';

export default function VacanciesPage() {
  return (
    <div className="content-inner">
      <EmptyVacancyPane />
    </div>
  );
}

function EmptyVacancyPane() {
  return (
    <EmptyState
      icon="briefcase"
      title="Выберите вакансию слева"
      description="Здесь откроется воронка кандидатов по выбранной вакансии. Или создайте новую вакансию."
    />
  );
}