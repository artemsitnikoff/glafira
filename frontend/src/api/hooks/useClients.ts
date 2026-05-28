import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type ClientOut = components['schemas']['ClientOut'];

export function useClients() {
  return useQuery({
    queryKey: ['clients'],
    queryFn: async () => {
      const response = await api.get('/clients');
      return response.data as ClientOut[];
    },
  });
}