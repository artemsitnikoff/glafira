import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для интеграции с Хабр Карьера (openapi не регенерён)
export interface HabrStatus {
  connected: boolean;
  habr_login?: string | null;
  expires_at?: string | null;
}

export interface HabrAuthorizeResponse {
  authorize_url: string;
}

// ⚠️ ASSUMPTION — форма ответа эндпоинта не подтверждена до одобрения приложения Хабром.
// Поле 'title' (или 'name') может различаться. Обрабатывается gracefully.
export interface HabrVacancy {
  id: string;
  title: string;
  city: string | null;
}

export function useHabrStatus() {
  return useQuery({
    queryKey: ['integrations', 'habr', 'status'],
    queryFn: async (): Promise<HabrStatus> => {
      const response = await api.get('/integrations/habr/status');
      return response.data as HabrStatus;
    },
  });
}

// enabled=false по умолчанию — запрос делается только когда нужен (connected && editMode)
// При ошибке (эндпоинт-ASSUMPTION) graceful: возвращает пустой список, не краш
export function useHabrVacancies(enabled = false) {
  return useQuery({
    queryKey: ['integrations', 'habr', 'vacancies'],
    queryFn: async (): Promise<HabrVacancy[]> => {
      const response = await api.get('/integrations/habr/vacancies');
      return response.data as HabrVacancy[];
    },
    enabled,
    // При сбое эндпоинта — не ретраить агрессивно (эндпоинт под ASSUMPTION)
    retry: 1,
  });
}
