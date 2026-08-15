import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';

// API types (соблюдаем контракт точно)
export interface ParseResponse {
  columns: string[];
  samples: Record<string, string[]>;
  row_count: number;
  auto_mapping: Record<string, string>;
}

// Структурные блоки резюме из Потока (приходят в detail у источника 'potok')
export interface PotokExperience {
  position: string;
  company: string | null;
  period: string | null;
  description: string | null;
}
export interface PotokSkill { skill: string }
export interface PotokEducation {
  institution: string;
  specialty: string | null;
  years: string | null;
}

export interface PreviewRow {
  index: number;
  name: string;
  phone: string | null;
  email: string | null;
  city: string | null;
  source: string | null;
  status: 'new' | 'duplicate' | 'error';
  error?: string;
  // detail — супермножество форм Excel и Потока (контракт бека; openapi не регенерён).
  detail: {
    // Форма «Файл» (Excel)
    full_name?: string | null;
    position?: string | null;
    company?: string | null;
    experience?: string | PotokExperience[] | null;
    city?: string | null;
    phone?: string | null;
    email?: string | null;
    source?: string | null;
    comment?: string | null;
    resume_url?: string | null;
    age?: number | null;
    salary?: number | null;
    // Форма «Поток» (структурированное резюме из API)
    first_name?: string | null;
    last_name?: string | null;
    middle_name?: string | null;
    birth_date?: string | null;
    gender?: string | null;
    salary_expectation?: number | null;
    last_position?: string | null;
    source_url?: string | null;
    resume_text?: string | null;
    resume_summary?: string | null;
    skills?: PotokSkill[] | null;
    education?: PotokEducation[] | null;
    languages?: string[] | null;
    external_id?: string | null;
  };
}

export interface PreviewResponse {
  summary: {
    total: number;
    new: number;
    duplicates: number;
    errors: number;
    total_capped?: boolean; // Talantix: превью упёрлось в кап перечисления → база БОЛЬШЕ (рисуем «N+»)
  };
  rows: PreviewRow[];
  shown: number;
  remaining: number;
}

export interface ExecuteResponse {
  job_id: string;
}

export interface ImportJob {
  id: string;
  status: 'running' | 'done' | 'error';
  total: number;
  processed: number;
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  // Комментарии рекрутёров, перенесённые вместе с кандидатами (headline-метрика
  // Talantix). У Excel/Потока = 0. openapi не регенерён — поле локальное, опциональное.
  comments_imported?: number;
  error?: string;
}

export type FieldKey = 'name' | 'phone' | 'email' | 'city' | 'age' | 'salary' | 'source' | 'position' | 'company' | 'experience' | 'comment' | 'resume_url' | 'skip';

export interface ColumnMapping {
  [columnName: string]: FieldKey;
}

export type DedupMode = 'skip' | 'update';

// Hook: парсинг файла
export function useParseFile() {
  return useMutation({
    mutationFn: async (file: File): Promise<ParseResponse> => {
      const formData = new FormData();
      formData.append('file', file);

      const response = await api.post('/candidates/import/parse', formData);
      return response.data;
    },
  });
}

// Hook: превью импорта
export function usePreviewImport() {
  return useMutation({
    mutationFn: async ({
      file,
      mapping,
      dedup_mode,
    }: {
      file: File;
      mapping: ColumnMapping;
      dedup_mode: DedupMode;
    }): Promise<PreviewResponse> => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('mapping', JSON.stringify(mapping));
      formData.append('dedup_mode', dedup_mode);

      const response = await api.post('/candidates/import/preview', formData);
      return response.data;
    },
  });
}

// Hook: выполнение импорта
export function useExecuteImport() {
  return useMutation({
    mutationFn: async ({
      file,
      mapping,
      dedup_mode,
    }: {
      file: File;
      mapping: ColumnMapping;
      dedup_mode: DedupMode;
    }): Promise<ExecuteResponse> => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('mapping', JSON.stringify(mapping));
      formData.append('dedup_mode', dedup_mode);

      const response = await api.post('/candidates/import/execute', formData);
      return response.data;
    },
  });
}

// Hook: статус задачи импорта
export function useImportJob(jobId: string | null, enabled: boolean = true) {
  return useQuery({
    queryKey: ['import-job', jobId],
    queryFn: async (): Promise<ImportJob> => {
      if (!jobId) throw new Error('Job ID required');
      const response = await api.get(`/candidates/import/jobs/${jobId}`);
      return response.data;
    },
    enabled: enabled && !!jobId,
    // Поллим 1200мс ПОКА импорт идёт; после done/error — стоп (не долбим эндпоинт).
    refetchInterval: (query) =>
      query.state.data && query.state.data.status === 'running' ? 1200 : false,
    refetchIntervalInBackground: false,
  });
}

// Hook: превью импорта из Потока
export function usePreviewPotokImport() {
  return useMutation({
    mutationFn: async ({
      token,
      dedup_mode,
    }: {
      token: string;
      dedup_mode: DedupMode;
    }): Promise<PreviewResponse> => {
      const response = await api.post('/candidates/import/potok/preview', {
        token,
        dedup_mode,
      });
      return response.data;
    },
  });
}

// Hook: выполнение импорта из Потока
export function useExecutePotokImport() {
  return useMutation({
    mutationFn: async ({
      token,
      dedup_mode,
    }: {
      token: string;
      dedup_mode: DedupMode;
    }): Promise<ExecuteResponse> => {
      const response = await api.post('/candidates/import/potok/execute', {
        token,
        dedup_mode,
      });
      return response.data;
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Talantix (импорт из ATS Talantix). Контракт бека: /candidates/import/talantix/*.
// openapi протух → локальные типы + as-cast. Отличие от Потока: токен(ы)
// передаются один раз в /connect (хранятся на сервере, наружу НЕ возвращаются),
// а preview/execute токен уже не принимают.
// ─────────────────────────────────────────────────────────────────────────
export interface TalantixStatus {
  connected: boolean;
  connected_at: string | null;
  expires_at: string | null;
}

// Hook: подключение Talantix. Пользователь вставляет ВЕСЬ JSON со страницы токена
// ЛК Talantix (или сам refresh_token) — шлём одной строкой в поле token, бек парсит.
// (Страница токена — SPA, «вставить ссылку» не сработает, поэтому именно JSON.)
export function useTalantixConnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ token }: { token: string }): Promise<TalantixStatus> => {
      const response = await api.post('/candidates/import/talantix/connect', { token });
      return response.data as TalantixStatus;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['talantix-status'] });
    },
  });
}

// Hook: статус подключения Talantix
export function useTalantixStatus(enabled: boolean = true) {
  return useQuery({
    queryKey: ['talantix-status'],
    queryFn: async (): Promise<TalantixStatus> => {
      const response = await api.get('/candidates/import/talantix/status');
      return response.data as TalantixStatus;
    },
    enabled,
    staleTime: 0,
  });
}

// Hook: превью импорта из Talantix (токен уже сохранён на сервере через connect)
export function useTalantixPreview() {
  return useMutation({
    mutationFn: async ({
      dedup_mode,
    }: {
      dedup_mode: DedupMode;
    }): Promise<PreviewResponse> => {
      const response = await api.post('/candidates/import/talantix/preview', {
        dedup_mode,
      });
      return response.data as PreviewResponse;
    },
  });
}

// Hook: выполнение импорта из Talantix
export function useTalantixExecute() {
  return useMutation({
    mutationFn: async ({
      dedup_mode,
    }: {
      dedup_mode: DedupMode;
    }): Promise<ExecuteResponse> => {
      const response = await api.post('/candidates/import/talantix/execute', {
        dedup_mode,
      });
      return response.data as ExecuteResponse;
    },
  });
}