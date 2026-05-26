import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { PulseSummary } from '@/api/aliases';

export function useHomePulseSummary() {
  return useQuery({
    queryKey: ['home', 'pulse-summary'],
    queryFn: async () => (await api.get<PulseSummary>('/home/pulse-summary')).data,
  });
}