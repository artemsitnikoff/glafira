import { useState, useCallback, useRef } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import './funnel/Funnel.css';
import './funnel/FilterDrawer.css';
import { useVacancy } from '@/api/hooks/useVacancy';
import { useVacancyStages } from '@/api/hooks/useVacancyStages';
import { useApplications } from '@/api/hooks/useApplications';
import VacancyHeader from '@/pages/funnel/VacancyHeader';
import StageChipsBar from '@/pages/funnel/StageChipsBar';
import SearchBar from '@/pages/funnel/SearchBar';
import FunnelTable from '@/pages/funnel/FunnelTable';
import BulkActionBar from '@/pages/funnel/BulkActionBar';
import FilterDrawer from '@/pages/funnel/FilterDrawer';
import NewCandidateForm from '@/pages/funnel/NewCandidateForm';
import DetailHost from '@/pages/funnel/DetailHost';
import { Skeleton } from '@/components/ui/Skeleton';
import { Icon } from '@/components/ui/Icon';
import type { ApplicationFilters } from '@/api/hooks/useApplications';

export default function VacancyDetailPage() {
  const { id, cid } = useParams<{ id: string; cid?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // searchParamsRef — чтобы onCandidateSelect оставался стабильным (не зависел от меняющегося
  // searchParams). Иначе useCallback(onOpenRow,[onCandidateSelect]) в FunnelTable пересоздаётся
  // на каждый ре-рендер (напр. toggle чекбокса) → React.memo на FunnelRow проваливается у всех строк.
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;

  const handleCandidateSelect = useCallback((candidateId: string) => {
    navigate({
      pathname: `/vacancies/${id}/candidates/${candidateId}`,
      search: searchParamsRef.current.toString(),
    });
  }, [navigate, id]);

  const { data: vacancy, isLoading: vacancyLoading } = useVacancy(id!);
  const { data: stages, isLoading: stagesLoading } = useVacancyStages(id!);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [createCandidateOpen, setCreateCandidateOpen] = useState(false);

  // Extract filters from URL — читаем ВСЕ поля (раньше читались только stage/search/score_min,
  // из-за чего фильтры из drawer писались в URL, но не доходили до API).
  const filters: ApplicationFilters = {
    stage: searchParams.get('stage') || undefined,
    search: searchParams.get('search') || undefined,
    score_min: searchParams.get('score_min') ? Number(searchParams.get('score_min')) : undefined,
    salary_max: searchParams.get('salary_max') ? Number(searchParams.get('salary_max')) : undefined,
    source: searchParams.getAll('source').length ? searchParams.getAll('source') : undefined,
    city: searchParams.get('city') || undefined,
    messenger: searchParams.getAll('messenger').length ? searchParams.getAll('messenger') : undefined,
    ready_relocate: searchParams.get('ready_relocate') === 'true' || undefined,
    added_period: searchParams.get('added_period') || undefined,
    repeat: searchParams.get('repeat') === 'true' || undefined,
    tags: searchParams.getAll('tags').length ? searchParams.getAll('tags') : undefined,
    sort: searchParams.get('sort') || 'ai_score', // дефолт — AI-скоринг (совпадает с подсветкой колонки)
    order: (searchParams.get('order') as 'asc' | 'desc') || 'desc',
  };

  // Кол-во активных фильтров (без этапа/поиска/сортировки — у них свои контролы) — для бейджа.
  const arrLen = (v: string | string[] | undefined) => (v ? (Array.isArray(v) ? v.length : 1) : 0);
  const activeFilterCount =
    (filters.score_min ? 1 : 0) +
    (filters.salary_max && filters.salary_max < 500000 ? 1 : 0) + // Учитываем, что salary_max теперь в рублях
    arrLen(filters.source) +
    (filters.city ? 1 : 0) +
    arrLen(filters.messenger) +
    (filters.ready_relocate ? 1 : 0) +
    (filters.added_period ? 1 : 0) +
    (filters.repeat ? 1 : 0) +
    arrLen(filters.tags);

  // Get applications for finding current candidate's application
  const { data: applicationsData } = useApplications(id!, filters);

  const isDetailMode = !!cid;

  // Find current application by candidate_id
  const currentApplication = isDetailMode && applicationsData?.items
    ? applicationsData.items.find(app => app.candidate_id === cid) || null
    : null;

  // Fallback query for direct links when candidate is not in current page/filter
  const fallbackQuery = useApplications(
    id!,
    { candidate_id: cid, page: 1, size: 1 },
    { enabled: isDetailMode && !!cid && !currentApplication && !!applicationsData }
  );

  // Resolve the final application - prefer main query, fallback to specific query
  const resolvedApplication = currentApplication
    ?? fallbackQuery.data?.items?.[0]
    ?? null;

  const isResolvingApplication = isDetailMode && !resolvedApplication && fallbackQuery.isLoading;

  const updateFilters = (newFilters: ApplicationFilters) => {
    const params = new URLSearchParams(searchParams);

    // Чистим ВСЕ фильтр-ключи (вызыватели передают полный объект filters).
    ['stage', 'search', 'score_min', 'salary_max', 'source', 'city', 'messenger',
     'ready_relocate', 'added_period', 'repeat', 'tags', 'sort', 'order'].forEach(k => params.delete(k));

    // Пишем заново; массивы (source/messenger) — несколькими значениями.
    const setParam = (key: string, value: unknown) => {
      if (value === undefined || value === null || value === '') return;
      if (Array.isArray(value)) {
        value.forEach(v => params.append(key, String(v)));
      } else {
        params.set(key, String(value));
      }
    };
    Object.entries(newFilters).forEach(([key, value]) => setParam(key, value));

    setSearchParams(params);
  };

  const closeDetail = () => {
    navigate({
      pathname: `/vacancies/${id}`,
      search: searchParams.toString(),
    });
  };

  if (vacancyLoading || stagesLoading) {
    return (
      <div className="cnd-funnel-wrap">
        <div className="vac-header">
          <Skeleton height={60} />
        </div>
        <div className="funnel-row">
          <Skeleton height={32} width={100} />
          <Skeleton height={32} width={120} />
          <Skeleton height={32} width={140} />
        </div>
        <div className="cand-controls">
          <Skeleton height={30} width={280} />
          <Skeleton height={30} width={120} />
        </div>
        <div className="cand-table">
          <Skeleton height={400} />
        </div>
      </div>
    );
  }

  if (!vacancy || !stages) {
    return <div>Вакансия не найдена</div>;
  }

  // Show full-screen candidate form if open
  if (createCandidateOpen) {
    return (
      <NewCandidateForm
        vacancyId={id!}
        onClose={() => setCreateCandidateOpen(false)}
      />
    );
  }

  return (
    <div className={`cnd-funnel-wrap ${isDetailMode ? 'detail-mode' : ''}`}>
      <VacancyHeader
        vacancy={vacancy}
        onEdit={() => navigate(`/vacancies/${id}/edit`)}
        onAddCandidate={() => setCreateCandidateOpen(true)}
      />

      <StageChipsBar
        stages={stages}
        currentStage={filters.stage}
        onStageSelect={stage => {
          // Одна навигация: меняем этап + закрываем карточку (без гонки со stale searchParams).
          const params = new URLSearchParams(searchParams);
          if (stage && stage !== 'all') params.set('stage', stage);
          else params.delete('stage');
          navigate({ pathname: `/vacancies/${id}`, search: params.toString() });
        }}
      />

      <div className="cand-controls">
        <SearchBar
          search={filters.search}
          onSearchChange={search => updateFilters({ ...filters, search })}
          onFiltersOpen={() => setFiltersOpen(true)}
          filtersCount={activeFilterCount}
        />

        {selectedIds.size > 0 && !isDetailMode && (
          <BulkActionBar
            selectedIds={selectedIds}
            onClearSelection={() => setSelectedIds(new Set())}
            vacancyId={id!}
          />
        )}

        <div style={{ flex: 1 }} />

        <button
          className={`btn btn-secondary btn-sm ${activeFilterCount > 0 ? 'has-filters' : ''}`}
          onClick={() => setFiltersOpen(true)}
        >
          <Icon name="filter" size={14} /> Фильтры
          {activeFilterCount > 0 && <span className="filter-badge">{activeFilterCount}</span>}
        </button>
      </div>

      <div className="cand-body">
        <FunnelTable
          vacancyId={id!}
          filters={filters}
          onFiltersChange={updateFilters}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          activeCandidateId={cid}
          detailMode={isDetailMode}
          onCandidateSelect={handleCandidateSelect}
        />

        {isDetailMode && (
          <DetailHost
            application={resolvedApplication}
            onClose={closeDetail}
            isResolving={isResolvingApplication}
            vacancyId={id!}
          />
        )}
      </div>

      {filtersOpen && (
        <FilterDrawer
          onClose={() => setFiltersOpen(false)}
          filters={filters}
          onFiltersChange={updateFilters}
        />
      )}

    </div>
  );
}