import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для интеграции с hh.ru (openapi не регенерён)
export interface HhStatus {
  configured: boolean;
  connected: boolean;
  redirect_uri?: string;
  client_id_masked?: string;
  hh_employer_id?: string;
  connected_at?: string;
  expires_at?: string;
}

export interface HhVacancy {
  id: string;
  name: string;
  area: string | null;
  linked: boolean;
}

export interface HhAuthorizeResponse {
  authorize_url: string;
}

// Персональное (per-user) hh-подключение рекрутёра.
// Форма ответа сверена с backend `hh_service.get_personal_status`
// (GET /integrations/hh/me/status). НЕ содержит имени работодателя —
// только id/флаги, поэтому и в UI показываем только то, что реально приходит.
export interface MyHhStatus {
  connected: boolean;
  hh_employer_id?: string | null;
  hh_manager_id?: string | null;
  expires_at?: string | null;
  connected_at?: string | null;
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

// Статус ЛИЧНОГО hh-подключения текущего пользователя (admin/recruiter).
// `enabled` — чтобы не дёргать 403-эндпоинт у ролей без доступа.
export function useMyHhStatus(enabled = true) {
  return useQuery({
    queryKey: ['integrations', 'hh', 'me', 'status'],
    queryFn: async (): Promise<MyHhStatus> => {
      const response = await api.get('/integrations/hh/me/status');
      return response.data as MyHhStatus;
    },
    enabled,
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