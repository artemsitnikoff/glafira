import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';

// Локальные типы для умного подбора (openapi не регенерён — skill_chips/skill_mode добавлены
// локально, соответствуют схеме v0.9.99 бека; openapi регенерировать при наличии живого сервера)
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

// Навык из справочника hh с id (структурный фильтр, v0.9.99)
// openapi не регенерён — локальный тип + as-cast
export interface SmartSkillChip {
  id: string;
  text: string;
}

export interface SmartSearchRequest {
  vacancy_id: string;
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
  // v0.9.99: структурный фильтр навыков hh (openapi не регенерён — локальные типы)
  skill_chips?: SmartSkillChip[];
  skill_mode?: 'exact' | 'soft';
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
  passed: number;
}

export interface SmartVacancyFilters {
  area: string;
  professional_role: string;
  experience: string;
  skills: string[];
  city?: string;
  salary_from?: number | null;
  salary_to?: number | null;
  // v0.9.99: навыки, резолвленные Глафирой в id справочника hh (openapi не регенерён)
  skill_chips?: SmartSkillChip[];
}

export interface SmartAreaSuggestItem {
  id: string;
  text: string;
}

export interface SmartRoleSuggestItem {
  id: string;
  name: string;
  category: string | null;
}

export interface SmartRoleCategoryItem {
  id: string;
  name: string;
}

export interface SmartRoleCategory {
  category_id: string;
  category: string;
  roles: SmartRoleCategoryItem[];
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
  professional_role?: string;
  experience?: string;
  skills: string[];
  salary_from?: number;
  salary_to?: number;
  include_no_salary: boolean;
  area_id?: string;
  period?: number;
  // v0.9.99: структурный фильтр навыков hh (openapi не регенерён — локальные типы)
  skill_chips?: SmartSkillChip[];
  skill_mode?: 'exact' | 'soft';
}

// Тип debug_params v0.9.96 — новая форма (openapi не регенерён; локальный тип + as-cast)
export interface SmartDebugTextBlock {
  text: string;
  field?: string;    // "everywhere" (роль) | "skills" (навыки)
  logic?: string;    // "any"
  period?: string;   // "all_time"
  label: string;     // "роль" | "навыки"
}

export interface SmartDebugStructural {
  area?: string;
  professional_role?: string;
  experience?: string;
  salary_from?: string;
  salary_to?: string;
  only_with_salary?: string;
  period?: string;
}

export interface SmartDebugParams {
  structural: SmartDebugStructural;
  text_blocks: SmartDebugTextBlock[];
  // v0.9.99: навыки, ушедшие как структурный skill= фильтр (только в режиме exact)
  // openapi не регенерён — локальный тип + as-cast
  skill_filter?: SmartSkillChip[];
}

export interface SmartCountResponse {
  found: number | null;
  debug_params: SmartDebugParams | null;
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

export function useSmartRoleSuggest(text: string) {
  return useQuery({
    queryKey: ['smart', 'role-suggest', text],
    queryFn: async (): Promise<SmartRoleSuggestItem[]> => {
      const response = await api.get('/smart/role-suggest', { params: { text } });
      return response.data as SmartRoleSuggestItem[];
    },
    enabled: text.trim().length >= 2,
  });
}

// v0.9.99: подсказки навыков из справочника hh (зеркало useSmartRoleSuggest)
// openapi не регенерён — локальный тип SmartSkillChip + as-cast
export function useSmartSkillSuggest(text: string) {
  return useQuery({
    queryKey: ['smart', 'skill-suggest', text],
    queryFn: async (): Promise<SmartSkillChip[]> => {
      const response = await api.get('/smart/skill-suggest', { params: { text } });
      return response.data as SmartSkillChip[];
    },
    enabled: text.trim().length >= 2,
  });
}

export function useRoleCategories() {
  return useQuery({
    queryKey: ['smart', 'role-categories'],
    queryFn: async (): Promise<SmartRoleCategory[]> => {
      const response = await api.get('/smart/role-categories');
      return response.data as SmartRoleCategory[];
    },
    staleTime: 24 * 60 * 60 * 1000, // 24ч — справочник статичный
    gcTime: 48 * 60 * 60 * 1000,
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

// === ВЕТКА Б: Умный подбор по своей базе ===

export interface BaseSearchCandidate {
  id: string;
  full_name: string;
  age: number | null;
  last_position: string | null;
  last_company: string | null;
  last_period: string | null; // стаж/tenure
  city: string | null;
  ai_score: number | null;
  source: string;
  salary_expectation: number | null;
  matched_skills: string[];
  all_skills: string[];
  match_percent: number | null;
  has_pdn: boolean;
  scored_by: 'cosine' | 'ai';
}

export interface BaseSearchRequest {
  search_type: 'prompt' | 'vacancy';
  query?: string;
  vacancy_id?: string;
  // Отредактированные автофильтры из вакансии (метод 'vacancy') — бек ищет по ним.
  role?: string;
  skills?: string[];
  city?: string;
  salary_from?: number;
  salary_to?: number;
}

export interface BaseSearchRetrieveResponse {
  run_id: string;
  total: number;
}

export interface BaseSearchResponse {
  run_id: string;
}

export interface BaseSearchRunStatus {
  id: string;
  status: 'retrieved' | 'running' | 'done' | 'error';
  stage: 'retrieve' | 'rerank' | 'done' | null;
  found: number;
  to_evaluate: number;
  evaluated: number;
  results: BaseSearchCandidate[];
  criteria: {
    role: string;
    skills: string[];
    city: string;
    salary_from: number | null;
    salary_to: number | null;
  } | null;
  query_echo: string | null;
  vacancy_title: string | null;
  error: string | null;
}

export interface BaseSearchRunItem {
  id: string;
  search_type: 'prompt' | 'vacancy';
  query_text: string;
  vacancy_id: string | null;
  found: number;
  added_to_funnel: number;
  created_at: string;
}

export interface BaseCountResponse {
  count: number;
}

// Поиск по своей базе (фаза 1 - retrieve)
export function useSmartBaseSearch() {
  return useMutation<BaseSearchRetrieveResponse, Error, BaseSearchRequest>({
    mutationFn: async (request): Promise<BaseSearchRetrieveResponse> => {
      const response = await api.post('/smart/base/search', request);
      return response.data as BaseSearchRetrieveResponse;
    },
  });
}

// Оценка AI (фаза 2 - evaluate)
export function useSmartBaseEvaluate() {
  return useMutation<{ run_id: string }, Error, { runId: string; evaluateN: number }>({
    mutationFn: async ({ runId, evaluateN }) => {
      const response = await api.post(`/smart/base/runs/${runId}/evaluate`, { evaluate_n: evaluateN });
      return response.data as { run_id: string };
    },
  });
}

// История поиска по базе
export function useSmartBaseHistory() {
  return useQuery({
    queryKey: ['smart', 'base', 'runs'],
    queryFn: async (): Promise<BaseSearchRunItem[]> => {
      const response = await api.get('/smart/base/runs');
      return response.data as BaseSearchRunItem[];
    },
  });
}

// Счётчик кандидатов в базе
export function useSmartBaseCount() {
  return useQuery({
    queryKey: ['smart', 'base', 'count'],
    queryFn: async (): Promise<BaseCountResponse> => {
      const response = await api.get('/smart/base/count');
      return response.data as BaseCountResponse;
    },
  });
}

// Отметка добавления в воронку
export function useMarkBaseRunAdded() {
  return useMutation<void, Error, string>({
    mutationFn: async (runId): Promise<void> => {
      await api.post(`/smart/base/runs/${runId}/mark-added`, {});
    },
  });
}

export function useSmartBaseRun(runId: string | null, enabled: boolean = true) {
  return useQuery({
    queryKey: ['smart', 'base', 'run', runId],
    queryFn: async (): Promise<BaseSearchRunStatus> => {
      const response = await api.get(`/smart/base/runs/${runId}`);
      return response.data as BaseSearchRunStatus;
    },
    enabled: enabled && runId !== null,
    refetchInterval: (data) => {
      return data?.state?.data && data.state.data.status === 'running' ? 1500 : false;
    },
  });
}

// === ИНДЕКСАЦИЯ СЕМАНТИЧЕСКОГО ПОИСКА ===

export interface SmartBaseIndexStatusResponse {
  total_candidates: number;
  indexed_candidates: number;
  indexing: boolean;
  model: string;
  embed_model: string;
}

// Статус индексации семантического поиска
export function useSmartBaseIndexStatus() {
  return useQuery({
    queryKey: ['smart', 'base', 'index-status'],
    queryFn: async (): Promise<SmartBaseIndexStatusResponse> => {
      const response = await api.get('/smart/base/index-status');
      return response.data as SmartBaseIndexStatusResponse;
    },
    refetchInterval: (data) => {
      // Поллинг каждые 3000мс ТОЛЬКО пока indexing === true
      return data?.state?.data && data.state.data.indexing === true ? 3000 : false;
    },
  });
}

// Запуск переиндексации базы
export function useReindexBase() {
  return useMutation<void, Error, void>({
    mutationFn: async (): Promise<void> => {
      await api.post('/smart/base/reindex', {});
    },
  });
}

// === «Забрать к себе» — добавить найденных hh-кандидатов в свою базу+воронку ===

export interface SmartTakeResultItem {
  resume_id: string;
  status: 'taken' | 'already' | 'error';
  message?: string;
  candidate_id?: string | null;
  name?: string | null;
}

export interface SmartTakeResponse {
  results: SmartTakeResultItem[];
  taken_count: number;
}

export function useSmartTake(runId: string) {
  return useMutation<SmartTakeResponse, Error, string[]>({
    mutationFn: async (resumeIds): Promise<SmartTakeResponse> => {
      const response = await api.post(`/smart/runs/${runId}/take`, { resume_ids: resumeIds });
      return response.data as SmartTakeResponse;
    },
  });
}

// === ВЕТКА В: Автоподбор (сохранённые автопоиски hh) ===
// Бек /smart/auto/* готов и проверен на живом hh; openapi не регенерён — локальные типы + as-cast.

export interface AutoAccess {
  has_access: boolean;
  has_paid_access: boolean;
  reason: string | null;
  pool_left: number | null;
}

export interface AutoSearchBasis {
  kind: 'vacancy' | 'prompt';
  vacancy_id?: string;
  prompt?: string;
}

export interface AutoSearch {
  id: string;
  hh_saved_search_id: string;
  name: string;
  region: string | null;
  subscribed: boolean;
  auto_eval: boolean;
  total: number | null;
  new_count: number | null;
  basis: AutoSearchBasis | null;
  updated_at: string | null;
  // Персистентный прогресс последнего прогона AI-оценки (v0.9.177) —
  // виден всегда, не только во время активного поллинга.
  eval_status?: 'running' | 'done' | 'error' | null;
  eval_done?: number;
  eval_total?: number;
}

// Доступ к автопоискам hh (платный доступ + остаток пула контактов)
export function useAutoAccess() {
  return useQuery({
    queryKey: ['smart', 'auto', 'access'],
    queryFn: async (): Promise<AutoAccess> => {
      const response = await api.get('/smart/auto/access');
      return response.data as AutoAccess;
    },
  });
}

// Список автопоисков из hh (синхронизированные сохранённые поиски)
export function useAutoSearches() {
  return useQuery({
    queryKey: ['smart', 'auto', 'searches'],
    queryFn: async (): Promise<AutoSearch[]> => {
      const response = await api.get('/smart/auto/searches');
      return response.data as AutoSearch[];
    },
  });
}

// Принудительная синхронизация автопоисков с hh
export function useSyncAutoSearches() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: async (): Promise<void> => {
      await api.post('/smart/auto/searches/sync', {});
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart', 'auto', 'searches'] });
    },
  });
}

// Кандидат автопоиска (бесплатные поля hh — контакты закрыты до списания пула).
// skills приходит ПУСТЫМ из поиска (навыки — только в полном резюме); НЕ выдумывать.
export interface AutoCandidate {
  hh_resume_id: string;
  title: string | null;
  age: number | null;
  city: string | null;
  anonymous: boolean;
  salary: number | null;
  experience: string | null;
  skills: string[];
  last_job: string | null;
  updated_at: string | null;
  is_new: boolean;
  score: number | null;
  taken: boolean;
  // Прокси-путь к фото кандидата вида "/api/v1/smart/auto/photo?src=<hh_url>"
  // (эндпоинт под Bearer — тянуть blob'ом через api, см. CandidatePhoto). null у анонимных/без фото.
  photo_url?: string | null;
  // Публичная web-ссылка на резюме hh (https://hh.ru/resume/...). null, если недоступна.
  hh_url?: string | null;
}

export interface AutoCandidatesResp {
  items: AutoCandidate[];
  total: number;
  page: number;
  pages: number;
  per_page: number;
}

// === ПОЛНОЕ РЕЗЮМЕ КАНДИДАТА АВТОПОИСКА (без контактов) ===
// Бек: GET /smart/auto/candidate/{hh_resume_id}/detail → AutoCandidateDetail.
// ⚠️ 1 запрос = 1 «просмотр» резюме на hh (НЕ списание контакта). Кэшируем на сессию
// (staleTime Infinity), чтобы повторное открытие карточки не тратило квоту просмотров.

export interface AutoExpItem {
  position?: string | null;
  company?: string | null;
  period?: string | null;
  description?: string | null;
}

export interface AutoEduItem {
  name?: string | null;
  organization?: string | null;
  year?: number | null;
  result?: string | null;
}

export interface AutoCandidateDetail {
  hh_resume_id: string;
  title?: string | null;
  age?: number | null;
  city?: string | null;
  salary?: number | null;
  total_experience?: string | null;
  anonymous?: boolean;
  photo_url?: string | null;
  hh_url?: string | null;
  about?: string | null;
  skills: string[];
  experience: AutoExpItem[];
  education: AutoEduItem[];
  languages: string[];
}

// Полное резюме кандидата автопоиска. Кэш на сессию (staleTime Infinity / retry false)
// — экономит квоту просмотров hh: одно открытие карточки = один реальный запрос.
export function useAutoCandidateDetail(hhResumeId: string | null) {
  return useQuery({
    queryKey: ['smart', 'auto', 'detail', hhResumeId],
    queryFn: async (): Promise<AutoCandidateDetail> => {
      const response = await api.get(`/smart/auto/candidate/${hhResumeId}/detail`);
      return response.data as AutoCandidateDetail;
    },
    enabled: hhResumeId !== null,
    staleTime: Infinity,
    gcTime: 30 * 60 * 1000,
    retry: false,
  });
}

// Кандидаты выбранного автопоиска: пагинация + сегмент (all|new) + сортировка.
// keepPreviousData (placeholderData) — чтобы при смене страницы не мигало в пустоту.
export function useAutoCandidates(
  searchId: string | null,
  params: { segment: 'all' | 'new'; page: number; sort?: string },
) {
  const { segment, page, sort } = params;
  return useQuery({
    queryKey: ['smart', 'auto', 'candidates', searchId, segment, page, sort ?? null],
    queryFn: async (): Promise<AutoCandidatesResp> => {
      const response = await api.get(`/smart/auto/searches/${searchId}/candidates`, {
        params: { segment, page, ...(sort ? { sort } : {}) },
      });
      return response.data as AutoCandidatesResp;
    },
    enabled: searchId !== null,
    placeholderData: (prev) => prev,
  });
}

// === ОЦЕНКА АВТОПОИСКА (чанк C) ===

export interface AutoScored {
  hh_resume_id: string;
  title?: string | null;
  score: number;
  verdict: string;
  summary: string;
  strengths: string[];
  risks: string[];
  requirements_match: { criterion: string; weight: number; points: number; comment?: string }[];
  questions: string[];
  forecast?: string | null;
}

export interface AutoRunStatus {
  id: string;
  status: string;
  stage: string | null;
  to_evaluate: number;
  evaluated: number;
  scored_candidates: AutoScored[];
  note: string | null;
  error: string | null;
}

export function useSetAutoBasis(searchId: string) {
  const qc = useQueryClient();
  return useMutation<AutoSearch, Error, AutoSearchBasis>({
    mutationFn: async (basis): Promise<AutoSearch> => {
      const response = await api.post(`/smart/auto/searches/${searchId}/basis`, basis);
      return response.data as AutoSearch;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['smart', 'auto', 'searches'] });
    },
  });
}

export function useToggleAutoEval(searchId: string) {
  const qc = useQueryClient();
  return useMutation<AutoSearch, Error, boolean>({
    mutationFn: async (enabled): Promise<AutoSearch> => {
      const response = await api.patch(`/smart/auto/searches/${searchId}/auto-eval`, { enabled });
      return response.data as AutoSearch;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['smart', 'auto', 'searches'] });
    },
  });
}

export function useRunAutoEval(searchId: string) {
  return useMutation<{ run_id: string }, Error, { segment: 'all' | 'new'; n?: number }>({
    mutationFn: async ({ segment, n }): Promise<{ run_id: string }> => {
      const response = await api.post(`/smart/auto/searches/${searchId}/evaluate`, {
        segment,
        ...(n ? { n } : {}),
      });
      return response.data as { run_id: string };
    },
  });
}

export function useAutoEvalRun(runId: string | null, enabled: boolean) {
  return useQuery<AutoRunStatus>({
    queryKey: ['smart', 'auto', 'run', runId],
    queryFn: async (): Promise<AutoRunStatus> => {
      const response = await api.get(`/smart/auto/runs/${runId}`);
      return response.data as AutoRunStatus;
    },
    enabled: enabled && runId !== null,
    refetchInterval: (query) => {
      return query.state.data?.status === 'running' ? 1500 : false;
    },
  });
}

// === ЗАБОР КОНТАКТА / ПЕРЕВОД (чанк C2) ===
// ⚠️ ПЛАТНО — списывает контакт из пула hh. Бек гейтит has_paid_access; пул 0 → 429/ошибка.

export interface AutoTakeResult {
  hh_resume_id: string;
  status: 'created' | 'already' | 'error';
  candidate_id?: string | null;
  error?: string | null;
}

export interface AutoTakeResp {
  results: AutoTakeResult[];
  taken: number;
  pool_left: number | null;
}

export interface AutoTakeRequest {
  resume_ids: string[];
  target: 'pool' | 'vacancy';
  vacancy_id?: string;
}

export function useAutoTake(searchId: string) {
  const qc = useQueryClient();
  return useMutation<AutoTakeResp, unknown, AutoTakeRequest>({
    mutationFn: async (body): Promise<AutoTakeResp> => {
      const response = await api.post(`/smart/auto/searches/${searchId}/take`, body);
      return response.data as AutoTakeResp;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['smart', 'auto', 'candidates', searchId] });
      qc.invalidateQueries({ queryKey: ['smart', 'auto', 'access'] });
    },
  });
}