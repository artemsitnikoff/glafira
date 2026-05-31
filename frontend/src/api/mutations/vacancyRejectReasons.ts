import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// CRUD причин отказа вакансии (/vacancies/{id}/reject-reasons). Контракт 1:1 с беком
// (RejectReasonCreate/Update). Системную причину бэк удалять не даёт (400).
const key = (vacancyId: string) => ['vacancy', vacancyId, 'reject-reasons'];

export function useAddVacancyRejectReason(vacancyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { side: 'candidate' | 'company'; label: string; order_index?: number }) => {
      const res = await api.post(`/vacancies/${vacancyId}/reject-reasons`, data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key(vacancyId) }),
  });
}

export function useUpdateVacancyRejectReason(vacancyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, label }: { id: string; label: string }) => {
      const res = await api.patch(`/vacancies/${vacancyId}/reject-reasons/${id}`, { label });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key(vacancyId) }),
  });
}

export function useDeleteVacancyRejectReason(vacancyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await api.delete(`/vacancies/${vacancyId}/reject-reasons/${id}`);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key(vacancyId) }),
  });
}
