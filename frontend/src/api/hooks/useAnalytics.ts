import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AnalyticsResponse, AnalyticsFilters } from '@/api/aliases';

export function useAnalytics(report: string, filters: AnalyticsFilters) {
  return useQuery({
    queryKey: ['analytics', report, filters],
    queryFn: async () => {
      const params = new URLSearchParams();

      // Add all filter parameters
      params.append('period', filters.period);
      if (filters.date_from) params.append('date_from', filters.date_from);
      if (filters.date_to) params.append('date_to', filters.date_to);
      if (filters.compare !== undefined) params.append('compare', filters.compare.toString());

      // Add array parameters
      if (filters.vacancy_ids?.length) {
        filters.vacancy_ids.forEach(id => params.append('vacancy_ids', id));
      }
      if (filters.recruiter_ids?.length) {
        filters.recruiter_ids.forEach(id => params.append('recruiter_ids', id));
      }

      const response = await api.get(`/analytics/${report}?${params.toString()}`);
      return response.data as AnalyticsResponse;
    },
    enabled: !!report,
    staleTime: 60000, // 1 minute
  });
}