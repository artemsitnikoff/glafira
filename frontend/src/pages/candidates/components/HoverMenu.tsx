import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { CandidateGridItem } from '../../../api/aliases'
import { useDeleteCandidate } from '../../../api/mutations/candidates'
import { AssignToVacancyModal } from './AssignToVacancyModal'

interface Props {
  candidate: CandidateGridItem
  onMenuClick?: (e: React.MouseEvent) => void
}

export function HoverMenu({ candidate, onMenuClick }: Props) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [showAssignModal, setShowAssignModal] = useState(false)

  const deleteMutation = useDeleteCandidate()

  const handleOpen = () => {
    // Save current state for back navigation
    sessionStorage.setItem('pool:filters', searchParams.toString())
    sessionStorage.setItem('pool:scrollY', String(window.scrollY))

    navigate(`/candidates/${candidate.id}`)
  }

  const handleAssign = () => {
    setShowAssignModal(true)
  }

  const handleChat = () => {
    // Save current state for back navigation
    sessionStorage.setItem('pool:filters', searchParams.toString())
    sessionStorage.setItem('pool:scrollY', String(window.scrollY))

    navigate(`/candidates/${candidate.id}?tab=chat`)
  }

  const handleMerge = () => {
    // TODO: Implement merge functionality when backend is ready
    console.log('Merge functionality not implemented yet')
  }

  const handleDelete = async () => {
    const confirmed = window.confirm(
      `Удалить кандидата ${candidate.full_name} из базы? Действие необратимо.`
    )

    if (!confirmed) return

    try {
      await deleteMutation.mutateAsync(candidate.id)
      // Mutation automatically invalidates candidates query
    } catch (error: any) {
      console.error('Failed to delete candidate:', error)

      let errorMessage = 'Произошла ошибка при удалении кандидата'

      if (error?.response?.status === 409) {
        errorMessage = 'Невозможно удалить кандидата: есть связанные заявки на вакансии'
      } else if (error?.response?.status === 422) {
        errorMessage = 'Невозможно удалить кандидата: есть связанные данные'
      }

      alert(errorMessage)
    }
  }

  return (
    <>
      <div className="hover-menu" onClick={onMenuClick}>
        <button className="menu-trigger">⋯</button>
        <div className="menu-dropdown">
          <button type="button" onClick={handleOpen} className="menu-item">
            Открыть
          </button>
          <button type="button" onClick={handleAssign} className="menu-item">
            Назначить на вакансию
          </button>
          <button type="button" onClick={handleChat} className="menu-item">
            Написать
          </button>
          <button
            type="button"
            onClick={handleMerge}
            className="menu-item disabled"
            disabled
            title="Функция в разработке"
          >
            Объединить дубли
          </button>
          <div className="menu-separator" />
          <button
            type="button"
            onClick={handleDelete}
            className="menu-item danger"
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? 'Удаление...' : 'Удалить'}
          </button>
        </div>
      </div>

      {showAssignModal && (
        <AssignToVacancyModal
          candidate={candidate}
          isOpen={showAssignModal}
          onClose={() => setShowAssignModal(false)}
        />
      )}
    </>
  )
}