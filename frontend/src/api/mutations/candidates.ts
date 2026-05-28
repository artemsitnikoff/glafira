import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type CandidateCreate = components['schemas']['CandidateCreate'];
type CandidateDetail = components['schemas']['CandidateDetail'];

export function useCreateCandidate(vacancyId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CandidateCreate) => {
      const response = await api.post('/api/v1/candidates', data);
      return response.data as CandidateDetail;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      if (vacancyId) {
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'applications'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      }
    },
  });
}

export function useDeleteCandidate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (candidateId: string) => {
      await api.delete(`/api/v1/candidates/${candidateId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
    },
  });
}