import { useQuery, useMutation } from '@tanstack/react-query';
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

// QR-flow типы (новые эндпоинты qr/start + qr/status)
export interface TelegramQrStartResult {
  qr_image: string;   // data:image/svg+xml;base64,…
  expires: number;    // epoch int
}

export type TelegramQrState = 'idle' | 'waiting' | 'need_password' | 'connected';

export interface TelegramQrStatus {
  state: TelegramQrState;
  qr_image?: string;  // обновлённый QR (если QR обновился на waiting)
  expires?: number;
  user?: { id?: string; username?: string | null; first_name?: string | null } | null;
}

const TG_STATUS_KEY = ['integrations', 'telegram', 'status'];

export function useTelegramStatus() {
  return useQuery({
    queryKey: TG_STATUS_KEY,
    queryFn: async (): Promise<TelegramStatus> => {
      const response = await api.get('/integrations/telegram/status');
      return response.data as TelegramStatus;
    },
  });
}

// POST /integrations/telegram/qr/start — запустить QR-логин
export function useTelegramQrStart() {
  return useMutation({
    mutationFn: async (): Promise<TelegramQrStartResult> => {
      const r = await api.post('/integrations/telegram/qr/start');
      return r.data as TelegramQrStartResult;
    },
  });
}

// GET /integrations/telegram/qr/status — поллинг статуса QR-логина
export function useTelegramQrStatus(enabled: boolean) {
  return useQuery<TelegramQrStatus>({
    queryKey: ['integrations', 'telegram', 'qr', 'status'],
    queryFn: async (): Promise<TelegramQrStatus> => {
      const r = await api.get('/integrations/telegram/qr/status');
      return r.data as TelegramQrStatus;
    },
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 3000;
      if (data.state === 'connected' || data.state === 'need_password') return false;
      return 3000;
    },
  });
}
