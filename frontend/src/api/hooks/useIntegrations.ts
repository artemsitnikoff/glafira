import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type IntegrationOut = components['schemas']['IntegrationOut'];

export function useIntegrations() {
  return useQuery({
    queryKey: ['settings', 'integrations'],
    queryFn: async () => {
      const response = await api.get('/api/v1/settings/integrations');
      return response.data as IntegrationOut[];
    },
    staleTime: 60_000,
  });
}