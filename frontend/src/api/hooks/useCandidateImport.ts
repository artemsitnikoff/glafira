import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../client';

// API types (соблюдаем контракт точно)
export interface ParseResponse {
  columns: string[];
  samples: Record<string, string[]>;
  row_count: number;
  auto_mapping: Record<string, string>;
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
  detail: {
    full_name: string | null;
    position: string | null;
    company: string | null;
    experience: string | null;
    city: string | null;
    phone: string | null;
    email: string | null;
    source: string | null;
    comment: string | null;
    resume_url: string | null;
    age: number | null;
    salary: number | null;
  };
}

export interface PreviewResponse {
  summary: {
    total: number;
    new: number;
    duplicates: number;
    errors: number;
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