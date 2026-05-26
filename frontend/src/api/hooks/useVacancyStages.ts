import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type VacancyStageCount = components['schemas']['VacancyStageCount'];

export function useVacancyStages(vacancyId: string) {
  return useQuery({
    queryKey: ['vacancies', vacancyId, 'stages'],
    queryFn: async () => {
      const response = await api.get(`/api/v1/vacancies/${vacancyId}/stages`);
      return response.data as VacancyStageCount[];
    },
    enabled: !!vacancyId,
  });
}