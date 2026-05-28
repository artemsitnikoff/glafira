import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type RejectReasonOut = components['schemas']['RejectReasonOut'];

export function useRejectReasons() {
  return useQuery({
    queryKey: ['settings', 'reject-reasons'],
    queryFn: async () => {
      const response = await api.get('/settings/reject-reasons');
      return response.data as RejectReasonOut[];
    },
    staleTime: 60_000, // 1 minute
  });
}