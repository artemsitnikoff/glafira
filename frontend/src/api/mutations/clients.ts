import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type ClientOut = components['schemas']['ClientOut'];

// Локальные типы (openapi не регенерён — POST/PATCH тела через cast)
export interface ClientCreate {
  name: string;
  contact_person?: string | null;
}

export interface ClientUpdate {
  name?: string;
  contact_person?: string | null;
}

export function useCreateClient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: ClientCreate): Promise<ClientOut> => {
      const response = await api.post('/clients', data as ClientCreate);
      return response.data as ClientOut;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
    },
  });
}

export function useUpdateClient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: ClientUpdate }): Promise<ClientOut> => {
      const response = await api.patch(`/clients/${id}`, data as ClientUpdate);
      return response.data as ClientOut;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
    },
  });
}

export function useDeleteClient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await api.delete(`/clients/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
    },
  });
}
