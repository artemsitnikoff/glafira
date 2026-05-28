import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type ProfileOut = components['schemas']['ProfileOut'];

export function useProfile() {
  return useQuery({
    queryKey: ['settings', 'profile'],
    queryFn: async () => {
      const response = await api.get('/settings/profile');
      return response.data as ProfileOut;
    },
    staleTime: 30_000,
  });
}