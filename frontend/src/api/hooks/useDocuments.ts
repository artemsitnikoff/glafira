import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { DocumentOut } from '@/api/aliases';

export function useDocuments(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'documents'],
    queryFn: async () => (await api.get<DocumentOut[]>(`/candidates/${candidateId}/documents`)).data,
    enabled: !!candidateId,
  });
}