import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Candidate } from '@/api/aliases';

export function useCandidateDetail(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId],
    queryFn: async () => (await api.get<Candidate>(`/candidates/${candidateId}`)).data,
    enabled: !!candidateId,
  });
}