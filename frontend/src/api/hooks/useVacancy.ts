import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type VacancyDetail = components['schemas']['VacancyDetail'];

export function useVacancy(id: string) {
  return useQuery({
    queryKey: ['vacancies', id],
    queryFn: async () => {
      const response = await api.get(`/vacancies/${id}`);
      return response.data as VacancyDetail;
    },
    enabled: !!id,
  });
}