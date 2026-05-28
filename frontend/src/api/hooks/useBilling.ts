import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type BillingOut = components['schemas']['BillingOut'];

export function useBilling() {
  return useQuery({
    queryKey: ['settings', 'billing'],
    queryFn: async () => {
      const response = await api.get('/api/v1/settings/billing');
      return response.data as BillingOut;
    },
    staleTime: 60_000,
  });
}