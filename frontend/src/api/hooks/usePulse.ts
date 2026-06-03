import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { client } from '../client';
import type { PulseKPI, EmployeeListItem, EmployeeDetail, AlertOut, Paginated } from '../aliases';

export function usePulseKpi(period: string = '30d') {
  return useQuery({
    queryKey: ['pulse', 'kpi', period],
    queryFn: async () => {
      const response = await client.get<PulseKPI>(`/pulse/kpi?period=${period}`);
      return response.data;
    },
  });
}

type EmployeeFilters = {
  page?: number;
  page_size?: number;
  manager_user_id?: string;
  department?: string;
  risk_level?: string;
  status?: string;
  q?: string;
};

export function usePulseEmployees(filters: EmployeeFilters = {}) {
  const params = new URLSearchParams();

  if (filters.page) params.set('page', String(filters.page));
  if (filters.page_size) params.set('page_size', String(filters.page_size));
  if (filters.manager_user_id) params.set('manager_user_id', filters.manager_user_id);
  if (filters.department) params.set('department', filters.department);
  if (filters.risk_level) params.set('risk_level', filters.risk_level);
  if (filters.status) params.set('status', filters.status);
  if (filters.q) params.set('q', filters.q);

  return useQuery({
    queryKey: ['pulse', 'employees', filters],
    queryFn: async () => {
      const response = await client.get<Paginated<EmployeeListItem>>(`/pulse/employees?${params}`);
      return response.data;
    },
  });
}

export function usePulseEmployee(id: string | undefined) {
  return useQuery({
    queryKey: ['pulse', 'employee', id],
    queryFn: async () => {
      const response = await client.get<EmployeeDetail>(`/pulse/employees/${id}`);
      return response.data;
    },
    enabled: !!id,
  });
}

type AlertFilters = {
  dismissed?: boolean | null;
  period_days?: number | null;
};

export function usePulseAlerts(filters: AlertFilters = {}) {
  const params = new URLSearchParams();

  if (filters.dismissed !== undefined && filters.dismissed !== null) {
    params.set('dismissed', String(filters.dismissed));
  }
  if (filters.period_days !== undefined && filters.period_days !== null) {
    params.set('period_days', String(filters.period_days));
  }

  return useQuery({
    queryKey: ['pulse', 'alerts', filters],
    queryFn: async () => {
      const response = await client.get<AlertOut[]>(`/pulse/alerts?${params}`);
      return response.data;
    },
  });
}

// Шаблоны опросов из настроек
export function useSurveyTemplates() {
  return useQuery({
    queryKey: ['survey-templates'],
    queryFn: async () => {
      const response = await client.get(`/settings/survey-templates`);
      return response.data;
    },
  });
}

// Создать стандартные шаблоны опросов адаптации (день 7/30/90), если их ещё нет
export function useProvisionSurveyDefaults() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await client.post('/settings/survey-templates/defaults');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['survey-templates'] });
    },
  });
}

// Массовый запуск опросов
export function useBulkRunSurvey() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ employee_ids, template_key }: { employee_ids: string[], template_key: string }) => {
      const response = await client.post('/pulse/employees/bulk/run-survey', {
        employee_ids,
        template_key
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pulse', 'employees'] });
    },
  });
}