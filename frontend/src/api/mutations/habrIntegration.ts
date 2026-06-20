import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { HabrAuthorizeResponse } from '../hooks/useHabrIntegration';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

// Локальные типы (openapi не регенерён)
export interface HabrPollResult {
  imported: number;
  skipped: number;
  vacancies: number;
  updated?: number;
  details?: Array<{
    name: string;
    habr_id: string;
    imported: number;
    skipped: number;
    error: string | null;
  }>;
}

export function useHabrAuthorize() {
  return useMutation({
    mutationFn: async (): Promise<HabrAuthorizeResponse> => {
      const response = await api.get('/integrations/habr/authorize');
      return response.data as HabrAuthorizeResponse;
    },
  });
}

export function useHabrDisconnect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MessageResult> => {
      const response = await api.post('/integrations/habr/disconnect');
      return response.data as MessageResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'habr', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['integrations', 'habr', 'vacancies'] });
    },
  });
}

// Ручной забор откликов Хабр → воронка (привязанные вакансии → этап «Отклик»)
export function useHabrPollResponses() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<HabrPollResult> => {
      const response = await api.post('/integrations/habr/poll-responses');
      return response.data as HabrPollResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

// Привязка вакансии Глафиры к вакансии Хабр Карьера
export function useHabrLinkVacancy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ vacancyId, habrVacancyId }: { vacancyId: string; habrVacancyId: string }): Promise<MessageResult> => {
      const response = await api.post('/integrations/habr/link-vacancy', {
        vacancy_id: vacancyId,
        habr_vacancy_id: habrVacancyId,
      });
      return response.data as MessageResult;
    },
    onSuccess: (_, { vacancyId }) => {
      queryClient.invalidateQueries({ queryKey: ['vacancy', vacancyId] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
    },
  });
}

// Отвязка вакансии Глафиры от Хабр Карьера
// ⚠️ Бек принимает vacancy_id как query param (не body): POST /habr/unlink-vacancy?vacancy_id=
export function useHabrUnlinkVacancy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (vacancyId: string): Promise<MessageResult> => {
      const response = await api.post(`/integrations/habr/unlink-vacancy?vacancy_id=${encodeURIComponent(vacancyId)}`);
      return response.data as MessageResult;
    },
    onSuccess: (_, vacancyId) => {
      queryClient.invalidateQueries({ queryKey: ['vacancy', vacancyId] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
    },
  });
}
