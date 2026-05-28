import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { EvaluationOut } from '@/api/aliases';

export function useEvaluation(candidateId: string | null, applicationId?: string) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'evaluation', applicationId],
    queryFn: async () => {
      const params = applicationId ? { application_id: applicationId } : undefined;
      return (await api.get<EvaluationOut>(`/candidates/${candidateId}/evaluation`, { params })).data;
    },
    enabled: !!candidateId,
  });
}