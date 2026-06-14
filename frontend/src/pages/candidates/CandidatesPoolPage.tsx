import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useDebounce } from '../../hooks/useDebounce'
import { useCandidates } from '../../api/hooks/useCandidates'
import { FilterDrawer } from './components/FilterDrawer'
import { Icon } from '../../components/ui/Icon'
import { Avatar } from '../../components/ui/Avatar'
import { ScoreLabel } from '../../components/ui/ScoreLabel'
import { StageChip } from '../../components/ui/StageChip'
import NewCandidateForm from '../funnel/NewCandidateForm'
import { ImportCandidatesWizard } from './ImportCandidatesWizard'
import type { CandidateFilters as FilterType } from '../../api/hooks/useCandidates'
import type { CandidateGridItem } from '../../api/aliases'
import './CandidatesPoolPage.css'

export function CandidatesPoolPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [searchInput, setSearchInput] = useState(searchParams.get('search') || '')
  const [showFilters, setShowFilters] = useState(false)
  const [showAddForm, setShowAddForm] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [sortOpen, setSortOpen] = useState(false)

  // Ref для стабильности коллбэков - используем актуальные searchParams без пересоздания коллбэков
  const searchParamsRef = useRef(searchParams)
  searchParamsRef.current = searchParams

  // Debounce search input
  const debouncedSearch = useDebounce(searchInput, 200)

  // Build filters from URL params
  const filters = useMemo((): FilterType => {
    const params: FilterType = {}

    if (debouncedSearch) params.search = debouncedSearch

    const city = searchParams.get('city')
    if (city) params.city = city

    const exp = searchParams.get('exp')
    if (exp) params.exp = Number(exp)

    const scoreMin = searchParams.get('score_min')
    const scoreMax = searchParams.get('score_max')
    if (scoreMin) params.score_min = Number(scoreMin)
    if (scoreMax) params.score_max = Number(scoreMax)

    const source = searchParams.get('source')
    if (source) params.source = source

    const vacancyId = searchParams.get('vacancy_id')
    if (vacancyId) params.vacancy_id = vacancyId

    const stage = searchParams.get('stage')
    if (stage) params.stage = stage

    const tags = searchParams.get('tags')
    if (tags) params.tags = tags.split(',').filter(Boolean)

    const addedPeriod = searchParams.get('added_period')
    if (addedPeriod) params.added_period = addedPeriod

    const sort = searchParams.get('sort')
    if (sort) params.sort = sort

    const order = searchParams.get('order')
    if (order) params.order = order

    return params
  }, [searchParams, debouncedSearch])

  const {
    data,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage
  } = useCandidates(filters)

  // Update search param when debounced search changes
  useEffect(() => {
    const newParams = new URLSearchParams(searchParams)

    if (debouncedSearch) {
      newParams.set('search', debouncedSearch)
    } else {
      newParams.delete('search')
    }

    if (newParams.toString() !== searchParams.toString()) {
      setSearchParams(newParams)
    }
  }, [debouncedSearch, searchParams, setSearchParams])

  // Restore scroll position after returning from detail view
  useEffect(() => {
    const savedScrollY = sessionStorage.getItem('pool:scrollY')
    if (savedScrollY && data?.pages?.[0]) {
      setTimeout(() => {
        window.scrollTo(0, Number(savedScrollY))
        sessionStorage.removeItem('pool:scrollY')
      }, 100)
    }
  }, [data?.pages])

  // Flatten candidates from all pages
  const allCandidates = useMemo(() => {
    return data?.pages?.flatMap(page => page.items) ?? []
  }, [data?.pages])

  const totalCount = data?.pages?.[0]?.total ?? 0
  const hasActiveFilters = Array.from(searchParams.entries()).some(([key, value]) =>
    key !== 'sort' && key !== 'order' && key !== 'search' && value
  )

  // Count active filters for badge
  const activeFilterCount = Array.from(searchParams.entries()).filter(([key, value]) =>
    key !== 'sort' && key !== 'order' && key !== 'search' && value
  ).length

  const handleSortChange = (sort: string) => {
    const newParams = new URLSearchParams(searchParams)
    if (sort) {
      newParams.set('sort', sort)
      if (sort === 'name') {
        newParams.set('order', 'asc')
      } else {
        newParams.set('order', 'desc')
      }
    } else {
      newParams.delete('sort')
      newParams.delete('order')
    }
    setSearchParams(newParams)
    setSortOpen(false)
  }

  const getCurrentSort = () => {
    return searchParams.get('sort') || 'created_at'
  }

  const getSortLabel = (sort: string) => {
    switch (sort) {
      case 'name': return 'По ФИО А–Я'
      case 'score': return 'По AI-скорингу'
      case 'activity': return 'По последней активности'
      default: return 'По дате добавления'
    }
  }

  const SORT_OPTIONS = [
    { id: 'created_at', label: 'По дате добавления' },
    { id: 'score', label: 'По AI-скорингу' },
    { id: 'name', label: 'По ФИО А–Я' },
    { id: 'activity', label: 'По последней активности' },
  ]

  const handleAddCandidate = () => {
    setShowAddForm(true)
  }

  const handleImportFile = () => {
    setShowImport(true)
  }

  const handleFiltersClick = () => {
    setShowFilters(true)
  }

  // Стабильные коллбэки для PoolCard - снимаем хуки из дочерних карточек
  const onOpenCard = useCallback((candidateId: string) => {
    sessionStorage.setItem('pool:filters', searchParamsRef.current.toString())
    sessionStorage.setItem('pool:scrollY', String(window.scrollY))
    navigate(`/candidates/${candidateId}`)
  }, [navigate])

  const onOpenEvaluation = useCallback((candidateId: string) => {
    sessionStorage.setItem('pool:filters', searchParamsRef.current.toString())
    sessionStorage.setItem('pool:scrollY', String(window.scrollY))
    navigate(`/candidates/${candidateId}?tab=evaluation`)
  }, [navigate])

  const onOpenVacancy = useCallback((vacancyId: string) => {
    navigate(`/vacancies/${vacancyId}`)
  }, [navigate])

  const onOpenHistory = useCallback((candidateId: string) => {
    sessionStorage.setItem('pool:filters', searchParamsRef.current.toString())
    sessionStorage.setItem('pool:scrollY', String(window.scrollY))
    navigate(`/candidates/${candidateId}?history=open`)
  }, [navigate])

  if (showAddForm) {
    return (
      <CandidateFormWrapper
        onClose={() => setShowAddForm(false)}
      />
    )
  }

  if (showImport) {
    return (
      <ImportCandidatesWizard
        onClose={() => setShowImport(false)}
        onDone={() => {
          setShowImport(false);
          // Список сам перезапросится через invalidate
        }}
      />
    )
  }

  return (
    <div className="cp-page">
      {/* ====== Sticky Header ====== */}
      <div className="cp-header">
        <div className="cp-header-left">
          <h1 className="cp-title">Кандидаты</h1>
          <div className="cp-counter">
            {hasActiveFilters || searchInput
              ? <>Показано <span className="t-mono">{allCandidates.length}</span> из <span className="t-mono">{totalCount}</span></>
              : <><span className="t-mono">{totalCount}</span> кандидатов в базе</>
            }
          </div>
        </div>
        <div className="cp-header-actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleImportFile}
          >
            <Icon name="download" size={14}/> Импорт кандидатов
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleAddCandidate}
          >
            <Icon name="plus" size={14}/> Добавить кандидата
          </button>
        </div>
      </div>

      {/* ====== Sticky Control Panel ====== */}
      <div className="cp-controls">
        <div className="cp-search">
          <Icon name="search" size={14} style={{color:'var(--fg-3)', flex:'none'}}/>
          <input
            placeholder="Поиск по ФИО, телефону, email…"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
          />
        </div>
        <div style={{flex:1}}/>

        <div className={`cp-sort ${sortOpen ? 'open' : ''}`}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setSortOpen(o => !o)}
          >
            <Icon name="chevron-up-down" size={14}/> {getSortLabel(getCurrentSort())} <Icon name="chevD" size={12}/>
          </button>
          {sortOpen && (
            <div className="cp-sort-menu" onMouseLeave={() => setSortOpen(false)}>
              {SORT_OPTIONS.map(({id, label}) => (
                <button key={id}
                  className={`cp-sort-opt ${getCurrentSort() === id ? 'active' : ''}`}
                  onClick={() => handleSortChange(id)}>
                  {label}
                  {getCurrentSort() === id && <Icon name="check" size={14}/>}
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          className={`btn btn-secondary btn-sm ${activeFilterCount > 0 ? 'has-filters' : ''}`}
          onClick={handleFiltersClick}
        >
          <Icon name="filter" size={14}/> Фильтры
          {activeFilterCount > 0 && <span className="filter-badge">{activeFilterCount}</span>}
        </button>
      </div>

      {/* ====== Grid ====== */}
      <div className="cp-grid">
        {allCandidates.map(candidate => (
          <PoolCard
            key={candidate.id}
            candidate={candidate}
            onOpenCard={onOpenCard}
            onOpenEvaluation={onOpenEvaluation}
            onOpenVacancy={onOpenVacancy}
            onOpenHistory={onOpenHistory}
          />
        ))}

        {/* Loading skeletons */}
        {(isLoading || isFetchingNextPage) && (
          Array.from({ length: isLoading ? 12 : 4 }, (_, i) => (
            <div key={`skeleton-${i}`} className="pool-card skeleton">
              <div className="pc-head">
                <div className="skeleton-avatar"></div>
                <div className="pc-name-wrap">
                  <div className="skeleton-name"></div>
                  <div className="skeleton-meta"></div>
                </div>
                <div className="skeleton-score"></div>
              </div>
              <div className="pc-divider"/>
              <div className="skeleton-vac"></div>
            </div>
          ))
        )}

        {/* Empty state */}
        {!isLoading && allCandidates.length === 0 && !hasActiveFilters && !searchInput && (
          <div className="cp-empty">
            <div className="empty-illust"><Icon name="users" size={36}/></div>
            <h3>В базе пока нет кандидатов</h3>
            <p>Добавьте первого кандидата, чтобы начать работу</p>
            <button className="btn btn-primary btn-sm" onClick={handleAddCandidate}>
              <Icon name="plus" size={14}/> Добавить кандидата
            </button>
          </div>
        )}

        {/* Not found state */}
        {!isLoading && allCandidates.length === 0 && (hasActiveFilters || searchInput) && (
          <div className="cp-empty">
            <div className="empty-illust"><Icon name="users" size={36}/></div>
            <h3>Никого не найдено по заданным параметрам</h3>
            <p>Попробуйте изменить фильтры или сбросьте их.</p>
            <button className="btn btn-secondary btn-sm" onClick={() => {
              const newParams = new URLSearchParams()
              const search = searchParams.get('search')
              const sort = searchParams.get('sort')
              const order = searchParams.get('order')
              if (search) newParams.set('search', search)
              if (sort) newParams.set('sort', sort)
              if (order) newParams.set('order', order)
              setSearchParams(newParams)
            }}>Сбросить фильтры</button>
          </div>
        )}

      </div>

      {/* Пагинатор «Показать ещё» (в эталоне нет — добавлен: подгрузка следующих кандидатов) */}
      {hasNextPage && (
        <div className="cp-pager">
          <button
            className="btn btn-secondary"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
          >
            {isFetchingNextPage ? 'Загрузка…' : `Показать ещё (${Math.max(0, totalCount - allCandidates.length)})`}
          </button>
        </div>
      )}

      {/* Эталонный FilterDrawer (.fdr) — замена временного моста */}
      {showFilters && (
        <FilterDrawer onClose={() => setShowFilters(false)} />
      )}
    </div>
  )
}

// ====== Pool Card Component ======
interface PoolCardProps {
  candidate: CandidateGridItem
  onOpenCard: (candidateId: string) => void
  onOpenEvaluation: (candidateId: string) => void
  onOpenVacancy: (vacancyId: string) => void
  onOpenHistory: (candidateId: string) => void
}

const PoolCard = React.memo(function PoolCard({
  candidate,
  onOpenCard,
  onOpenEvaluation,
  onOpenVacancy,
  onOpenHistory
}: PoolCardProps) {
  const handleCardClick = () => {
    onOpenCard(candidate.id)
  }

  const handleScoreBadgeClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    onOpenEvaluation(candidate.id)
  }

  const handleVacancyClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (candidate.last_vacancy) {
      onOpenVacancy(candidate.last_vacancy.vacancy_id)
    }
  }

  const handleOtherVacanciesClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    onOpenHistory(candidate.id)
  }

  // Format age and experience display
  const formatAge = (age: number | null | undefined) => age ? `${age} лет` : ''
  const formatExperience = () => {
    // Эталон: «стаж на последнем месте · компания» (last_tenure вычислен на беке).
    const tenure = (candidate as any).last_tenure as string | null | undefined
    const parts = []
    if (tenure) parts.push(tenure)
    if (candidate.last_company) parts.push(candidate.last_company)
    return parts.join(' · ')
  }

  return (
    <div
      className="pool-card"
      onClick={handleCardClick}
    >
      <div className="pc-head">
        <Avatar name={candidate.full_name} size="sm"/>
        <div className="pc-name-wrap">
          <div className="pc-name" title={candidate.full_name}>
            {candidate.full_name}
          </div>
          <div className="pc-meta-2l">
            <div className="pc-meta-line">{formatAge(candidate.age)}</div>
            <div className="pc-meta-line t-clip" title={formatExperience()}>
              {formatExperience()}
            </div>
          </div>
        </div>
        <div onClick={handleScoreBadgeClick}>
          <ScoreLabel value={candidate.ai_score ?? null} size="lg"/>
        </div>
      </div>

      {candidate.is_duplicate && <span className="pc-dup-flag">Дубль</span>}

      <div className="pc-divider"/>

      {candidate.last_vacancy ? (
        <div className="pc-vac">
          <div className="pc-vac-head">
            <Icon name="briefcase" size={13} className="pc-vac-icon"/>
            <span
              className="pc-vac-title"
              title={candidate.last_vacancy.vacancy_name}
              onClick={handleVacancyClick}
            >
              {candidate.last_vacancy.vacancy_name}
            </span>
            {candidate.other_vacancies_count > 0 && (
              <span
                className="pc-vac-more"
                title={`Ещё в ${candidate.other_vacancies_count} вакансиях`}
                onClick={handleOtherVacanciesClick}
              >
                +{candidate.other_vacancies_count}
              </span>
            )}
          </div>
          <StageChip
            stage={candidate.last_vacancy.stage}
            label={(candidate.last_vacancy as { stage_label?: string }).stage_label}
            color={candidate.last_vacancy.stage_color}
            size="sm"
          />
        </div>
      ) : (
        <div className="pc-vac pc-vac-empty">
          <span className="pc-vac-empty-dot"/>
          В базе · не привязан к вакансии
        </div>
      )}

    </div>
  )
});

// ====== Wrapper for NewCandidateForm without preset vacancy ======
interface CandidateFormWrapperProps {
  onClose: () => void
}

function CandidateFormWrapper({ onClose }: CandidateFormWrapperProps) {
  // Из пула добавляем БЕЗ предвыбранной вакансии — кандидат уходит «в базу», привязать можно
  // позже из карточки («Перевести на вакансию»). Вакансию можно выбрать в форме при желании.
  // Форма сама грузит список вакансий для дропдауна; спец-блока «нет вакансий» больше нет.
  return (
    <NewCandidateForm
      vacancyId=""
      onClose={onClose}
    />
  )
}