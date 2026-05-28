import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { MessageOut } from '@/api/aliases';

export function useMessages(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'messages'],
    queryFn: async () => (await api.get<MessageOut[]>(`/candidates/${candidateId}/messages`)).data,
    enabled: !!candidateId,
  });
}