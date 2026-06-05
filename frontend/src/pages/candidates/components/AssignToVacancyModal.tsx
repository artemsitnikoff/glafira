import { useState } from 'react'
import { useDebounce } from '../../../hooks/useDebounce'
import type { ApiError } from '../../../api/aliases'
import { useAssignToVacancy } from '../../../api/hooks/useCandidates'
import { useVacancies } from '../../../api/hooks/useVacancies'
import { Icon } from '@/components/ui/Icon'
import './AssignToVacancyModal.css'

// Назначение/перевод кандидата на вакансию: поиск сверху + список вакансий, клик по строке
// назначает кандидата (создаёт application на этап «Добавлен»). Работает и для кандидата
// без привязки (первое назначение), и для уже привязанного (добавить в ещё одну вакансию).
interface Props {
  candidateId: string
  candidateName: string
  isOpen: boolean
  onClose: () => void
}

export function AssignToVacancyModal({ candidateId, candidateName, isOpen, onClose }: Props) {
  const [searchQuery, setSearchQuery] = useState('')
  const [apiError, setApiError] = useState<string | null>(null)
  const [assigningId, setAssigningId] = useState<string | null>(null)

  const debouncedSearch = useDebounce(searchQuery, 200)
  const assignMutation = useAssignToVacancy()

  const { data: vacanciesData, isLoading } = useVacancies({
    search: debouncedSearch || null,
    status: 'active',
    page_size: 50,
  })
  const vacancies = vacanciesData?.items || []

  const handleAssign = async (vacancyId: string) => {
    if (assigningId) return
    setApiError(null)
    setAssigningId(vacancyId)
    try {
      // stage 'added' — системный этап «Добавлен» (как при ручном создании с вакансией)
      await assignMutation.mutateAsync({
        candidateId,
        data: { vacancy_id: vacancyId, stage: 'added' },
      })
      // useAssignToVacancy сам инвалидирует кэш и ведёт в воронку
      onClose()
    } catch (error: unknown) {
      const e = error as ApiError
      setApiError(
        e.error?.code === 'CONFLICT'
          ? 'Кандидат уже назначен на эту вакансию'
          : e.error?.message || 'Не удалось назначить кандидата'
      )
      setAssigningId(null)
    }
  }

  if (!isOpen) return null

  return (
    <div className="avm-backdrop" onClick={onClose}>
      <div className="avm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="avm-head">
          <div>
            <h3>Перевести на вакансию</h3>
            <div className="avm-sub">{candidateName}</div>
          </div>
          <button className="avm-close" onClick={onClose} aria-label="Закрыть">
            <Icon name="x" size={18} />
          </button>
        </div>

        <div className="avm-search">
          <Icon name="search" size={15} />
          <input
            autoFocus
            type="text"
            placeholder="Поиск по названию вакансии…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {apiError && <div className="avm-error">{apiError}</div>}

        <div className="avm-list">
          {isLoading ? (
            <div className="avm-empty">Загрузка вакансий…</div>
          ) : vacancies.length === 0 ? (
            <div className="avm-empty">
              {searchQuery ? 'Вакансии не найдены' : 'Нет активных вакансий'}
            </div>
          ) : (
            vacancies.map((v) => (
              <button
                key={v.id}
                type="button"
                className="avm-item"
                onClick={() => handleAssign(v.id)}
                disabled={!!assigningId}
              >
                <Icon name="briefcase" size={15} className="avm-item-icon" />
                <span className="avm-item-name">{v.name}</span>
                {assigningId === v.id ? (
                  <span className="avm-item-go">Назначаю…</span>
                ) : (
                  <Icon name="arrow-right" size={15} className="avm-item-arrow" />
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
