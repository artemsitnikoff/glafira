import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type ClientCreate = components['schemas']['ClientCreate'];
type ClientOut = components['schemas']['ClientOut'];

export function useCreateClient() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ClientCreate) => {
      const response = await api.post('/clients', data);
      return response.data as ClientOut;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
    },
  });
}