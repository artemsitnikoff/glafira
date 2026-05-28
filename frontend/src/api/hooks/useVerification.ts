import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { VerificationOut } from '@/api/aliases';

export function useVerification(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'verification'],
    queryFn: async () => (await api.get<VerificationOut>(`/candidates/${candidateId}/verification`)).data,
    enabled: !!candidateId,
  });
}