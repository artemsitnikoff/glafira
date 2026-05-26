import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { EventOut } from '@/api/aliases';

export function useHomeEvents(limit = 30) {
  return useQuery({
    queryKey: ['home', 'events', limit],
    queryFn: async () => (await api.get<EventOut[]>('/home/events', { params: { limit } })).data,
    refetchInterval: 15_000,
  });
}