import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { SourceItem } from '@/api/aliases';

export function useHomeSources(period: string) {
  return useQuery({
    queryKey: ['home', 'sources', period],
    queryFn: async () => (await api.get<SourceItem[]>('/home/sources', { params: { period } })).data,
  });
}