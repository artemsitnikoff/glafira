import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для SMTP-интеграции (openapi не регенерён)
export interface SmtpStatus {
  configured: boolean;
  verified: boolean;
  host?: string | null;
  port?: number | null;
  encryption?: 'tls' | 'ssl' | 'none' | null;
  username?: string | null;
  from_email?: string | null;
  from_name?: string | null;
  reply_to?: string | null;
  last_test_at?: string | null;
  last_test_ok?: boolean;
  last_test_error?: string | null;
}

export function useSmtpStatus() {
  return useQuery({
    queryKey: ['integrations', 'smtp', 'status'],
    queryFn: async (): Promise<SmtpStatus> => {
      const response = await api.get('/integrations/smtp/status');
      return response.data as SmtpStatus;
    },
  });
}
