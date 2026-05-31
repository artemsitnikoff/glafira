import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для интеграции с hh.ru (openapi не регенерён)
export interface HhStatus {
  connected: boolean;
  hh_employer_id?: string;
  connected_at?: string;
  expires_at?: string;
}

export interface HhVacancy {
  id: string;
  name: string;
  area: string | null;
}

export interface HhAuthorizeResponse {
  authorize_url: string;
}

export interface HhPublishResponse {
  hh_vacancy_id: string;
}

export function useHhStatus() {
  return useQuery({
    queryKey: ['integrations', 'hh', 'status'],
    queryFn: async (): Promise<HhStatus> => {
      const response = await api.get('/integrations/hh/status');
      return response.data as HhStatus;
    },
  });
}

export function useHhVacancies(enabled = false) {
  return useQuery({
    queryKey: ['integrations', 'hh', 'vacancies'],
    queryFn: async (): Promise<HhVacancy[]> => {
      const response = await api.get('/integrations/hh/vacancies');
      return response.data as HhVacancy[];
    },
    enabled,
  });
}