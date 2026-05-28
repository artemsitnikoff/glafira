import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { EventOut } from '@/api/aliases';

type UseEventsParams = {
  candidate_id?: string;
  limit?: number;
}

export function useEvents(params: UseEventsParams = {}) {
  const { candidate_id, limit = 30 } = params;

  return useQuery({
    queryKey: ['home', 'events', { candidate_id, limit }],
    queryFn: async () => {
      const queryParams: Record<string, string | number> = { limit };
      if (candidate_id) {
        queryParams.candidate_id = candidate_id;
      }
      return (await api.get<EventOut[]>('/home/events', { params: queryParams })).data;
    },
  });
}