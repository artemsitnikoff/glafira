import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type VacancyCreate = components['schemas']['VacancyCreate'];
type VacancyUpdate = components['schemas']['VacancyUpdate'];
type VacancyDetail = components['schemas']['VacancyDetail'];

export function useCreateVacancy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: VacancyCreate) => {
      const response = await api.post('/vacancies', data);
      return response.data as VacancyDetail;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['sidebar'] });
    },
  });
}

export function useUpdateVacancy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: VacancyUpdate }) => {
      const response = await api.patch(`/vacancies/${id}`, data);
      return response.data as VacancyDetail;
    },
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['vacancies', id] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['sidebar'] });
    },
  });
}

export function useArchiveVacancy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const response = await api.post(`/vacancies/${id}/archive`);
      return response.data;
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['vacancies', id] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['sidebar'] });
    },
  });
}