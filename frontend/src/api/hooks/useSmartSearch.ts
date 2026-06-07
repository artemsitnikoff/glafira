import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для умного подбора (openapi не регенерён)
export interface SmartAccessResponse {
  has_access: boolean;
  reason: string | null;
}

export interface SmartVacancy {
  id: string;
  title: string;
  city: string | null;
  area: string | null;
  professional_role: string | null;
  experience: string | null;
  salary_from: number | null;
  salary_to: number | null;
  skills: string[];
  found: number | null;
  hh_published: boolean;
}

export interface SmartSearchRequest {
  vacancy_id: string;
  area?: string;
  professional_role?: string;
  experience?: string;
  skills: string[];
  salary_from?: number;
  salary_to?: number;
  include_no_salary: boolean;
  scan_n: number; // 1..400
  invite_m: number; // 1..100
  threshold: number; // 0..100
}

export interface SmartSearchResponse {
  run_id: string;
}

export interface SmartRun {
  id: string;
  status: 'running' | 'done' | 'error';
  stage: 'search' | 'eval' | 'invite' | 'done';
  found: number;
  scanned: number;
  evaluated: number;
  invited: number;
  error: string | null;
  invited_candidates: SmartCandidate[];
}

export interface SmartCandidate {
  candidate_id: string;
  name: string;
  age: number;
  experience_years: number;
  last_company: string;
  city: string;
  score: number;
  verdict: string;
}

export interface SmartHistoryItem {
  id: string;
  vacancy_id: string;
  vacancy_title: string;
  created_at: string;
  found: number;
  evaluated: number;
  invited: number;
}

export function useSmartAccess() {
  return useQuery({
    queryKey: ['smart', 'access'],
    queryFn: async (): Promise<SmartAccessResponse> => {
      const response = await api.get('/smart/access');
      return response.data as SmartAccessResponse;
    },
  });
}

export function useSmartVacancies() {
  return useQuery({
    queryKey: ['smart', 'vacancies'],
    queryFn: async (): Promise<SmartVacancy[]> => {
      const response = await api.get('/smart/vacancies');
      return response.data as SmartVacancy[];
    },
  });
}

export function useStartSmartSearch() {
  return useMutation<SmartSearchResponse, Error, SmartSearchRequest>({
    mutationFn: async (request): Promise<SmartSearchResponse> => {
      const response = await api.post('/smart/search', request);
      return response.data as SmartSearchResponse;
    },
  });
}

export function useSmartRun(runId: string | null, enabled: boolean = true) {
  return useQuery({
    queryKey: ['smart', 'runs', runId],
    queryFn: async (): Promise<SmartRun> => {
      const response = await api.get(`/smart/runs/${runId}`);
      return response.data as SmartRun;
    },
    enabled: enabled && runId !== null,
    refetchInterval: (data) => {
      // Поллинг каждые 1500мс ПОКА status === 'running'
      return data?.state?.data && data.state.data.status === 'running' ? 1500 : false;
    },
  });
}

export function useSmartHistory() {
  return useQuery({
    queryKey: ['smart', 'runs'],
    queryFn: async (): Promise<SmartHistoryItem[]> => {
      const response = await api.get('/smart/runs');
      return response.data as SmartHistoryItem[];
    },
  });
}