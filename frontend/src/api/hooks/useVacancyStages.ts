import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

// openapi не регенерился → добавляем description локально (бэк его уже отдаёт)
type VacancyStageCount = components['schemas']['VacancyStageCount'] & {
  description?: string | null;
};

export function useVacancyStages(vacancyId: string) {
  return useQuery({
    queryKey: ['vacancies', vacancyId, 'stages'],
    queryFn: async () => {
      const response = await api.get(`/vacancies/${vacancyId}/stages`);
      return response.data as VacancyStageCount[];
    },
    enabled: !!vacancyId,
  });
}