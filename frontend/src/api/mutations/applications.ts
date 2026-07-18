import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type MoveRequest = components['schemas']['MoveRequest'];
type RejectRequest = components['schemas']['RejectRequest'];
type BulkMoveRequest = components['schemas']['BulkMoveRequest'];
type BulkRejectRequest = components['schemas']['BulkRejectRequest'];

export function useMoveApplication(vacancyId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: MoveRequest }) => {
      const response = await api.post(`/applications/${id}/move`, data);
      return response.data;
    },
    onSuccess: () => {
      if (vacancyId) {
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'applications'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      }
      // Лента «Все действия» / KPI на Главной зависят от move/reject/restore
      queryClient.invalidateQueries({ queryKey: ['home'] });
      // Счётчики вакансий в сайдбаре (кандидатов/новых) — иначе висят старыми до 30-сек поллинга.
      queryClient.invalidateQueries({ queryKey: ['vacancies', 'sidebar'] });
      // Наём (move→hired) может авто-закрыть связанную заявку — обновим её счётчики/список.
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });
}

export function useRejectApplication(vacancyId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: RejectRequest }) => {
      const response = await api.post(`/applications/${id}/reject`, data);
      return response.data;
    },
    onSuccess: () => {
      if (vacancyId) {
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'applications'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      }
      // Лента «Все действия» / KPI на Главной зависят от move/reject/restore
      queryClient.invalidateQueries({ queryKey: ['home'] });
      // Счётчики вакансий в сайдбаре (кандидатов/новых) — иначе висят старыми до 30-сек поллинга.
      queryClient.invalidateQueries({ queryKey: ['vacancies', 'sidebar'] });
      // Наём (move→hired) может авто-закрыть связанную заявку — обновим её счётчики/список.
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });
}

export function useRestoreApplication(vacancyId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const response = await api.post(`/applications/${id}/restore`);
      return response.data;
    },
    onSuccess: () => {
      if (vacancyId) {
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'applications'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      }
      // Лента «Все действия» / KPI на Главной зависят от move/reject/restore
      queryClient.invalidateQueries({ queryKey: ['home'] });
      // Счётчики вакансий в сайдбаре (кандидатов/новых) — иначе висят старыми до 30-сек поллинга.
      queryClient.invalidateQueries({ queryKey: ['vacancies', 'sidebar'] });
      // Наём (move→hired) может авто-закрыть связанную заявку — обновим её счётчики/список.
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });
}

export function useBulkMove(vacancyId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: BulkMoveRequest) => {
      const response = await api.post('/applications/bulk/move', data);
      return response.data;
    },
    onSuccess: () => {
      if (vacancyId) {
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'applications'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      }
      // Лента «Все действия» / KPI на Главной зависят от move/reject/restore
      queryClient.invalidateQueries({ queryKey: ['home'] });
      // Счётчики вакансий в сайдбаре (кандидатов/новых) — иначе висят старыми до 30-сек поллинга.
      queryClient.invalidateQueries({ queryKey: ['vacancies', 'sidebar'] });
      // Наём (move→hired) может авто-закрыть связанную заявку — обновим её счётчики/список.
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });
}

export function useBulkReject(vacancyId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: BulkRejectRequest) => {
      const response = await api.post('/applications/bulk/reject', data);
      return response.data;
    },
    onSuccess: () => {
      if (vacancyId) {
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'applications'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies', vacancyId, 'stages'] });
      }
      // Лента «Все действия» / KPI на Главной зависят от move/reject/restore
      queryClient.invalidateQueries({ queryKey: ['home'] });
      // Счётчики вакансий в сайдбаре (кандидатов/новых) — иначе висят старыми до 30-сек поллинга.
      queryClient.invalidateQueries({ queryKey: ['vacancies', 'sidebar'] });
      // Наём (move→hired) может авто-закрыть связанную заявку — обновим её счётчики/список.
      queryClient.invalidateQueries({ queryKey: ['requests'] });
    },
  });
}