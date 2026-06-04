import { useMutation, useQueryClient } from '@tanstack/react-query';
import { client } from '../client';
import type { PlanItemOut, EmployeeDetail } from '../aliases';

export function useDismissAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (alertId: string) => {
      const response = await client.post(`/pulse/alerts/${alertId}/dismiss`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pulse', 'alerts'] });
    },
  });
}

export function useTogglePlanItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ itemId, isDone }: { itemId: string; isDone: boolean }) => {
      const response = await client.patch<PlanItemOut>(`/pulse/plan-items/${itemId}`, {
        is_done: isDone,
      });
      return response.data;
    },
    onSuccess: () => {
      // Invalidate specific employee data to update plan
      queryClient.invalidateQueries({ queryKey: ['pulse', 'employee'] });
    },
  });
}

// Запуск опроса по выбранному шаблону. Возвращает опрос с public_token —
// из него фронт строит публичную ссылку для респондента.
export type LaunchedSurvey = {
  id: string;
  public_token: string | null;
  type: string;
  sent_at: string;
};

export function useRunSurvey() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      employeeId,
      templateId,
    }: {
      employeeId: string;
      templateId: string;
    }) => {
      const response = await client.post<LaunchedSurvey>(
        `/pulse/employees/${employeeId}/surveys`,
        { template_id: templateId }
      );
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['pulse', 'employee', variables.employeeId] });
    },
  });
}

export function useAddNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ employeeId, text }: { employeeId: string; text: string }) => {
      const response = await client.post<EmployeeDetail>(`/pulse/employees/${employeeId}/note`, {
        text,
      });
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['pulse', 'employee', variables.employeeId] });
    },
  });
}

export function useRegenerateAiSummary() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (employeeId: string) => {
      return (await client.post(`/pulse/employees/${employeeId}/ai-summary`)).data;
    },
    onSuccess: (_, employeeId) => {
      queryClient.invalidateQueries({ queryKey: ['pulse', 'employee', employeeId] });
    },
  });
}