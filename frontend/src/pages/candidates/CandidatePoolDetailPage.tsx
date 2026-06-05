import { useState } from 'react'
import './CandidatePoolDetailPage.css'
import '../funnel/candidate-detail/CandidateDetail.css'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { useCandidate, useCandidateApplications } from '../../api/hooks/useCandidates'
import { useRequestConsent } from '@/api/mutations/candidateDetail'
import { AssignToVacancyModal } from './components/AssignToVacancyModal'
import { Icon } from '@/components/ui/Icon'
import { ScoreLabel } from '@/components/ui/ScoreLabel'
import { StageChip } from '@/components/ui/StageChip'

// Карточка кандидата в пуле = ТА ЖЕ карточка, что в воронке (эталон: «точь-в-точь как в
// вакансиях»). Переиспользуем шапку (CandidateHeader / cd-header), 7 табов (cc-tabs) и
// тулбар — всё внутри .cnd-funnel-wrap .cand-detail. Сверху — «История участия в вакансиях».
import { CandidateHeader } from '../funnel/candidate-detail/CandidateHeader'
import { ResumeTab } from '../funnel/candidate-detail/tabs/ResumeTab'
import { EvaluationTab } from '../funnel/candidate-detail/tabs/EvaluationTab'
import { VerificationTab } from '../funnel/candidate-detail/tabs/VerificationTab'
import { ChatTab } from '../funnel/candidate-detail/tabs/ChatTab'
import { DocumentsTab } from '../funnel/candidate-detail/tabs/DocumentsTab'
import { CommentsTab } from '../funnel/candidate-detail/tabs/CommentsTab'
import { AllActionsTab } from '../funnel/candidate-detail/tabs/AllActionsTab'

const TABS = [
  { key: 'resume', label: 'Резюме' },
  { key: 'evaluation', label: 'Оценка AI' },
  { key: 'verification', label: 'Верификация' },
  { key: 'chat', label: 'Чат' },
  { key: 'docs', label: 'Документы' },
  { key: 'comments', label: 'Комментарии' },
  { key: 'actions', label: 'Все действия' }
] as const

type TabKey = typeof TABS[number]['key']

export function CandidatePoolDetailPage() {
  const { id: candidateId } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const [showAssignModal, setShowAssignModal] = useState(false)

  const activeTab = (searchParams.get('tab') as TabKey) || 'resume'

  const {
    data: candidate,
    isLoading: candidateLoading,
    error: candidateError
  } = useCandidate(candidateId!)

  const {
    data: applications,
    isLoading: applicationsLoading
  } = useCandidateApplications(candidateId!)

  const consentMutation = useRequestConsent(candidateId || '')

  const handleBackToPool = () => {
    // К СПИСКУ кандидатов (не navigate(-1) — иначе ходит по истории смены табов),
    // восстанавливая сохранённые фильтры пула.
    const savedFilters = sessionStorage.getItem('pool:filters')
    navigate(savedFilters ? `/candidates?${savedFilters}` : '/candidates')
  }

  const handleTabChange = (tabKey: TabKey) => {
    const newParams = new URLSearchParams(searchParams)
    if (tabKey === 'resume') {
      newParams.delete('tab')
    } else {
      newParams.set('tab', tabKey)
    }
    // replace — смена таба не плодит записи истории (чтобы Назад вёл к списку, а не по табам)
    setSearchParams(newParams, { replace: true })
  }

  const fmtDate = (iso: string | null | undefined) =>
    iso ? new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''

  const renderTabContent = () => {
    if (!candidate) return null
    const commonProps = { candidate, fromPool: true }
    switch (activeTab) {
      case 'resume':
        return <ResumeTab {...commonProps} onOpenAI={() => handleTabChange('evaluation')} />
      case 'evaluation':
        return <EvaluationTab {...commonProps} />
      case 'verification':
        return <VerificationTab candidateId={candidate.id} hasPdn={candidate.has_pdn ?? false} />
      case 'chat':
        return <ChatTab {...commonProps} />
      case 'docs':
        return <DocumentsTab {...commonProps} />
      case 'comments':
        return <CommentsTab {...commonProps} />
      case 'actions':
        return <AllActionsTab candidateId={candidate.id} />
      default:
        return <ResumeTab {...commonProps} onOpenAI={() => handleTabChange('evaluation')} />
    }
  }

  if (candidateError) {
    return (
      <div className="error-state">
        <h2>Кандидат не найден</h2>
        <button onClick={handleBackToPool} className="btn btn-primary">
          ← Назад к кандидатам
        </button>
      </div>
    )
  }

  if (candidateLoading || !candidate) {
    return (
      <div className="candidate-detail-page loading">
        <div className="skeleton-header">
          <div className="skeleton-element" style={{ width: 200, height: 24 }} />
          <div className="skeleton-element" style={{ width: 300, height: 20 }} />
        </div>
      </div>
    )
  }

  return (
    <div className="cfp-page">
      {/* Назад */}
      <div className="cfp-back-row">
        <button className="cfp-back" onClick={handleBackToPool}>
          <Icon name="chevron-left" size={14} /> Назад к кандидатам
        </button>
      </div>

      {/* История участия в вакансиях (как в эталоне — над карточкой) */}
      <div className="cfp-history">
        <div className="cfp-section-head">
          <h2 className="cfp-section-title">История участия в вакансиях</h2>
          <span className="cfp-section-count">{applications?.length || 0}</span>
        </div>

        {applicationsLoading ? (
          <div className="cfp-mini-empty">Загрузка истории...</div>
        ) : !applications || applications.length === 0 ? (
          <div className="cfp-history-empty">
            <span>Кандидат пока ни в одной вакансии</span>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setShowAssignModal(true)}
            >
              <Icon name="briefcase" size={14} /> Назначить на вакансию
            </button>
          </div>
        ) : (
          <div className="cfp-history-list">
            {applications.map((app, i) => (
              <div key={i} className="cfp-h-row">
                <div className="cfp-h-row-main">
                  <div className="cfp-h-vac">
                    <Icon name="briefcase" size={14} style={{ color: 'var(--fg-3)', flex: 'none' }} />
                    <span className="cfp-h-vac-title">{app.vacancy_name}</span>
                    <span className={`cfp-vac-status ${app.vacancy_status === 'active' ? 'on' : 'off'}`}>
                      {app.vacancy_status === 'active' ? 'Активна' : 'В архиве'}
                    </span>
                  </div>
                  <div className="cfp-h-stage">
                    <StageChip stage={app.stage} size="sm" />
                  </div>
                </div>
                <div className="cfp-h-row-meta">
                  <span>Заказчик: <b>{app.client_name}</b></span>
                  <span className="sep">·</span>
                  <span>Рекрутер: {app.recruiter_name}</span>
                  <span className="sep">·</span>
                  <span className="t-mono">
                    Отбор: {fmtDate(app.selected_at)}
                    {app.stage_changed_at && ['hired', 'rejected'].includes(app.stage) &&
                      ` → ${app.stage === 'hired' ? 'Нанят' : 'Отказ'}: ${fmtDate(app.stage_changed_at)}`}
                  </span>
                  <span className="sep">·</span>
                  <span>Скоринг: <ScoreLabel value={app.ai_score ?? null} size="sm" /></span>
                </div>
                {app.reject_reason && (
                  <div className="cfp-h-reject">Причина отказа: {app.reject_reason}</div>
                )}
                <button
                  className="cfp-h-go"
                  title="Перейти к карточке внутри вакансии"
                  onClick={() => navigate(`/vacancies/${app.vacancy_id}`)}
                >
                  Перейти <Icon name="arrow-right" size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Карточка соискателя — точь-в-точь как в воронке (cd-toolbar + cd-header + cc-tabs) */}
      <div className="cfp-detail-host">
        <div className="cnd-funnel-wrap">
          <div className="cand-detail">
            {/* Тулбар: Перевести на вакансию / Комментарий / ПдН (без «Отклонить» — без вакансии не имеет смысла) */}
            <div className="cd-toolbar">
              <button className="btn btn-success btn-sm" onClick={() => setShowAssignModal(true)}>
                <Icon name="briefcase" size={14} /> Перевести на вакансию
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => handleTabChange('comments')}>
                <Icon name="message-square" size={14} /> Комментарий
              </button>
              {candidate.has_pdn ? (
                <span className="cd-pdn-confirmed" title="Согласие на обработку ПдН получено">
                  ПдН
                  <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
                    <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
              ) : (
                <button
                  className="btn btn-secondary btn-sm cd-pdn-btn"
                  onClick={() => consentMutation.mutate({ channel: 'email' })}
                  disabled={consentMutation.isPending}
                  title="Запросить согласие на обработку персональных данных"
                >
                  <Icon name="shield" size={14} /> ПдН
                </button>
              )}
              <div style={{ flex: 1 }} />
              <button className="icon-btn" onClick={handleBackToPool} title="Закрыть">
                <Icon name="x" size={18} />
              </button>
            </div>

            {/* Шапка кандидата — общая с воронкой (cd-header). application=null: в пуле нет
                одной «контекстной» заявки, источник/город берутся из самого кандидата. */}
            <CandidateHeader candidateId={candidate.id} application={null} />

            {/* Табы */}
            <div className="cc-tabs">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  className={`cc-tab ${activeTab === tab.key ? 'active' : ''}`}
                  onClick={() => handleTabChange(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="cc-content">
              {renderTabContent()}
            </div>
          </div>
        </div>
      </div>

      {/* Перевод/назначение на вакансию (поиск + список) */}
      {showAssignModal && (
        <AssignToVacancyModal
          candidateId={candidate.id}
          candidateName={candidate.full_name}
          isOpen={showAssignModal}
          onClose={() => setShowAssignModal(false)}
        />
      )}
    </div>
  )
}
