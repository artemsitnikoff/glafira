import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { scoreSegmentToRange, rangeToScoreSegment, getScoreSegmentLabel } from '../../../lib/score-segments'
import type { ScoreSegment } from '../../../lib/score-segments'
import { useVacancies } from '../../../api/hooks/useVacancies'
import { useTags } from '../../../api/hooks/useTags'

interface FilterOption {
  value: string
  label: string
}

export function CandidateFilters() {
  const [searchParams, setSearchParams] = useSearchParams()

  // Load vacancies for filter dropdown
  const { data: vacanciesData, isLoading: vacanciesLoading } = useVacancies({
    status: 'active',
    page_size: 100
  })

  // Load tags for filter dropdown
  const { data: tagsData, isLoading: tagsLoading } = useTags()

  // Extract current filter values
  const currentFilters = useMemo(() => ({
    city: searchParams.get('city') || '',
    exp: searchParams.get('exp') || '',
    score: rangeToScoreSegment(
      searchParams.get('score_min') ? Number(searchParams.get('score_min')) : undefined,
      searchParams.get('score_max') ? Number(searchParams.get('score_max')) : undefined
    ),
    source: searchParams.get('source') || '',
    vacancy_id: searchParams.get('vacancy_id') || '',
    stage: searchParams.get('stage') || '',
    tags: searchParams.get('tags')?.split(',').filter(Boolean) || [],
    added_period: searchParams.get('added_period') || ''
  }), [searchParams])

  const hasActiveFilters = useMemo(() => {
    return Object.values(currentFilters).some(value => {
      if (Array.isArray(value)) return value.length > 0
      return Boolean(value)
    })
  }, [currentFilters])

  // Update URL parameters
  const updateFilter = (key: string, value: string | string[] | null) => {
    const newParams = new URLSearchParams(searchParams)

    if (!value || (Array.isArray(value) && value.length === 0)) {
      newParams.delete(key)

      // Handle score segment special case
      if (key === 'score') {
        newParams.delete('score_min')
        newParams.delete('score_max')
      }
    } else if (Array.isArray(value)) {
      newParams.set(key, value.join(','))
    } else if (key === 'score') {
      // Convert score segment to min/max
      const { min, max } = scoreSegmentToRange(value as ScoreSegment)
      newParams.delete('score_min')
      newParams.delete('score_max')
      if (min !== undefined) newParams.set('score_min', String(min))
      if (max !== undefined) newParams.set('score_max', String(max))
    } else {
      newParams.set(key, value)
    }

    setSearchParams(newParams)
  }

  const clearAllFilters = () => {
    const newParams = new URLSearchParams()

    // Preserve search and sort params
    const search = searchParams.get('search')
    const sort = searchParams.get('sort')
    const order = searchParams.get('order')

    if (search) newParams.set('search', search)
    if (sort) newParams.set('sort', sort)
    if (order) newParams.set('order', order)

    setSearchParams(newParams)
  }

  const expOptions: FilterOption[] = [
    { value: '', label: 'Все' },
    { value: '0', label: 'до 1 года' },
    { value: '1', label: '1–3 года' },
    { value: '3', label: '3–5 лет' },
    { value: '5', label: '5+ лет' }
  ]

  const scoreOptions: Array<FilterOption & { segment?: ScoreSegment }> = [
    { value: '', label: 'Все' },
    { value: 'green', label: getScoreSegmentLabel('green'), segment: 'green' },
    { value: 'yellow', label: getScoreSegmentLabel('yellow'), segment: 'yellow' },
    { value: 'red', label: getScoreSegmentLabel('red'), segment: 'red' }
  ]

  const sourceOptions: FilterOption[] = [
    { value: '', label: 'Все' },
    { value: 'hh', label: 'hh.ru' },
    { value: 'avito', label: 'Авито' },
    { value: 'telegram', label: 'Глафира · Telegram' },
    { value: 'import', label: 'Импорт' },
    { value: 'manual', label: 'Ручной ввод' }
  ]

  const stageOptions: FilterOption[] = [
    { value: '', label: 'Все' },
    { value: 'response', label: 'Отклик' },
    { value: 'selected', label: 'Отобран' },
    { value: 'recruiter', label: 'Контакт с рекрутером' },
    { value: 'interview', label: 'Интервью' },
    { value: 'manager', label: 'Контакт с менеджером' },
    { value: 'offer', label: 'Оффер' },
    { value: 'hired', label: 'Нанят' },
    { value: 'rejected', label: 'Отказ' },
    { value: 'pool', label: 'В базе' }
  ]

  const periodOptions: FilterOption[] = [
    { value: '', label: 'Всё время' },
    { value: '7d', label: 'Неделя' },
    { value: '30d', label: 'Месяц' },
    { value: '3m', label: 'Квартал' },
    { value: '12m', label: 'Год' }
  ]

  return (
    <div className="candidate-filters">
      <div className="filters-row">
        {/* Город */}
        <div className="filter-item">
          <label className="filter-label">Город</label>
          <select
            value={currentFilters.city}
            onChange={(e) => updateFilter('city', e.target.value)}
            className="filter-select"
          >
            <option value="">Все города</option>
            <option value="Москва">Москва</option>
            <option value="Санкт-Петербург">Санкт-Петербург</option>
            <option value="Новосибирск">Новосибирск</option>
            <option value="Екатеринбург">Екатеринбург</option>
            <option value="Казань">Казань</option>
            <option value="Нижний Новгород">Нижний Новгород</option>
          </select>
        </div>

        {/* Опыт */}
        <div className="filter-item">
          <label className="filter-label">Опыт</label>
          <div className="segment-control">
            {expOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`segment-item ${currentFilters.exp === option.value ? 'active' : ''}`}
                onClick={() => updateFilter('exp', option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* AI-скоринг */}
        <div className="filter-item">
          <label className="filter-label">AI-скоринг</label>
          <div className="segment-control">
            {scoreOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`segment-item ${currentFilters.score === option.segment ? 'active' : ''}`}
                onClick={() => updateFilter('score', option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Источник */}
        <div className="filter-item">
          <label className="filter-label">Источник</label>
          <select
            value={currentFilters.source}
            onChange={(e) => updateFilter('source', e.target.value)}
            className="filter-select"
          >
            {sourceOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Вакансия */}
        <div className="filter-item">
          <label className="filter-label">Вакансия</label>
          <select
            value={currentFilters.vacancy_id}
            onChange={(e) => updateFilter('vacancy_id', e.target.value)}
            className="filter-select"
            disabled={vacanciesLoading}
          >
            <option value="">
              {vacanciesLoading ? 'Загрузка...' : 'Все вакансии'}
            </option>
            {vacanciesData?.items?.map((vacancy) => (
              <option key={vacancy.id} value={vacancy.id}>
                {vacancy.name}
              </option>
            ))}
          </select>
        </div>

        {/* Этап */}
        <div className="filter-item">
          <label className="filter-label">Этап</label>
          <select
            value={currentFilters.stage}
            onChange={(e) => updateFilter('stage', e.target.value)}
            className="filter-select"
          >
            {stageOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Теги */}
        <div className="filter-item">
          <label className="filter-label">Теги</label>
          <select
            value=""
            onChange={(e) => {
              if (e.target.value && !currentFilters.tags.includes(e.target.value)) {
                updateFilter('tags', [...currentFilters.tags, e.target.value])
              }
            }}
            className="filter-select"
            disabled={tagsLoading}
          >
            <option value="">
              {tagsLoading ? 'Загрузка...' : 'Добавить тег'}
            </option>
            {tagsData?.filter(tag => !currentFilters.tags.includes(tag.name)).map((tag) => (
              <option key={tag.id} value={tag.name}>
                {tag.name}
              </option>
            ))}
          </select>
          {currentFilters.tags.length > 0 && (
            <div className="selected-tags">
              {currentFilters.tags.map((tagName) => (
                <span key={tagName} className="tag-chip">
                  {tagName}
                  <button
                    type="button"
                    onClick={() => updateFilter('tags', currentFilters.tags.filter(t => t !== tagName))}
                    className="tag-remove"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Дата добавления */}
        <div className="filter-item">
          <label className="filter-label">Дата добавления</label>
          <div className="segment-control">
            {periodOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`segment-item ${currentFilters.added_period === option.value ? 'active' : ''}`}
                onClick={() => updateFilter('added_period', option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Сбросить */}
        {hasActiveFilters && (
          <div className="filter-item">
            <button
              type="button"
              onClick={clearAllFilters}
              className="reset-filters"
            >
              Сбросить
            </button>
          </div>
        )}
      </div>
    </div>
  )
}