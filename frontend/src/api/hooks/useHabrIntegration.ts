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

export function useHabrStatus() {
  return useQuery({
    queryKey: ['integrations', 'habr', 'status'],
    queryFn: async (): Promise<HabrStatus> => {
      const response = await api.get('/integrations/habr/status');
      return response.data as HabrStatus;
    },
  });
}
