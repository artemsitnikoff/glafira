import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { Bitrix24Status } from '../hooks/useBitrix24Integration';
import type { components } from '@/api/types';

type MessageResult = components['schemas']['MessageResult'];

export interface Bitrix24TestResponse {
  portal: string | null;
  user_count: number | null;
}

// Результат импорта сотрудников из Б24 (openapi не регенерён)
export interface Bitrix24ImportEmployeesResult {
  created: number;
  updated: number;
  marked_left: number;
  total: number;
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

export function useBitrix24ImportEmployees() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Bitrix24ImportEmployeesResult> => {
      const response = await api.post('/integrations/bitrix24/import-employees');
      return response.data as Bitrix24ImportEmployeesResult;
    },
    onSuccess: () => {
      // Импорт сотрудников меняет Пульс/«Текучку» — инвалидируем смежные кэши
      queryClient.invalidateQueries({ queryKey: ['pulse'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
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

export interface B24SchedulePatch {
  work_days?: number[];
  work_start?: string;
  work_end?: string;
  duration_min?: number;
  step_min?: number;
  horizon_days?: number;
  lead_hours?: number;
  tz?: string;
  interview_video_link?: string;
}

export function usePatchB24Schedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: B24SchedulePatch) => {
      const response = await api.patch('/integrations/bitrix24/schedule-settings', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'bitrix24', 'schedule-settings'] });
    },
  });
}

// Массовый авто-подбор b24_user_id по email для ВСЕХ пользователей компании (временная кнопка)
export interface MapAllB24Result {
  mapped: number;
  unmatched: string[];
  total_b24_users: number;
}
export function useMapAllB24Users() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<MapAllB24Result> => {
      const response = await api.post('/integrations/bitrix24/users/map-all');
      return response.data as MapAllB24Result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}
