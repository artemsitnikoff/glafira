import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { TestAssignmentOut, TestDetail, TestCategoryBand } from '@/api/hooks/useTests';

// openapi протух (модуль «Тесты») → локальные тела запросов + as-cast (§3 CLAUDE.md).
// Формы 1:1 из backend/app/schemas/tests.py.

/** Тело POST /applications/{id}/tests/assign. */
export type TestAssignRequest = {
  test_id: string;
  ttl_days: number; // 1..90
  channel?: 'email' | 'telegram' | 'hh' | null; // null → бек подберёт по контактам
  message?: string | null;
};

/** Тело PATCH /tests/{id} (только admin). Поля через model_fields_set — можно очистить в null. */
export type TestUpdateRequest = {
  category_thresholds?: TestCategoryBand[] | null;
  auto_reject_below?: number | null;
  randomize_options?: boolean | null;
  allow_back?: boolean | null;
  status?: 'active' | 'draft' | null;
  blocks?: Array<{ id: string; duration_sec: number }> | null;
};

/**
 * Назначить тест кандидату по заявке. После успеха — обновляем вкладку «Тесты»
 * карточки и воронку (test_status/test_score в ApplicationRow) + Главную.
 */
export function useAssignTest(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TestAssignRequest): Promise<TestAssignmentOut> => {
      const res = await api.post(`/applications/${applicationId}/tests/assign`, body);
      return res.data as TestAssignmentOut;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications', applicationId, 'tests'] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['home'] });
    },
  });
}

/** Переотправить ссылку (тот же токен) по активному назначению. */
export function useRemindTest(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (assignmentId: string): Promise<TestAssignmentOut> => {
      const res = await api.post(
        `/applications/${applicationId}/tests/${assignmentId}/remind`,
      );
      return res.data as TestAssignmentOut;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications', applicationId, 'tests'] });
    },
  });
}

/** Отменить назначение теста (пройденный отменить нельзя — 409). */
export function useCancelTest(applicationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (assignmentId: string): Promise<TestAssignmentOut> => {
      const res = await api.post(
        `/applications/${applicationId}/tests/${assignmentId}/cancel`,
      );
      return res.data as TestAssignmentOut;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications', applicationId, 'tests'] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
    },
  });
}

/** Правка настроек теста (PATCH /tests/{id}) — только admin. */
export function useUpdateTest(testId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TestUpdateRequest): Promise<TestDetail> => {
      const res = await api.patch(`/tests/${testId}`, body);
      return res.data as TestDetail;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tests'] });
      queryClient.invalidateQueries({ queryKey: ['tests', testId] });
    },
  });
}
