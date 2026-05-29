import { useEffect, useMemo, useState } from 'react'
import './CandidatesPool.css'
import { useSearchParams } from 'react-router-dom'
import { CandidateFilters } from './components/CandidateFilters'
import { CandidateGrid } from './components/CandidateGrid'
import { useCandidates } from '../../api/hooks/useCandidates'
import { useDebounce } from '../../hooks/useDebounce'
// import { scoreSegmentToRange } from '../../lib/score-segments' // Used for URL filtering
import type { CandidateFilters as FilterType } from '../../api/hooks/useCandidates'

export function CandidatesPoolPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [searchInput, setSearchInput] = useState(searchParams.get('search') || '')

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

    // Handle score segment
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

    // Only update if different to avoid infinite loops
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
    key !== 'sort' && key !== 'order' && value
  )

  const handleSortChange = (sort: string) => {
    const newParams = new URLSearchParams(searchParams)
    if (sort) {
      newParams.set('sort', sort)
      // Set default order based on sort type
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
  }

  const getCurrentSort = () => {
    return searchParams.get('sort') || 'created_at'
  }

  const getSortLabel = (sort: string) => {
    switch (sort) {
      case 'name': return 'По ФИО А-Я'
      case 'score': return 'По AI-скорингу'
      case 'activity': return 'По дате активности'
      default: return 'По дате добавления (новые)'
    }
  }

  return (
    <div className="candidates-pool-page">
      {/* Sticky Header */}
      <div className="cnd-page-header sticky">
        <div className="header-content">
          <div className="header-left">
            <h1>Кандидаты</h1>
            <div className="header-subtitle">
              {hasActiveFilters && totalCount > 0
                ? `Показано ${allCandidates.length} из ${totalCount}`
                : `${totalCount} кандидатов в базе`
              }
            </div>
          </div>
          <div className="header-actions">
            <button className="btn btn-primary">
              + Добавить кандидата
            </button>
            <button
              className="btn btn-secondary"
              disabled
              title="Функция в разработке"
            >
              Импорт из файла
            </button>
          </div>
        </div>
      </div>

      {/* Sticky Control Panel */}
      <div className="control-panel sticky">
        <div className="panel-left">
          <div className="search-container">
            <div className="search-input-wrapper">
              <span className="search-icon">🔍</span>
              <input
                type="text"
                placeholder="Поиск по ФИО"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="search-input"
              />
            </div>
          </div>
        </div>

        <div className="panel-right">
          <div className="sort-container">
            <label htmlFor="sort-select" className="sort-label">
              Сортировка:
            </label>
            <select
              id="sort-select"
              value={getCurrentSort()}
              onChange={(e) => handleSortChange(e.target.value)}
              className="sort-select"
            >
              <option value="created_at">{getSortLabel('created_at')}</option>
              <option value="score">{getSortLabel('score')}</option>
              <option value="name">{getSortLabel('name')}</option>
              <option value="activity">{getSortLabel('activity')}</option>
            </select>
          </div>
        </div>
      </div>

      {/* Filters */}
      <CandidateFilters />

      {/* Grid */}
      <CandidateGrid
        candidates={allCandidates}
        isLoading={isLoading}
        isFetchingNextPage={isFetchingNextPage}
        hasNextPage={hasNextPage ?? false}
        onLoadMore={() => fetchNextPage()}
      />
    </div>
  )
}