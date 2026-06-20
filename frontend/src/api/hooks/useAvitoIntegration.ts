import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для интеграции с Авито Работа (openapi не регенерён)
export interface AvitoStatus {
  connected: boolean;
}

export function useAvitoStatus() {
  return useQuery({
    queryKey: ['integrations', 'avito', 'status'],
    queryFn: async (): Promise<AvitoStatus> => {
      const response = await api.get('/integrations/avito/status');
      return response.data as AvitoStatus;
    },
  });
}
