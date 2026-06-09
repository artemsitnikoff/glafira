import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для умного подбора (openapi не регенерён)
export interface SmartAccessResponse {
  has_access: boolean;
  has_paid_access: boolean;
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
  confirm_cost?: boolean;
  area_id?: string;
  period?: number;
}

export interface SmartSearchResponse {
  run_id: string;
}

export interface SmartRun {
  id: string;
  status: 'running' | 'done' | 'error';
  stage: 'search' | 'eval' | 'finalizing' | 'invite' | 'done';
  found: number;
  scan_n: number;
  scanned: number;
  evaluated: number;
  invited: number;
  error: string | null;
  invites_skipped: boolean;
  invited_candidates: SmartCandidate[];
  scored_candidates: SmartCandidate[];
  passed_threshold: number;
  note: string | null;
  log: string[];
}

export interface SmartRequirementMatch {
  criterion: string;
  weight: number;
  points: number;
  comment?: string;
}

export interface SmartScoredExperience {
  position?: string;
  company?: string;
  period?: string;
  description?: string;
}

export interface SmartScoredResume {
  title?: string;
  total_experience_months?: number;
  city?: string;
  age?: number;
  salary?: string;
  experience: SmartScoredExperience[];
  skills: string[];
  education?: string;
}

export interface SmartCandidate {
  candidate_id: string | null;
  name: string;
  age: number;
  experience_years: number;
  last_company: string;
  city: string;
  score: number;
  verdict: string;
  passed?: boolean;
  summary?: string;
  strengths?: string[];
  risks?: string[];
  forecast?: string;
  requirements_match?: SmartRequirementMatch[];
  resume?: SmartScoredResume;
  hh_resume_id?: string;
  invited?: boolean;
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

export interface SmartVacancyFilters {
  area: string;
  professional_role: string;
  experience: string;
  skills: string[];
}

export interface SmartAreaSuggestItem {
  id: string;
  text: string;
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

export function useDeriveVacancyFilters() {
  return useMutation<SmartVacancyFilters, Error, string>({
    mutationFn: async (vacancyId): Promise<SmartVacancyFilters> => {
      const response = await api.get(`/smart/vacancy-filters/${vacancyId}`);
      return response.data as SmartVacancyFilters;
    },
  });
}

export interface SmartCountRequest {
  vacancy_id: string;
  area?: string;
  professional_role?: string;
  experience?: string;
  skills: string[];
  salary_from?: number;
  salary_to?: number;
  include_no_salary: boolean;
  area_id?: string;
  period?: number;
}

export interface SmartCountResponse {
  found: number | null;
}

export function useSmartCount() {
  return useMutation<SmartCountResponse, Error, SmartCountRequest>({
    mutationFn: async (request): Promise<SmartCountResponse> => {
      const response = await api.post('/smart/preview-count', request);
      return response.data as SmartCountResponse;
    },
  });
}

export function useSmartAreaSuggest(text: string) {
  return useQuery({
    queryKey: ['smart', 'area-suggest', text],
    queryFn: async (): Promise<SmartAreaSuggestItem[]> => {
      const response = await api.get('/smart/area-suggest', { params: { text } });
      return response.data as SmartAreaSuggestItem[];
    },
    enabled: text.trim().length >= 2,
  });
}

export interface SmartInviteResultItem {
  resume_id: string;
  status: 'invited' | 'already' | 'error';
  message?: string;
  candidate_id?: string;
  name?: string;
}

export interface SmartInviteRequest {
  resume_ids: string[];
}

export interface SmartInviteResponse {
  results: SmartInviteResultItem[];
  invited_count: number;
}

export function useSmartInvite(runId: string) {
  return useMutation<SmartInviteResponse, Error, string[]>({
    mutationFn: async (resumeIds): Promise<SmartInviteResponse> => {
      const response = await api.post(`/smart/runs/${runId}/invite`, { resume_ids: resumeIds });
      return response.data as SmartInviteResponse;
    },
  });
}