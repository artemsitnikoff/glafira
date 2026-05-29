import { useState } from 'react'
import './CandidatesPool.css'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { useCandidate, useCandidateApplications } from '../../api/hooks/useCandidates'
import { ApplicationsHistoryBlock } from './components/ApplicationsHistoryBlock'
import { AssignToVacancyModal } from './components/AssignToVacancyModal'

// Import existing tabs with fromPool prop support
import { ResumeTab } from '../funnel/candidate-detail/tabs/ResumeTab'
import { ChatTab } from '../funnel/candidate-detail/tabs/ChatTab'
import { DocumentsTab } from '../funnel/candidate-detail/tabs/DocumentsTab'
import { EvaluationTab } from '../funnel/candidate-detail/tabs/EvaluationTab'
import { CommentsTab } from '../funnel/candidate-detail/tabs/CommentsTab'
import { AllActionsTab } from '../funnel/candidate-detail/tabs/AllActionsTab'
import { VerificationTab } from '../funnel/candidate-detail/tabs/VerificationTab'

const TABS = [
  { key: 'resume', label: 'Резюме' },
  { key: 'chat', label: 'Чат' },
  { key: 'documents', label: 'Документы' },
  { key: 'evaluation', label: 'Оценка AI' },
  { key: 'comments', label: 'Комментарии' },
  { key: 'actions', label: 'Все действия' },
  { key: 'verification', label: 'Верификация' }
] as const

type TabKey = typeof TABS[number]['key']

export function CandidatePoolDetailPage() {
  const { candidateId } = useParams<{ candidateId: string }>()
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

  const handleBackToPool = () => {
    const savedFilters = sessionStorage.getItem('pool:filters')
    const targetUrl = savedFilters
      ? `/candidates?${savedFilters}`
      : '/candidates'

    navigate(targetUrl)
  }

  const handleTabChange = (tabKey: TabKey) => {
    const newParams = new URLSearchParams(searchParams)
    if (tabKey === 'resume') {
      newParams.delete('tab')
    } else {
      newParams.set('tab', tabKey)
    }
    setSearchParams(newParams)
  }

  const formatContactInfo = () => {
    if (!candidate) return ''

    const parts = []
    if (candidate.age) parts.push(`${candidate.age} лет`)
    if (candidate.last_position) parts.push(candidate.last_position)
    if (candidate.last_company) parts.push(candidate.last_company)
    if (candidate.last_period) parts.push(candidate.last_period)

    return parts.join(' / ')
  }

  const getScoreBadgeClass = (score: number | null | undefined) => {
    if (score === null || score === undefined) return 'score-badge large neutral'
    if (score >= 80) return 'score-badge large green'
    if (score >= 50) return 'score-badge large yellow'
    return 'score-badge large red'
  }

  const handleScoreBadgeClick = () => {
    handleTabChange('evaluation')
  }

  const renderTabContent = () => {
    if (!candidate) return null

    const commonProps = {
      candidate,
      fromPool: true
    }

    switch (activeTab) {
      case 'resume':
        return <ResumeTab {...commonProps} onOpenAI={() => handleTabChange('evaluation')} />
      case 'chat':
        return <ChatTab {...commonProps} />
      case 'documents':
        return <DocumentsTab {...commonProps} />
      case 'evaluation':
        return <EvaluationTab {...commonProps} />
      case 'comments':
        return <CommentsTab {...commonProps} />
      case 'actions':
        return <AllActionsTab {...commonProps} />
      case 'verification':
        return <VerificationTab {...commonProps} />
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
    <div className="candidate-pool-detail-page">
      {/* Back Navigation */}
      <div className="back-navigation">
        <button
          onClick={handleBackToPool}
          className="back-button"
          aria-label="Назад к кандидатам"
        >
          ← Назад к кандидатам
        </button>
      </div>

      {/* Candidate Header */}
      <div className="candidate-header sticky">
        <div className="header-row-1">
          <div className="name-and-actions">
            <h1 className="candidate-name">{candidate.full_name}</h1>
            <div className="header-actions">
              <button
                className="btn btn-secondary"
                onClick={() => handleTabChange('chat')}
              >
                Написать
              </button>
              {candidate.phone ? (
                <a
                  href={`tel:${candidate.phone}`}
                  className="btn btn-secondary"
                  style={{ textDecoration: 'none' }}
                >
                  Позвонить
                </a>
              ) : null}
              <button
                className="btn btn-primary"
                onClick={() => setShowAssignModal(true)}
              >
                Назначить на вакансию
              </button>
              <div className="more-menu">
                <button className="btn btn-ghost">⋯</button>
              </div>
            </div>
          </div>
          <div
            className={getScoreBadgeClass(candidate.ai_score)}
            onClick={handleScoreBadgeClick}
            title="Перейти к оценке AI"
            style={{ cursor: 'pointer' }}
          >
            {candidate.ai_score ?? '—'}
          </div>
        </div>

        <div className="header-row-2">
          <div className="info-line">
            {formatContactInfo()}
          </div>
        </div>

        <div className="header-row-3">
          <div className="contacts">
            {candidate.phone && (
              <a href={`tel:${candidate.phone}`} className="contact-link phone">
                {candidate.phone}
              </a>
            )}
            {candidate.messengers && candidate.messengers.length > 0 && (
              <div className="messenger-badges">
                {candidate.messengers.map((messenger) => (
                  <span
                    key={messenger}
                    className={`messenger-badge ${messenger}`}
                    onClick={() => handleTabChange('chat')}
                    title={`Открыть чат в ${messenger}`}
                  >
                    {messenger}
                  </span>
                ))}
              </div>
            )}
            {candidate.email && (
              <a href={`mailto:${candidate.email}`} className="contact-link email">
                {candidate.email}
              </a>
            )}
          </div>
        </div>

        <div className="header-row-4">
          <div className="location">
            Город: {candidate.city} {candidate.region && `(${candidate.region})`}
          </div>
        </div>

        <div className="header-row-5">
          <div className="tags">
            {candidate.tags?.map((tag) => (
              <span
                key={tag.id}
                className="tag-chip"
                style={{ backgroundColor: tag.color || undefined }}
              >
                {tag.name}
              </span>
            ))}
            <button className="add-tag-button" title="Добавить тег">+</button>
          </div>
        </div>
      </div>

      {/* Applications History */}
      <ApplicationsHistoryBlock
        applications={applications || []}
        isLoading={applicationsLoading}
        onAssignClick={() => setShowAssignModal(true)}
      />

      {/* Tabs Navigation */}
      <div className="tabs-navigation">
        <div className="tabs-list">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`tab-button ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => handleTabChange(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {renderTabContent()}
      </div>

      {/* Assign Modal */}
      {showAssignModal && (
        <AssignToVacancyModal
          candidate={{
            id: candidate.id,
            display_number: candidate.display_number,
            full_name: candidate.full_name,
            age: candidate.age,
            last_position: candidate.last_position,
            last_company: candidate.last_company,
            last_period: candidate.last_period,
            ai_score: candidate.ai_score,
            avatar_url: null,
            is_duplicate: candidate.is_duplicate,
            has_pdn: candidate.has_pdn,
            last_vacancy: null,
            other_vacancies_count: 0
          }}
          isOpen={showAssignModal}
          onClose={() => setShowAssignModal(false)}
        />
      )}
    </div>
  )
}