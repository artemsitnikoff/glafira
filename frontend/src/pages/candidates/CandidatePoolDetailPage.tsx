import { useState } from 'react'
import './CandidatePoolDetailPage.css'
import '../funnel/candidate-detail/CandidateDetail.css'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { useCandidate, useCandidateApplications } from '../../api/hooks/useCandidates'
import { AssignToVacancyModal } from './components/AssignToVacancyModal'
import { messengerChannel } from '@/lib/messengers'
import { formatSalary as fmtSalary } from '@/lib/format'
import { Icon } from '@/components/ui/Icon'
import { Avatar } from '@/components/ui/Avatar'
import { ScoreLabel } from '@/components/ui/ScoreLabel'
import { StageChip } from '@/components/ui/StageChip'
import { CandidateTagPicker } from '@/components/CandidateTagPicker'
import { MessIconRound } from '@/components/ui/MessIconRound'

// Import existing tabs with fromPool prop support
import { ResumeTab } from '../funnel/candidate-detail/tabs/ResumeTab'
import { ChatTab } from '../funnel/candidate-detail/tabs/ChatTab'
import { DocumentsTab } from '../funnel/candidate-detail/tabs/DocumentsTab'
import { EvaluationTab } from '../funnel/candidate-detail/tabs/EvaluationTab'

const TABS = [
  { key: 'resume', label: 'Резюме' },
  { key: 'evaluation', label: 'Оценка AI' },
  { key: 'chat', label: 'Чат' },
  { key: 'documents', label: 'Документы' }
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

  const formatContactInfo = () => {
    if (!candidate) return ''

    // Эталон: «возраст · стаж на последнем месте · последнее место» (без должности).
    // last_tenure/last_company приходят с бэка (вычислены из самой свежей записи опыта).
    const tenure = (candidate as any).last_tenure as string | null | undefined
    const parts = []
    if (candidate.age) parts.push(`${candidate.age} лет`)
    if (tenure) parts.push(tenure)
    if (candidate.last_company) parts.push(candidate.last_company)

    return parts.join(' · ')
  }

  const handleScoreBadgeClick = () => {
    handleTabChange('evaluation')
  }

  const formatSalary = () =>
    candidate?.salary_expectation
      ? fmtSalary(candidate.salary_expectation, candidate.currency)
      : null

  const fmtDate = (iso: string | null | undefined) =>
    iso ? new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''

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

      {/* Шапка кандидата */}
      <div className="cfp-header">
        <div className="cfp-h-top">
          <div className="cfp-h-id">
            <Avatar name={candidate.full_name} size="md" src={null} />
            <div className="cfp-name-wrap">
              <div className="cfp-name-row">
                <h1 className="cfp-name">{candidate.full_name}</h1>
                {candidate.display_number && (
                  <span className="cfp-num">№{candidate.display_number}</span>
                )}
                {candidate.is_duplicate && (
                  <span className="cfp-dup">Дубль</span>
                )}
              </div>
              {formatContactInfo() && (
                <div className="cfp-meta-line">{formatContactInfo()}</div>
              )}
            </div>
          </div>
          <div
            onClick={handleScoreBadgeClick}
            style={{ cursor: 'pointer' }}
            title="Перейти к оценке AI"
          >
            <ScoreLabel value={candidate.ai_score ?? null} size="xl" />
          </div>
        </div>

        {/* Контакты */}
        <div className="cfp-contact-row">
          {candidate.phone && (
            <div className="cfp-contact-item">
              <span className="cfp-contact-k">Телефон:</span>
              <a href={`tel:${candidate.phone}`} className="cfp-phone">
                {candidate.phone}
              </a>
              {candidate.messengers && candidate.messengers.length > 0 && (
                <div className="cfp-mess-row">
                  {candidate.messengers.map((m: any, i: number) => {
                    const ch = messengerChannel(m);
                    return (
                      <MessIconRound
                        key={`${ch}-${i}`}
                        channel={ch}
                        size="sm"
                      />
                    );
                  })}
                </div>
              )}
            </div>
          )}
          {candidate.email && (
            <div className="cfp-contact-item">
              <span className="cfp-contact-k">E-mail:</span>
              <a href={`mailto:${candidate.email}`} className="cfp-email">
                {candidate.email}
              </a>
            </div>
          )}
          {candidate.city && (
            <div className="cfp-contact-item">
              <span className="cfp-contact-k">Город:</span>
              <span>{candidate.city}</span>
            </div>
          )}
          {formatSalary() && (
            <div className="cfp-contact-item">
              <span className="cfp-contact-k">Ожидания:</span>
              <span>{formatSalary()}</span>
            </div>
          )}
        </div>

        {/* Теги */}
        <div className="cfp-tags-row">
          <span className="cfp-tags-k">Теги:</span>
          <CandidateTagPicker candidateId={candidate.id} assigned={candidate.tags ?? []} />
        </div>
      </div>

      {/* История участия в вакансиях */}
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

      {/* Табы */}
      <div className="cfp-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`cfp-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Контент табов с proper scoping для CandidateDetail CSS */}
      <div className="cfp-tab-content">
        <div className="cnd-funnel-wrap">
          <div className="cand-detail">
            {renderTabContent()}
          </div>
        </div>
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