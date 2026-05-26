import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { components } from '../types';

type AlertOut = components['schemas']['AlertOut'];

export function usePulseAlerts() {
  return useQuery({
    queryKey: ['pulse', 'alerts'],
    queryFn: async () => {
      const response = await api.get<AlertOut[]>('/pulse/alerts');
      return response.data;
    },
    refetchInterval: 30_000,
  });
}

export function usePulseAlertsCount() {
  const q = usePulseAlerts();
  const count = (q.data ?? []).filter((a: AlertOut) => !a.is_dismissed).length;
  return { count, isLoading: q.isLoading };
}