import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type Paginated = components['schemas']['Paginated_ApplicationRow_'];

export type ApplicationFilters = {
  stage?: string;
  search?: string;
  score_min?: number;
  salary_max?: number;
  source?: string | string[];
  city?: string | string[];
  messenger?: string | string[];
  ready_relocate?: boolean;
  added_period?: string;
  repeat?: boolean;
  sort?: string;
  order?: 'asc' | 'desc';
  page?: number;
  size?: number;
};

export function useApplications(vacancyId: string, filters: ApplicationFilters = {}) {
  return useQuery({
    queryKey: ['vacancies', vacancyId, 'applications', filters],
    queryFn: async () => {
      const params = new URLSearchParams();

      if (filters.stage) params.append('stage', filters.stage);
      if (filters.search) params.append('search', filters.search);
      if (filters.score_min) params.append('score_min', filters.score_min.toString());
      if (filters.salary_max) params.append('salary_max', filters.salary_max.toString());
      if (filters.source) {
        if (Array.isArray(filters.source)) {
          filters.source.forEach(s => params.append('source', s));
        } else {
          params.append('source', filters.source);
        }
      }
      if (filters.city) {
        if (Array.isArray(filters.city)) {
          filters.city.forEach(c => params.append('city', c));
        } else {
          params.append('city', filters.city);
        }
      }
      if (filters.messenger) {
        if (Array.isArray(filters.messenger)) {
          filters.messenger.forEach(m => params.append('messenger', m));
        } else {
          params.append('messenger', filters.messenger);
        }
      }
      if (filters.ready_relocate !== undefined) params.append('ready_relocate', filters.ready_relocate.toString());
      if (filters.added_period) params.append('added_period', filters.added_period);
      if (filters.repeat !== undefined) params.append('repeat', filters.repeat.toString());
      if (filters.sort) params.append('sort', filters.sort);
      if (filters.order) params.append('order', filters.order);
      if (filters.page) params.append('page', filters.page.toString());
      if (filters.size) params.append('size', filters.size.toString());

      const response = await api.get(`/api/v1/vacancies/${vacancyId}/applications?${params.toString()}`);
      return response.data as Paginated;
    },
    enabled: !!vacancyId,
  });
}