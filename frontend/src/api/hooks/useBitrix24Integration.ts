import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для Битрикс24-интеграции (openapi не регенерён)
export interface Bitrix24Status {
  configured: boolean;
  verified: boolean;
  portal?: string | null;
  user_count?: number | null;
  last_test_at?: string | null;
  last_test_ok?: boolean;
  last_test_error?: string | null;
}

export interface B24ScheduleSettings {
  work_days: number[];        // 1=пн..7=вс (на беке), мы храним 0=пн..6=вс
  work_start: string;         // "HH:MM"
  work_end: string;           // "HH:MM"
  duration_min: number;
  step_min: number;
  horizon_days: number;
  lead_hours: number;
  tz: string;
  interview_video_link: string;
}

export function useBitrix24Status() {
  return useQuery({
    queryKey: ['integrations', 'bitrix24', 'status'],
    queryFn: async (): Promise<Bitrix24Status> => {
      const response = await api.get('/integrations/bitrix24/status');
      return response.data as Bitrix24Status;
    },
  });
}

export function useB24ScheduleSettings(enabled: boolean) {
  return useQuery({
    queryKey: ['integrations', 'bitrix24', 'schedule-settings'],
    queryFn: async (): Promise<B24ScheduleSettings> => {
      const response = await api.get('/integrations/bitrix24/schedule-settings');
      return response.data as B24ScheduleSettings;
    },
    enabled,
  });
}
