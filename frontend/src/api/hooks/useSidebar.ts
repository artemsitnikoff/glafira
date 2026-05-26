import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { components } from '../types';

type VacancySidebar = components['schemas']['VacancySidebar'];

export function useSidebar() {
  return useQuery({
    queryKey: ['vacancies', 'sidebar'],
    queryFn: async () => {
      const response = await api.get<VacancySidebar>('/vacancies/sidebar');
      return response.data;
    },
    refetchInterval: 30_000,
  });
}