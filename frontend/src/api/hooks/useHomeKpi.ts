import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { HomeKpi } from '@/api/aliases';

export function useHomeKpi(period: string, extended: boolean) {
  return useQuery({
    queryKey: ['home', 'kpi', period, extended],
    queryFn: async () => (await api.get<HomeKpi>('/home/kpi', { params: { period, extended } })).data,
  });
}