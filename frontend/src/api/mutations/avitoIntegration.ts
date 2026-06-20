import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

// Результат забора откликов Авито: {imported, updated, skipped, vacancies, errors}
export interface AvitoPollResult {
  imported: number;
  updated?: number;
  skipped: number;
  vacancies: number;
  errors?: Array<{
    vacancy_id?: string;
    avito_vacancy_id?: string;
    error: string;
  }>;
}

/** Сохранить client_id и client_secret Авито (client_credentials). Admin only. */
export function useAvitoSaveConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ client_id, client_secret }: { client_id: string; client_secret: string }): Promise<MessageResult> => {
      const response = await api.post('/integrations/avito/config', { client_id, client_secret });
      return response.data as MessageResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'avito', 'status'] });
    },
  });
}

/** Ручной забор откликов Авито → воронка. Admin only. */
export function useAvitoPollResponses() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<AvitoPollResult> => {
      const response = await api.post('/integrations/avito/poll-responses');
      return response.data as AvitoPollResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

/** Привязать вакансию Глафиры к вакансии Авито (числовой id строкой). Admin only. */
export function useAvitoLinkVacancy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ vacancyId, avitoVacancyId }: { vacancyId: string; avitoVacancyId: string }): Promise<MessageResult> => {
      const response = await api.post('/integrations/avito/link-vacancy', {
        vacancy_id: vacancyId,
        avito_vacancy_id: avitoVacancyId,
      });
      return response.data as MessageResult;
    },
    onSuccess: (_, { vacancyId }) => {
      queryClient.invalidateQueries({ queryKey: ['vacancy', vacancyId] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
    },
  });
}

/**
 * Отвязать вакансию от Авито.
 * Бек принимает vacancy_id как query param: POST /avito/unlink-vacancy?vacancy_id=
 */
export function useAvitoUnlinkVacancy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (vacancyId: string): Promise<MessageResult> => {
      const response = await api.post(`/integrations/avito/unlink-vacancy?vacancy_id=${encodeURIComponent(vacancyId)}`);
      return response.data as MessageResult;
    },
    onSuccess: (_, vacancyId) => {
      queryClient.invalidateQueries({ queryKey: ['vacancy', vacancyId] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
    },
  });
}

/** Отключить интеграцию с Авито (удалить сохранённые ключи). Admin only. */
export function useAvitoDisconnect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MessageResult> => {
      const response = await api.post('/integrations/avito/disconnect');
      return response.data as MessageResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'avito', 'status'] });
    },
  });
}
