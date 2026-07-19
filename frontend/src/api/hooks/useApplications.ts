import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type Paginated = components['schemas']['Paginated_ApplicationRow_'];

export type ApplicationFilters = {
  stage?: string;
  search?: string;
  score_min?: number;
  salary_max?: number;
  source?: string | string[];
  city?: string; // свободный ввод (одно значение, ILIKE на беке)
  messenger?: string | string[];
  ready_relocate?: boolean;
  added_period?: string;
  repeat?: boolean;
  tags?: string[]; // id тегов
  sort?: string;
  order?: 'asc' | 'desc';
  page?: number;
  // ВАЖНО: бек читает именно `page_size` (applications.py: page_size: int = Query(24, ge=1, le=100)).
  // Раньше фронт слал `size` — параметр молча терялся, страница всегда была дефолтной (24).
  page_size?: number;
  candidate_id?: string;
};

/** Размер страницы автодогрузки воронки (бек: page_size ge=1 le=100). */
const PAGE_SIZE = 24;

/**
 * Общий сборщик query-параметров списка откликов вакансии.
 * Используется и обычным `useApplications`, и постраничным `useApplicationsInfinite`,
 * чтобы фильтры не расходились между двумя копиями.
 */
function buildApplicationParams(filters: ApplicationFilters): URLSearchParams {
  const params = new URLSearchParams();

  if (filters.stage && filters.stage !== 'all') params.append('stage', filters.stage);
  if (filters.search) params.append('search', filters.search);
  if (filters.score_min) params.append('score_min', filters.score_min.toString());
  if (filters.salary_max) params.append('salary_max', filters.salary_max.toString());
  if (filters.source) {
    if (Array.isArray(filters.source)) {
      filters.source.forEach(s => params.append('source', s));
    } else {
      params.append('source', filters.source);
    }
  }
  if (filters.city) {
    if (Array.isArray(filters.city)) {
      filters.city.forEach(c => params.append('city', c));
    } else {
      params.append('city', filters.city);
    }
  }
  if (filters.messenger) {
    if (Array.isArray(filters.messenger)) {
      filters.messenger.forEach(m => params.append('messenger', m));
    } else {
      params.append('messenger', filters.messenger);
    }
  }
  if (filters.ready_relocate !== undefined) params.append('ready_relocate', filters.ready_relocate.toString());
  if (filters.added_period) params.append('added_period', filters.added_period);
  if (filters.repeat !== undefined) params.append('repeat', filters.repeat.toString());
  if (filters.tags && filters.tags.length) filters.tags.forEach(t => params.append('tags', t));
  if (filters.sort) params.append('sort', filters.sort);
  if (filters.order) params.append('order', filters.order);
  if (filters.page) params.append('page', filters.page.toString());
  if (filters.page_size) params.append('page_size', filters.page_size.toString());
  if (filters.candidate_id) params.append('candidate_id', filters.candidate_id);

  return params;
}

type UseApplicationsOptions = {
  enabled?: boolean;
};

/**
 * Точечный (одностраничный) запрос откликов — используется для поиска конкретной заявки
 * по `candidate_id`, когда её нет в подгруженных страницах списка.
 *
 * Сегмент 'one' идёт ПОСЛЕ 'applications', чтобы префиксная инвалидация
 * ['vacancies', id, 'applications'] в api/mutations/applications.ts продолжала работать.
 */
export function useApplications(
  vacancyId: string,
  filters: ApplicationFilters = {},
  options: UseApplicationsOptions = {}
) {
  return useQuery({
    queryKey: ['vacancies', vacancyId, 'applications', 'one', filters],
    queryFn: async () => {
      const params = buildApplicationParams(filters);
      const response = await api.get(`/vacancies/${vacancyId}/applications?${params.toString()}`);
      return response.data as Paginated;
    },
    enabled: !!vacancyId && (options.enabled ?? true),
  });
}

/**
 * Постраничный список откликов воронки с автодогрузкой при скролле.
 * Бек отдаёт `pages` (всего страниц), а не `has_next` — следующая страница есть,
 * пока загруженных страниц меньше общего числа (тот же идиом, что в useCandidates).
 */
export function useApplicationsInfinite(
  vacancyId: string,
  filters: ApplicationFilters = {}
) {
  return useInfiniteQuery({
    queryKey: ['vacancies', vacancyId, 'applications', 'list', filters],
    queryFn: async ({ pageParam }) => {
      const params = buildApplicationParams(filters);
      params.set('page', String(pageParam));
      params.set('page_size', String(PAGE_SIZE));

      const response = await api.get(`/vacancies/${vacancyId}/applications?${params.toString()}`);
      return response.data as Paginated;
    },
    getNextPageParam: (lastPage, allPages) =>
      allPages.length < lastPage.pages ? allPages.length + 1 : undefined,
    initialPageParam: 1,
    enabled: !!vacancyId,
  });
}
