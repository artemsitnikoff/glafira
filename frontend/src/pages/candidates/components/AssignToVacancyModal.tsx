import { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useDebounce } from '../../../hooks/useDebounce'
import type { CandidateGridItem, ApiError } from '../../../api/aliases'
import { useAssignToVacancy } from '../../../api/hooks/useCandidates'
import { useVacancies } from '../../../api/hooks/useVacancies'
import { useVacancyStages } from '../../../api/hooks/useVacancyStages'

interface Props {
  candidate: CandidateGridItem
  isOpen: boolean
  onClose: () => void
}

export function AssignToVacancyModal({ candidate, isOpen, onClose }: Props) {
  const [selectedVacancyId, setSelectedVacancyId] = useState('')
  const [selectedStage, setSelectedStage] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [apiError, setApiError] = useState<string | null>(null)

  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const debouncedSearch = useDebounce(searchQuery, 200)

  const assignMutation = useAssignToVacancy()

  const { data: vacanciesData, isLoading: vacanciesLoading } = useVacancies({
    search: debouncedSearch || null,
    status: 'active',
    page_size: 50
  })

  const filteredVacancies = useMemo(() => {
    return vacanciesData?.items || []
  }, [vacanciesData])

  // Этапы ВЫБРАННОЙ вакансии (без терминальных hired/rejected — в них не назначают).
  // useVacancyStages сам не фетчит при пустом id.
  const { data: vacancyStages } = useVacancyStages(selectedVacancyId)
  const availableStages = useMemo(() => {
    return (vacancyStages || [])
      .filter((s) => !s.is_terminal)
      .map((s) => ({ value: s.stage_key, label: s.label }))
  }, [vacancyStages])

  // При смене вакансии — выставить первый доступный этап (или сбросить, если этапов нет/не загружены).
  useEffect(() => {
    if (!availableStages.some((s) => s.value === selectedStage)) {
      setSelectedStage(availableStages[0]?.value || '')
    }
  }, [availableStages, selectedStage])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setApiError(null)

    if (!selectedVacancyId) return

    try {
      await assignMutation.mutateAsync({
        candidateId: candidate.id,
        data: {
          vacancy_id: selectedVacancyId,
          stage: selectedStage
        }
      })

      // Invalidate queries to refresh data
      await queryClient.invalidateQueries({ queryKey: ['candidates'] })
      await queryClient.invalidateQueries({
        queryKey: ['candidate', candidate.id, 'applications']
      })

      // Navigate to funnel
      navigate(`/vacancies/${selectedVacancyId}/candidates/${candidate.id}`)
      onClose()
    } catch (error: any) {
      // Handle conflict error (already assigned)
      const e = error as ApiError;
      if (e.error?.code === 'CONFLICT') {
        setApiError('Кандидат уже назначен на эту вакансию')
      } else {
        setApiError(e.error?.message || 'Произошла ошибка при назначении кандидата')
      }
    }
  }

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Назначить на вакансию</h2>
          <button
            type="button"
            onClick={onClose}
            className="modal-close"
            aria-label="Закрыть"
          >
            ×
          </button>
        </div>

        <div className="modal-body">
          <div className="candidate-info">
            <div className="candidate-avatar">
              {candidate.avatar_url ? (
                <img src={candidate.avatar_url} alt="" />
              ) : (
                <div className="avatar-placeholder">
                  {candidate.full_name.charAt(0)}
                </div>
              )}
            </div>
            <div className="candidate-details">
              <div className="name">{candidate.full_name}</div>
              <div className="profile">
                {[
                  candidate.age ? `${candidate.age} лет` : null,
                  candidate.last_position
                ].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="assign-form">
            <div className="form-group">
              <label htmlFor="vacancy-search">Вакансия *</label>
              <input
                id="vacancy-search"
                type="text"
                placeholder="Поиск по названию вакансии"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="search-input"
                disabled={assignMutation.isPending}
              />
              <select
                value={selectedVacancyId}
                onChange={(e) => setSelectedVacancyId(e.target.value)}
                className="vacancy-select"
                required
                disabled={assignMutation.isPending}
              >
                <option value="">
                  {vacanciesLoading ? 'Загрузка...' : 'Выберите вакансию'}
                </option>
                {filteredVacancies.map((vacancy) => (
                  <option key={vacancy.id} value={vacancy.id}>
                    {vacancy.name} {vacancy.status === 'active' ? '' : `(${vacancy.status})`}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="stage">Стадия</label>
              <select
                id="stage"
                value={selectedStage}
                onChange={(e) => setSelectedStage(e.target.value)}
                className="stage-select"
                disabled={!selectedVacancyId || assignMutation.isPending}
              >
                {!selectedVacancyId ? (
                  <option value="">Сначала выберите вакансию</option>
                ) : availableStages.length === 0 ? (
                  <option value="">Загрузка этапов…</option>
                ) : (
                  availableStages.map((stage) => (
                    <option key={stage.value} value={stage.value}>
                      {stage.label}
                    </option>
                  ))
                )}
              </select>
              <div className="help-text">
                Кандидат будет добавлен в выбранную стадию воронки
              </div>
            </div>

            {apiError && (
              <div className="form-error">
                {apiError}
              </div>
            )}

            <div className="form-actions">
              <button
                type="button"
                onClick={onClose}
                className="btn btn-secondary"
                disabled={assignMutation.isPending}
              >
                Отмена
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!selectedVacancyId || !selectedStage || assignMutation.isPending}
              >
                {assignMutation.isPending ? 'Назначение...' : 'Назначить'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}