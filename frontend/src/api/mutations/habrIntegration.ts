import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { HabrAuthorizeResponse } from '../hooks/useHabrIntegration';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

export function useHabrAuthorize() {
  return useMutation({
    mutationFn: async (): Promise<HabrAuthorizeResponse> => {
      const response = await api.get('/integrations/habr/authorize');
      return response.data as HabrAuthorizeResponse;
    },
  });
}

export function useHabrDisconnect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MessageResult> => {
      const response = await api.post('/integrations/habr/disconnect');
      return response.data as MessageResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'habr', 'status'] });
    },
  });
}
