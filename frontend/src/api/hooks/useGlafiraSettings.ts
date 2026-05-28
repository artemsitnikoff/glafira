import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type GlafiraSettingsOut = components['schemas']['GlafiraSettingsOut'];

export function useGlafiraSettings() {
  return useQuery({
    queryKey: ['settings', 'glafira'],
    queryFn: async () => {
      const response = await api.get('/api/v1/settings/glafira');
      return response.data as GlafiraSettingsOut;
    },
    staleTime: 60_000,
  });
}