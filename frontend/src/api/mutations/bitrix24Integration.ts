import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { Bitrix24Status } from '../hooks/useBitrix24Integration';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

export interface Bitrix24TestResponse {
  portal: string | null;
  user_count: number | null;
}

export function useBitrix24SaveConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { webhook_url: string }): Promise<Bitrix24Status> => {
      const response = await api.post('/integrations/bitrix24/config', data);
      return response.data as Bitrix24Status;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'bitrix24', 'status'] });
    },
  });
}

export function useBitrix24Test() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Bitrix24TestResponse> => {
      const response = await api.post('/integrations/bitrix24/test');
      return response.data as Bitrix24TestResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'bitrix24', 'status'] });
    },
  });
}

export function useBitrix24Disconnect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MessageResult> => {
      const response = await api.post('/integrations/bitrix24/disconnect');
      return response.data as MessageResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'bitrix24', 'status'] });
    },
  });
}
