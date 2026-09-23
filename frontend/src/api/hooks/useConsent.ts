import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { ApiError } from '@/api/aliases';

// GET /candidates/{id}/consent. Сгенерённый ConsentOut ещё без signed_by (openapi
// отстаёт) — описываем локально + as-cast. Контракт сверен с бэкендом v1.9.0.
export type ConsentStatus = {
  id: string;
  candidate_id: string;
  number: string;
  status: 'pending' | 'signed' | 'revoked' | string;
  channel: string | null;
  signed_at: string | null;
  requested_at: string | null;
  signed_by?: 'candidate' | 'recruiter' | null;
};

/**
 * Актуальный снимок последнего согласия кандидата (подписано / ждём подписи).
 * Гейт верификации по-прежнему открывается по has_pdn; этот запрос нужен блоку
 * согласия таба Верификация, чтобы показать «подписано онлайн», пока has_pdn
 * не подтянулся. Нет согласия (404 NOT_FOUND) — валидное «пусто», не ошибка.
 */
export function useConsentStatus(candidateId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'consent'],
    queryFn: async (): Promise<ConsentStatus | null> => {
      try {
        return (await api.get(`/candidates/${candidateId}/consent`)).data as ConsentStatus;
      } catch (e) {
        if ((e as ApiError)?.error?.code === 'NOT_FOUND') return null;
        throw e;
      }
    },
    enabled: !!candidateId && enabled,
  });
}
