import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { RejectReasonOut } from './useRejectReasons';

// Причины отказа, привязанные к вакансии (GET /vacancies/{id}/reject-reasons).
// Бэк при пустоте копирует дефолты компании (инвариант непустоты).
export function useVacancyRejectReasons(vacancyId: string | undefined) {
  return useQuery({
    queryKey: ['vacancy', vacancyId, 'reject-reasons'],
    queryFn: async () => {
      const response = await api.get(`/vacancies/${vacancyId}/reject-reasons`);
      return response.data as RejectReasonOut[];
    },
    enabled: !!vacancyId,
    staleTime: 60_000,
  });
}
