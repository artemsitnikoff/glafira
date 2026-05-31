import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

export type DefaultFunnelStage = {
  id: string;
  key: string;
  name: string;
  type: 'start' | 'system' | 'middle' | 'finalOk' | 'finalBad';
  description?: string;
  protected?: boolean;
  position: number;
};

export function useDefaultFunnel() {
  return useQuery({
    queryKey: ['settings', 'default-funnel'],
    queryFn: async () => {
      const response = await api.get('/settings/default-funnel');
      return response.data as DefaultFunnelStage[];
    },
    staleTime: 60_000,
  });
}