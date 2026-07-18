/**
 * Хуки модуля «Заявки на подбор».
 * openapi не регенерён → локальные типы (зеркало backend/app/schemas/hiring_request.py).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';

export type RequestStatus = 'new' | 'work' | 'sourcing' | 'done' | 'rejected' | string;

export interface RequestProgress {
  vacancy_id: string;
  vacancy_name: string;
  candidates: number;
  new_count: number;
  hired: number;
  positions: number;
}

export interface RequestListItem {
  id: string;
  num: number;
  title: string;
  department: string | null;
  city: string | null;
  positions: number;
  deadline: string | null;
  priority: 'normal' | 'high';
  status: RequestStatus;
  via: 'cabinet' | 'form' | 'manual';
  author_name: string | null;
  author_role: string | null;
  created_at: string;
  progress: RequestProgress | null;
}

export interface RequestComment {
  id: string;
  side: 'recruiter' | 'manager';
  author_name: string | null;
  author_user_id: string | null;
  body: string;
  created_at: string;
}

export interface RequestHistoryItem {
  label: string;
  at: string;
}

export interface RequestDetail extends RequestListItem {
  description: string;
  salary_from: number | null;
  salary_to: number | null;
  employment_format: string | null;
  author_contact: string | null;
  author_user_id: string | null;
  vacancy_id: string | null;
  vacancy_name: string | null;
  reject_reason: string | null;
  closed_note: string | null;
  comments: RequestComment[];
  history: RequestHistoryItem[];
}

export interface RequestStage {
  key: string;
  label: string;
  color: string;
  system: boolean;
  terminal: boolean;
  custom: boolean;
  description: string | null;
}

export interface RequestCreateBody {
  title: string;
  description: string;
  department?: string | null;
  city?: string | null;
  positions?: number;
  deadline?: string | null;
  salary_from?: number | null;
  salary_to?: number | null;
  employment_format?: 'office' | 'hybrid' | 'remote' | null;
  priority?: 'normal' | 'high';
  author_name?: string | null;
  author_role?: string | null;
  author_contact?: string | null;
}

export interface RequestSettings {
  autoclose_on: boolean;
  question_moves_to_work: boolean;
  notify_manager_on_stage: boolean;
  form_enabled: boolean;
}

export interface RequestFormLink {
  url: string | null;
  enabled: boolean;
}

// ── Списки/деталь ─────────────────────────────────────────────────────────────
export function useRequests(params: { status?: string; query?: string } = {}) {
  return useQuery({
    queryKey: ['requests', params.status ?? 'all', params.query ?? ''],
    queryFn: async () => {
      const res = await api.get<{ items: RequestListItem[]; total: number }>('/requests', {
        params: { status: params.status || undefined, query: params.query || undefined },
      });
      return res.data;
    },
    refetchInterval: 30_000,
  });
}

export function useRequest(id: string | undefined) {
  return useQuery({
    queryKey: ['requests', 'detail', id],
    queryFn: async () => (await api.get<RequestDetail>(`/requests/${id}`)).data,
    enabled: !!id,
    refetchInterval: 15_000,
  });
}

export function useRequestsSidebar() {
  return useQuery({
    queryKey: ['requests', 'sidebar'],
    queryFn: async () => (await api.get<{ active: number; new: number }>('/requests/sidebar')).data,
    refetchInterval: 30_000,
  });
}

export function useRequestStages() {
  return useQuery({
    queryKey: ['requests', 'stages'],
    queryFn: async () => (await api.get<RequestStage[]>('/requests/stages')).data,
    staleTime: 60_000,
  });
}

// ── Мутации ───────────────────────────────────────────────────────────────────
function invalidate(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['requests'] });
}

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: RequestCreateBody) =>
      (await api.post<RequestDetail>('/requests', body)).data,
    onSuccess: () => invalidate(qc),
  });
}

export function useMoveRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, target }: { id: string; target: string }) =>
      (await api.patch<RequestDetail>(`/requests/${id}/move`, { target })).data,
    onSuccess: () => invalidate(qc),
  });
}

export function useRejectRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string }) =>
      (await api.post<RequestDetail>(`/requests/${id}/reject`, { reason })).data,
    onSuccess: () => invalidate(qc),
  });
}

export function useRestoreRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      (await api.post<RequestDetail>(`/requests/${id}/restore`)).data,
    onSuccess: () => invalidate(qc),
  });
}

export function useCloseRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, note }: { id: string; note?: string }) =>
      (await api.post<RequestDetail>(`/requests/${id}/close`, { note })).data,
    onSuccess: () => invalidate(qc),
  });
}

export function useAddRequestComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: string }) =>
      (await api.post<RequestDetail>(`/requests/${id}/comments`, { body })).data,
    onSuccess: () => invalidate(qc),
  });
}

// ── Настройки / воронка / ссылка формы (admin) ──────────────────────────────
export function useRequestSettings(enabled = true) {
  return useQuery({
    queryKey: ['requests', 'settings'],
    queryFn: async () => (await api.get<RequestSettings>('/requests/settings')).data,
    enabled,
  });
}

export function usePatchRequestSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Partial<RequestSettings>) =>
      (await api.patch<RequestSettings>('/requests/settings', body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests', 'settings'] }),
  });
}

export function useRequestFormLink(enabled = true) {
  return useQuery({
    queryKey: ['requests', 'form-link'],
    queryFn: async () => (await api.get<RequestFormLink>('/requests/form-link')).data,
    enabled,
  });
}

export function useRotateFormLink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<RequestFormLink>('/requests/form-link/rotate')).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests', 'form-link'] }),
  });
}

export function useCreateRequestStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { label: string; description?: string | null }) =>
      (await api.post<RequestStage[]>('/requests/funnel-stages', body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests', 'stages'] }),
  });
}

export function useUpdateRequestStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, ...body }: { key: string; label?: string; description?: string | null }) =>
      (await api.patch<RequestStage[]>(`/requests/funnel-stages/${key}`, body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests', 'stages'] }),
  });
}

export function useDeleteRequestStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (key: string) =>
      (await api.delete<RequestStage[]>(`/requests/funnel-stages/${key}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests', 'stages'] }),
  });
}
