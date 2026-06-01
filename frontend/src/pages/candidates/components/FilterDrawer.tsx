import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useVacancies } from '../../../api/hooks/useVacancies'
import { useTags } from '../../../api/hooks/useTags'
import { useCandidates } from '../../../api/hooks/useCandidates'
import { STAGES } from '../../../lib/stages'
import { Icon } from '../../../components/ui/Icon'
import type { CandidateFilters as FilterType } from '../../../api/hooks/useCandidates'

interface FilterDrawerProps {
  onClose: () => void
}

export function FilterDrawer({ onClose }: FilterDrawerProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [openSections, setOpenSections] = useState(new Set(['ai', 'source', 'vacancy']))

  // Load data for filter options
  const { data: vacanciesData } = useVacancies({ status: 'active', page_size: 100 })
  const { data: tagsData } = useTags()

  // Extract current filters
  const currentFilters = useMemo(() => {
    const city = searchParams.get('city') || ''
    const scoreMin = searchParams.get('score_min') ? Number(searchParams.get('score_min')) : 0
    const scoreMax = searchParams.get('score_max') ? Number(searchParams.get('score_max')) : 100
    const sources = searchParams.get('source') ? searchParams.get('source')!.split(',') : []
    const vacancies = searchParams.get('vacancy_id') ? searchParams.get('vacancy_id')!.split(',') : []
    const stages = searchParams.get('stage') ? searchParams.get('stage')!.split(',') : []
    const tags = searchParams.get('tags') ? searchParams.get('tags')!.split(',').filter(Boolean) : []
    const addedPeriod = searchParams.get('added_period') || ''

    return {
      city,
      scoreMin,
      scoreMax,
      sources: new Set(sources),
      vacancies: new Set(vacancies),
      stages: new Set(stages),
      tags: new Set(tags),
      addedPeriod
    }
  }, [searchParams])

  // Calculate filtered count using the same filters that would be applied
  const filtersForCount = useMemo((): FilterType => {
    const params: FilterType = {}

    if (currentFilters.city) params.city = currentFilters.city
    if (currentFilters.scoreMin > 0) params.score_min = currentFilters.scoreMin
    if (currentFilters.scoreMax < 100) params.score_max = currentFilters.scoreMax
    if (currentFilters.sources.size > 0) params.source = Array.from(currentFilters.sources).join(',')
    if (currentFilters.vacancies.size > 0) params.vacancy_id = Array.from(currentFilters.vacancies).join(',')
    if (currentFilters.stages.size > 0) params.stage = Array.from(currentFilters.stages).join(',')
    if (currentFilters.tags.size > 0) params.tags = Array.from(currentFilters.tags)
    if (currentFilters.addedPeriod) params.added_period = currentFilters.addedPeriod

    // Include search from URL
    const search = searchParams.get('search')
    if (search) params.search = search

    return params
  }, [currentFilters, searchParams])

  const { data: countData } = useCandidates(filtersForCount)
  const filteredCount = countData?.pages?.[0]?.total ?? 0

  // Count active filters
  const activeFilterCount = useMemo(() => {
    let count = 0
    if (currentFilters.city) count++
    if (currentFilters.scoreMin > 0 || currentFilters.scoreMax < 100) count++
    if (currentFilters.sources.size > 0) count++
    if (currentFilters.vacancies.size > 0) count++
    if (currentFilters.stages.size > 0) count++
    if (currentFilters.tags.size > 0) count++
    if (currentFilters.addedPeriod) count++
    return count
  }, [currentFilters])

  const toggleSection = (id: string) => {
    const next = new Set(openSections)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setOpenSections(next)
  }

  const updateFilter = (key: string, values: Set<string> | string | number) => {
    const newParams = new URLSearchParams(searchParams)

    if (key === 'city') {
      if (values) {
        newParams.set('city', values as string)
      } else {
        newParams.delete('city')
      }
    } else if (key === 'scoreMin') {
      const numValue = values as number
      if (numValue && numValue > 0) {
        newParams.set('score_min', String(numValue))
      } else {
        newParams.delete('score_min')
      }
    } else if (key === 'scoreMax') {
      const numValue = values as number
      if (numValue && numValue < 100) {
        newParams.set('score_max', String(numValue))
      } else {
        newParams.delete('score_max')
      }
    } else if (key === 'addedPeriod') {
      if (values) {
        newParams.set('added_period', values as string)
      } else {
        newParams.delete('added_period')
      }
    } else {
      // For sets (sources, vacancies, stages, tags)
      const valueSet = values as Set<string>
      if (valueSet.size > 0) {
        newParams.set(key, Array.from(valueSet).join(','))
      } else {
        newParams.delete(key)
      }
    }

    setSearchParams(newParams)
  }

  const toggleSetFilter = (key: string, value: string) => {
    const currentSet = key === 'sources' ? currentFilters.sources :
                       key === 'vacancies' ? currentFilters.vacancies :
                       key === 'stages' ? currentFilters.stages :
                       currentFilters.tags

    const newSet = new Set(currentSet)
    if (newSet.has(value)) {
      newSet.delete(value)
    } else {
      newSet.add(value)
    }

    const paramKey = key === 'sources' ? 'source' :
                     key === 'vacancies' ? 'vacancy_id' :
                     key === 'stages' ? 'stage' :
                     'tags'

    updateFilter(paramKey, newSet)
  }

  const resetAllFilters = () => {
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

  const Section = ({ id, title, count, children }: {
    id: string
    title: string
    count: number
    children: React.ReactNode
  }) => {
    const open = openSections.has(id)
    return (
      <div className={`fdr-section ${open ? 'open' : ''}`}>
        <button className="fdr-section-head" onClick={() => toggleSection(id)}>
          <span className="fdr-section-title">{title}</span>
          {count > 0 && <span className="fdr-section-count">{count}</span>}
          <Icon name="chevD" size={14} className={`fdr-chev ${open ? 'rot' : ''}`}/>
        </button>
        {open && <div className="fdr-section-body">{children}</div>}
      </div>
    )
  }

  // Source options (real from CHECK)
  const sourceOptions = [
    { id: 'hh', label: 'hh.ru' },
    { id: 'avito', label: 'Авито' },
    { id: 'superjob', label: 'SuperJob' },
    { id: 'telegram', label: 'Глафира · Telegram' },
    { id: 'referral', label: 'Реферал' },
    { id: 'direct', label: 'Прямое обращение' },
    { id: 'agency', label: 'Агентство' },
    { id: 'import', label: 'Импорт' },
    { id: 'manual', label: 'Ручной ввод' },
    { id: 'other', label: 'Другое' }
  ]

  // Period options
  const periodOptions = [
    { id: '', label: 'Всё время' },
    { id: '7d', label: 'За 7 дней' },
    { id: '30d', label: 'За 30 дней' },
    { id: '3m', label: 'За 3 месяца' }
  ]

  return (
    <>
      <div className="fdr-overlay" onClick={onClose}/>
      <aside className="fdr">
        <div className="fdr-head">
          <div className="fdr-title">
            Фильтры
            {activeFilterCount > 0 && (
              <button className="fdr-reset-circle" onClick={resetAllFilters} title="Сбросить">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 12a9 9 0 1 0 3-6.7"/>
                  <path d="M3 4v5h5"/>
                </svg>
              </button>
            )}
          </div>
          <button className="icon-btn" onClick={onClose}>
            <Icon name="x" size={18}/>
          </button>
        </div>

        <div className="fdr-pin-row">
          {/* «Сохранённые фильтры» в эталоне есть, но фичи (бэка) у нас нет → честно disabled «Скоро» */}
          <button className="fdr-pin-btn" disabled title="Скоро">
            <Icon name="bookmark" size={13}/>
            Сохранить настроенный фильтр
          </button>
        </div>

        <div className="fdr-body">
          <Section
            id="ai"
            title="AI-скоринг"
            count={currentFilters.scoreMin > 0 || currentFilters.scoreMax < 100 ? 1 : 0}
          >
            <div className="fdr-slider-row">
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={currentFilters.scoreMin}
                onChange={e => updateFilter('scoreMin', Number(e.target.value))}
              />
              <span className="fdr-slider-val t-mono">от {currentFilters.scoreMin}</span>
            </div>
            <div className="fdr-tick-row">
              <span>0</span><span>50</span><span>100</span>
            </div>
          </Section>

          <Section id="source" title="Источник" count={currentFilters.sources.size}>
            <div className="fdr-chip-row">
              {sourceOptions.map(source => (
                <button
                  key={source.id}
                  className={`filter-chip ${currentFilters.sources.has(source.id) ? 'active' : ''}`}
                  onClick={() => toggleSetFilter('sources', source.id)}
                >
                  {source.label}
                </button>
              ))}
            </div>
          </Section>

          <Section id="vacancy" title="Вакансия" count={currentFilters.vacancies.size}>
            <div className="fdr-chip-row">
              {vacanciesData?.items?.map(vacancy => (
                <button
                  key={vacancy.id}
                  className={`filter-chip ${currentFilters.vacancies.has(vacancy.id) ? 'active' : ''}`}
                  onClick={() => toggleSetFilter('vacancies', vacancy.id)}
                >
                  {vacancy.name}
                </button>
              ))}
            </div>
          </Section>

          <Section id="stage" title="Этап воронки" count={currentFilters.stages.size}>
            <div className="fdr-chip-row">
              {Object.values(STAGES).map(stage => (
                <button
                  key={stage.key}
                  className={`filter-chip ${currentFilters.stages.has(stage.key) ? 'active' : ''}`}
                  onClick={() => toggleSetFilter('stages', stage.key)}
                >
                  <span className="stage-dot" style={{background: stage.color, marginRight: 6}}/>
                  {stage.label}
                </button>
              ))}
              <button
                className={`filter-chip ${currentFilters.stages.has('pool') ? 'active' : ''}`}
                onClick={() => toggleSetFilter('stages', 'pool')}
              >
                В базе (без вакансии)
              </button>
            </div>
          </Section>

          <Section id="city" title="Город проживания" count={currentFilters.city ? 1 : 0}>
            <input
              type="text"
              placeholder="Введите город..."
              value={currentFilters.city}
              onChange={e => updateFilter('city', e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid var(--border-1)',
                borderRadius: 'var(--radius-md)',
                fontSize: '13px'
              }}
            />
          </Section>

          <Section id="exp" title="Опыт работы" count={0}>
            <div className="fdr-chip-row">
              {[
                { id: '<1', label: 'до 1 года' },
                { id: '1-3', label: '1–3 года' },
                { id: '3-5', label: '3–5 лет' },
                { id: '5+', label: '5+ лет' }
              ].map(exp => (
                <button
                  key={exp.id}
                  className="filter-chip"
                  disabled
                  style={{ opacity: 0.5, cursor: 'not-allowed' }}
                >
                  {exp.label}
                </button>
              ))}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--fg-3)', marginTop: '8px' }}>
              Скоро
            </div>
          </Section>

          <Section id="period" title="Период добавления" count={currentFilters.addedPeriod ? 1 : 0}>
            <div className="fdr-chip-row">
              {periodOptions.map(period => (
                <button
                  key={period.id}
                  className={`filter-chip ${currentFilters.addedPeriod === period.id ? 'active' : ''}`}
                  onClick={() => updateFilter('addedPeriod', period.id)}
                >
                  {period.label}
                </button>
              ))}
            </div>
          </Section>

          {tagsData && tagsData.length > 0 && (
            <Section id="tags" title="Теги" count={currentFilters.tags.size}>
              <div className="fdr-chip-row">
                {tagsData.map(tag => (
                  <button
                    key={tag.id}
                    className={`filter-chip ${currentFilters.tags.has(tag.id) ? 'active' : ''}`}
                    onClick={() => toggleSetFilter('tags', tag.id)}
                  >
                    {tag.name}
                  </button>
                ))}
              </div>
            </Section>
          )}
        </div>

        <div className="fdr-foot">
          <button className="btn btn-secondary btn-sm" onClick={resetAllFilters}>
            Сбросить всё
          </button>
          <button className="btn btn-primary btn-sm" onClick={onClose}>
            Показать {filteredCount}
          </button>
        </div>
      </aside>
    </>
  )
}