import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { VerificationOut, ApiError } from '@/api/aliases';

export function useVerification(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'verification'],
    queryFn: async (): Promise<VerificationOut | null> => {
      try {
        return (await api.get<VerificationOut>(`/candidates/${candidateId}/verification`)).data;
      } catch (e) {
        // Верификации ещё нет — это валидное «пусто», не ошибка загрузки.
        if ((e as ApiError)?.error?.code === 'NOT_FOUND') return null;
        throw e;
      }
    },
    enabled: !!candidateId,
  });
}
