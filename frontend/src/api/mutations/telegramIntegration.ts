import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

export interface TgStepResult {
  state: 'pending_code' | 'pending_password' | 'connected';
  user?: { id: string; username?: string | null } | null;
}

const KEY = ['integrations', 'telegram', 'status'];

export function useTgSendCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { phone: string }): Promise<TgStepResult> => {
      const r = await api.post('/integrations/telegram/send-code', data);
      return r.data as TgStepResult;
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: KEY }); },
  });
}

export function useTgConfirmCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { code: string }): Promise<TgStepResult> => {
      const r = await api.post('/integrations/telegram/confirm-code', data);
      return r.data as TgStepResult;
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: KEY }); },
  });
}

export function useTgConfirmPassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { password: string }): Promise<TgStepResult> => {
      const r = await api.post('/integrations/telegram/confirm-password', data);
      return r.data as TgStepResult;
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: KEY }); },
  });
}

export function useTgTest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<{ sent: boolean }> => {
      const r = await api.post('/integrations/telegram/test');
      return r.data as { sent: boolean };
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: KEY }); },
  });
}

export function useTgDisconnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MessageResult> => {
      const r = await api.post('/integrations/telegram/disconnect');
      return r.data as MessageResult;
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: KEY }); },
  });
}
