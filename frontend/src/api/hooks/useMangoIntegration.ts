import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы (openapi не регенерён)
export interface MangoStatus {
  configured: boolean;
  verified: boolean;
  vpbx_api_url: string | null;
  last_test_at: string | null;
  last_test_ok: boolean;
  last_test_error: string | null;
}

export function useMangoStatus() {
  return useQuery({
    queryKey: ['integrations', 'mango', 'status'],
    queryFn: async (): Promise<MangoStatus> => {
      const response = await api.get('/integrations/mango/status');
      return response.data as MangoStatus;
    },
  });
}