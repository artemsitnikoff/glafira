import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type Paginated = components['schemas']['Paginated_VacancyDetail_'];

export function useArchivedVacancies() {
  return useQuery({
    queryKey: ['vacancies', 'archived'],
    queryFn: async () => {
      const response = await api.get('/api/v1/vacancies?status=archived');
      return response.data as Paginated;
    },
  });
}