import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type CandidateCreate = components['schemas']['CandidateCreate'];
type CandidateDetail = components['schemas']['CandidateDetail'];

export function useCreateCandidate(vacancyId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CandidateCreate) => {
      const response = await api.post('/candidates', data);
      return response.data as CandidateDetail;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      if (vacancyId) {
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'applications'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      }
      // KPI/«Требуют внимания»/лента на Главной устаревают после добавления кандидата
      queryClient.invalidateQueries({ queryKey: ['home'] });
      // Счётчики вакансий в сайдбаре — добавление кандидата меняет count/new_count.
      queryClient.invalidateQueries({ queryKey: ['vacancies', 'sidebar'] });
    },
  });
}

export function useDeleteCandidate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (candidateId: string) => {
      await api.delete(`/candidates/${candidateId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      // Удаление кандидата снимает его заявки из воронок → обновить сайдбар-счётчики и Главную.
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['home'] });
    },
  });
}