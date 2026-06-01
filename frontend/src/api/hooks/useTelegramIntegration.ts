import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для Telegram-интеграции (openapi не регенерён)
export interface TelegramStatus {
  configured: boolean;
  connected: boolean;
  state?: 'pending_code' | 'pending_password' | 'connected' | 'disconnected' | null;
  phone?: string | null;
  tg_username?: string | null;
  code_type?: string | null; // SentCodeTypeApp | ...Sms | ...Call | ...
  last_test_at?: string | null;
  last_test_ok?: boolean;
  last_test_error?: string | null;
}

export function useTelegramStatus() {
  return useQuery({
    queryKey: ['integrations', 'telegram', 'status'],
    queryFn: async (): Promise<TelegramStatus> => {
      const response = await api.get('/integrations/telegram/status');
      return response.data as TelegramStatus;
    },
  });
}
