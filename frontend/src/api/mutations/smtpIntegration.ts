import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { SmtpStatus } from '../hooks/useSmtpIntegration';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

// Локальные типы (openapi не регенерён)
export interface SmtpConfigRequest {
  host: string;
  port: number;
  encryption: string;
  username: string;
  password: string; // пусто = сохранить существующий
  from_email: string;
  from_name: string;
  reply_to: string;
}

export interface SmtpTestResponse {
  sent_to: string;
  last_test_at: string;
}

export function useSmtpSaveConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: SmtpConfigRequest): Promise<SmtpStatus> => {
      const response = await api.post('/integrations/smtp/config', data);
      return response.data as SmtpStatus;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'smtp', 'status'] });
    },
  });
}

export function useSmtpTest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { to: string }): Promise<SmtpTestResponse> => {
      const response = await api.post('/integrations/smtp/test', data);
      return response.data as SmtpTestResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'smtp', 'status'] });
    },
  });
}

export function useSmtpDisconnect() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MessageResult> => {
      const response = await api.post('/integrations/smtp/disconnect');
      return response.data as MessageResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'smtp', 'status'] });
    },
  });
}
