import { useNavigate } from 'react-router-dom'
import type { ApplicationHistoryItem } from '../../../api/aliases'

interface Props {
  applications: ApplicationHistoryItem[]
  isLoading: boolean
  onAssignClick: () => void
}

export function ApplicationsHistoryBlock({ applications, isLoading, onAssignClick }: Props) {
  const navigate = useNavigate()

  const formatDate = (date: string | null) => {
    if (!date) return null
    return new Date(date).toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    })
  }

  const getVacancyStatusLabel = (status: string) => {
    switch (status) {
      case 'active': return 'Активна'
      case 'archived': return 'В архиве'
      case 'closed': return 'Закрыта'
      case 'frozen': return 'Заморожена'
      default: return status
    }
  }

  const getVacancyStatusClass = (status: string) => {
    switch (status) {
      case 'active': return 'status-active'
      case 'archived': return 'status-archived'
      case 'closed': return 'status-closed'
      case 'frozen': return 'status-frozen'
      default: return 'status-default'
    }
  }

  const getScoreBadgeClass = (score: number | null | undefined) => {
    if (score === null || score === undefined) return 'score-badge small neutral'
    if (score >= 80) return 'score-badge small green'
    if (score >= 50) return 'score-badge small yellow'
    return 'score-badge small red'
  }

  const handleApplicationClick = (application: ApplicationHistoryItem) => {
    navigate(`/vacancies/${application.vacancy_id}/candidates/${application.application_id}`)
  }

  if (isLoading) {
    return (
      <div className="applications-history-block">
        <h2>История участия в вакансиях</h2>
        <div className="history-loading">
          <div className="skeleton-rows">
            {Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="skeleton-row">
                <div className="skeleton-element" style={{ width: 300, height: 20 }} />
                <div className="skeleton-element" style={{ width: 100, height: 16 }} />
                <div className="skeleton-element" style={{ width: 200, height: 16 }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (applications.length === 0) {
    return (
      <div className="applications-history-block">
        <div className="no-applications">
          <div className="no-apps-message">
            Кандидат не участвовал ни в одной вакансии
          </div>
          <button
            onClick={onAssignClick}
            className="btn btn-primary"
          >
            Назначить на вакансию
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="applications-history-block">
      <h2>История участия в вакансиях ({applications.length})</h2>

      <div className="history-list">
        {applications.map((app) => (
          <div
            key={app.application_id}
            className="history-item"
            onClick={() => handleApplicationClick(app)}
          >
            <div className="item-header">
              <div className="vacancy-info">
                <span className="vacancy-marker">▣</span>
                <span className="vacancy-name" title={app.vacancy_name}>
                  {app.vacancy_name}
                </span>
              </div>
              <div
                className="stage-chip"
                style={{ backgroundColor: app.stage_color }}
              >
                {app.stage}
              </div>
            </div>

            <div className="item-details">
              <div className="detail-line">
                {app.client_name && (
                  <span>Заказчик: {app.client_name}</span>
                )}
                <span className={`vacancy-status ${getVacancyStatusClass(app.vacancy_status)}`}>
                  {getVacancyStatusLabel(app.vacancy_status)}
                </span>
              </div>

              <div className="detail-line">
                {app.selected_at && (
                  <span>Отбор: {formatDate(app.selected_at)}</span>
                )}
                {app.stage_changed_at && app.stage_changed_at !== app.selected_at && (
                  <span>
                    {app.stage === 'rejected' ? 'Отказ' : 'Изменение стадии'}: {formatDate(app.stage_changed_at)}
                  </span>
                )}
                {app.ai_score !== null && (
                  <span>
                    Скоринг: <span className={getScoreBadgeClass(app.ai_score)}>{app.ai_score}</span>
                  </span>
                )}
              </div>

              {app.reject_reason && (
                <div className="detail-line reject-reason">
                  Причина отказа: {app.reject_reason}
                </div>
              )}

              {app.recruiter_name && (
                <div className="detail-line recruiter">
                  Рекрутер: {app.recruiter_name}
                </div>
              )}
            </div>

            <div className="item-arrow">→</div>
          </div>
        ))}
      </div>
    </div>
  )
}