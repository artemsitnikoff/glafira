import { useQuery } from '@tanstack/react-query';
import { client } from '../client';
import type { AlertOut } from '../aliases';

export function usePulseAlertsCount() {
  const { data: alerts, isLoading } = useQuery({
    queryKey: ['pulse', 'alerts'],
    queryFn: async () => {
      const response = await client.get<AlertOut[]>('/pulse/alerts?dismissed=false');
      return response.data;
    },
    refetchInterval: 30_000,
  });

  const count = alerts?.length || 0;
  return { count, isLoading };
}