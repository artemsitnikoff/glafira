import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { CommentOut } from '@/api/aliases';

export function useComments(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'comments'],
    queryFn: async () => (await api.get<CommentOut[]>(`/candidates/${candidateId}/comments`)).data,
    enabled: !!candidateId,
  });
}