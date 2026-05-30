import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type VacancyCreate = components['schemas']['VacancyCreate'];
type VacancyUpdate = components['schemas']['VacancyUpdate'];
type VacancyDetail = components['schemas']['VacancyDetail'];

// Локальные типы для stage API (openapi не регенерился)
type StageCreateRequest = {
  stage_key: string;
  label: string;
  order_index: number;
  is_terminal?: boolean;
};

type StageUpdateRequest = {
  label: string;
};

type StageReorderRequest = {
  order: string[];
};

type ApiResponse = {
  message: string;
};

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

export function useAddVacancyStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ vacancyId, data }: { vacancyId: string; data: StageCreateRequest }) => {
      const response = await api.post(`/vacancies/${vacancyId}/stages`, data);
      return response.data as ApiResponse;
    },
    onSuccess: (_, { vacancyId }) => {
      queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId] });
    },
  });
}

export function useRenameVacancyStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ vacancyId, stageKey, data }: { vacancyId: string; stageKey: string; data: StageUpdateRequest }) => {
      const response = await api.patch(`/vacancies/${vacancyId}/stages/${stageKey}`, data);
      return response.data as ApiResponse;
    },
    onSuccess: (_, { vacancyId }) => {
      queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId] });
    },
  });
}

export function useDeleteVacancyStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ vacancyId, stageKey }: { vacancyId: string; stageKey: string }) => {
      await api.delete(`/vacancies/${vacancyId}/stages/${stageKey}`);
    },
    onSuccess: (_, { vacancyId }) => {
      queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId] });
    },
  });
}

export function useReorderVacancyStages() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ vacancyId, data }: { vacancyId: string; data: StageReorderRequest }) => {
      const response = await api.put(`/vacancies/${vacancyId}/stages/reorder`, data);
      return response.data as ApiResponse;
    },
    onSuccess: (_, { vacancyId }) => {
      queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId] });
    },
  });
}