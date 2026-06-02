import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { HhAuthorizeResponse, HhPublishResponse } from '../hooks/useHhIntegration';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

// Локальные типы (openapi не регенерён)
interface HhConfigRequest {
  client_id: string;
  client_secret: string;
  redirect_uri: string;
}

interface HhConfigResponse {
  authorize_url: string;
}

// Интеграции с hh.ru
export function useHhSaveConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: HhConfigRequest): Promise<HhConfigResponse> => {
      const response = await api.post('/integrations/hh/config', data);
      return response.data as HhConfigResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'hh', 'status'] });
    },
  });
}

export function useHhAuthorize() {
  return useMutation({
    mutationFn: async (): Promise<HhAuthorizeResponse> => {
      const response = await api.get('/integrations/hh/authorize');
      return response.data as HhAuthorizeResponse;
    },
  });
}

export function useHhDisconnect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MessageResult> => {
      const response = await api.post('/integrations/hh/disconnect');
      return response.data as MessageResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'hh', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['integrations', 'hh', 'vacancies'] });
    },
  });
}

// Ручной забор откликов с hh.ru (привязанные вакансии → этап «Отклик»)
export interface HhPollDetail {
  name: string;
  status: string;
  hh_id: string;
  found: number | null;
  by_collection?: Record<string, number | null>;
  imported: number;
  updated?: number;
  sample?: string;
  error: string | null;
}
export interface HhPollResult {
  imported: number;
  updated?: number;
  skipped: number;
  vacancies: number;
  details?: HhPollDetail[];
}
export function useHhPollResponses() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<HhPollResult> => {
      const response = await api.post('/integrations/hh/poll-responses');
      return response.data as HhPollResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

// Привязка/отвязка вакансий
export function useHhLinkVacancy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ vacancyId, hhVacancyId }: { vacancyId: string; hhVacancyId: string }): Promise<MessageResult> => {
      const response = await api.post(`/vacancies/${vacancyId}/hh/link`, {
        hh_vacancy_id: hhVacancyId
      });
      return response.data as MessageResult;
    },
    onSuccess: (_, { vacancyId }) => {
      queryClient.invalidateQueries({ queryKey: ['vacancy', vacancyId] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
    },
  });
}

export function useHhUnlinkVacancy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (vacancyId: string): Promise<MessageResult> => {
      const response = await api.delete(`/vacancies/${vacancyId}/hh/link`);
      return response.data as MessageResult;
    },
    onSuccess: (_, vacancyId) => {
      queryClient.invalidateQueries({ queryKey: ['vacancy', vacancyId] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
    },
  });
}

export function useHhPublishVacancy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (vacancyId: string): Promise<HhPublishResponse> => {
      const response = await api.post(`/vacancies/${vacancyId}/hh/publish`);
      return response.data as HhPublishResponse;
    },
    onSuccess: (_, vacancyId) => {
      queryClient.invalidateQueries({ queryKey: ['vacancy', vacancyId] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['integrations', 'hh', 'vacancies'] });
    },
  });
}