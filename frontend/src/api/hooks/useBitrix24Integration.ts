import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для Битрикс24-интеграции (openapi не регенерён)
export interface Bitrix24Status {
  configured: boolean;
  verified: boolean;
  portal?: string | null;
  user_count?: number | null;
  last_test_at?: string | null;
  last_test_ok?: boolean;
  last_test_error?: string | null;
}

export function useBitrix24Status() {
  return useQuery({
    queryKey: ['integrations', 'bitrix24', 'status'],
    queryFn: async (): Promise<Bitrix24Status> => {
      const response = await api.get('/integrations/bitrix24/status');
      return response.data as Bitrix24Status;
    },
  });
}
