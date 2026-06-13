import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { MangoStatus } from '../hooks/useMangoIntegration';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

// Локальные типы (openapi не регенерён)
export interface MangoConfigRequest {
  api_key?: string;
  api_salt?: string;
  vpbx_api_url?: string;
}

export interface MangoTestResponse {
  vpbx_api_url: string;
  last_test_at: string;
}

export function useMangoSaveConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: MangoConfigRequest): Promise<MangoStatus> => {
      const response = await api.post('/integrations/mango/config', data);
      return response.data as MangoStatus;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'mango', 'status'] });
    },
  });
}

export function useMangoTest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MangoTestResponse> => {
      const response = await api.post('/integrations/mango/test');
      return response.data as MangoTestResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'mango', 'status'] });
    },
  });
}

export function useMangoDisconnect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MessageResult> => {
      const response = await api.post('/integrations/mango/disconnect');
      return response.data as MessageResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'mango', 'status'] });
    },
  });
}