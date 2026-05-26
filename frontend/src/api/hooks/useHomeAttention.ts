import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AttentionItem } from '@/api/aliases';

export function useHomeAttention() {
  return useQuery({
    queryKey: ['home', 'attention'],
    queryFn: async () => (await api.get<AttentionItem[]>('/home/attention')).data,
  });
}