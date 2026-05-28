import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { CandidateGridItem } from '../../../api/aliases'
import { HoverMenu } from './HoverMenu'

interface Props {
  candidate: CandidateGridItem
}

export function CandidateCard({ candidate }: Props) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [isHovered, setIsHovered] = useState(false)

  // Format display text
  const formatAge = (age: number | null | undefined) => age ? `${age} лет` : ''
  const formatProfile = () => {
    const parts = [
      formatAge(candidate.age),
      candidate.last_position,
      candidate.last_company && candidate.last_period
        ? `${candidate.last_company} · ${candidate.last_period}`
        : candidate.last_company || candidate.last_period
    ].filter(Boolean)

    return parts.join(' / ')
  }

  const getScoreBadgeClass = (score: number | null | undefined) => {
    if (score === null || score === undefined) return 'score-badge neutral'
    if (score >= 80) return 'score-badge green'
    if (score >= 50) return 'score-badge yellow'
    return 'score-badge red'
  }

  const getScoreDisplay = (score: number | null | undefined) => {
    return score !== null && score !== undefined ? score : '—'
  }

  const handleCardClick = () => {
    // Save current filters for back navigation
    sessionStorage.setItem('pool:filters', searchParams.toString())
    sessionStorage.setItem('pool:scrollY', String(window.scrollY))

    navigate(`/candidates/${candidate.id}`)
  }

  const handleScoreBadgeClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    sessionStorage.setItem('pool:filters', searchParams.toString())
    sessionStorage.setItem('pool:scrollY', String(window.scrollY))

    navigate(`/candidates/${candidate.id}?tab=evaluation`)
  }

  const handleVacancyClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (candidate.last_vacancy) {
      navigate(`/vacancies/${candidate.last_vacancy.vacancy_id}`)
    }
  }

  const handleOtherVacanciesClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    sessionStorage.setItem('pool:filters', searchParams.toString())
    sessionStorage.setItem('pool:scrollY', String(window.scrollY))

    navigate(`/candidates/${candidate.id}?history=open`)
  }

  return (
    <div
      className={`candidate-card ${isHovered ? 'hovered' : ''}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={handleCardClick}
    >
      {/* Header */}
      <div className="card-header">
        <div className="avatar-and-name">
          {candidate.avatar_url ? (
            <img src={candidate.avatar_url} alt="" className="avatar" />
          ) : (
            <div className="avatar placeholder">
              {candidate.full_name.charAt(0)}
            </div>
          )}
          <div className="name" title={candidate.full_name}>
            {candidate.full_name}
          </div>
        </div>

        <div
          className={getScoreBadgeClass(candidate.ai_score)}
          onClick={handleScoreBadgeClick}
          title={candidate.ai_score !== null ? `AI-скоринг: ${candidate.ai_score}` : 'Скоринг не рассчитан'}
        >
          {getScoreDisplay(candidate.ai_score)}
        </div>
      </div>

      {/* Profile Info */}
      <div className="card-profile">
        <div className="profile-text">
          {formatProfile()}
        </div>
      </div>

      <div className="card-divider" />

      {/* Vacancy Status */}
      <div className="card-vacancy">
        {candidate.last_vacancy ? (
          <>
            <div className="vacancy-info" onClick={handleVacancyClick}>
              <span className="vacancy-marker">▣</span>
              <span className="vacancy-name" title={candidate.last_vacancy.vacancy_name}>
                {candidate.last_vacancy.vacancy_name}
              </span>
            </div>
            <div className="vacancy-stage-row">
              <div
                className="stage-chip"
                style={{ backgroundColor: candidate.last_vacancy.stage_color }}
              >
                {candidate.last_vacancy.stage}
              </div>
              {candidate.other_vacancies_count > 0 && (
                <div
                  className="other-vacancies"
                  onClick={handleOtherVacanciesClick}
                  title={`Ещё в ${candidate.other_vacancies_count} вакансиях`}
                >
                  +{candidate.other_vacancies_count}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="vacancy-info no-vacancy">
            <span className="vacancy-marker">🔘</span>
            <span className="vacancy-name">В базе</span>
          </div>
        )}
      </div>

      {/* Badges */}
      {(candidate.is_duplicate || candidate.has_pdn) && (
        <div className="card-badges">
          {candidate.is_duplicate && (
            <div className="badge duplicate">Дубль</div>
          )}
          {candidate.has_pdn && (
            <div className="badge pdn">ПДН</div>
          )}
        </div>
      )}

      {/* Hover Menu */}
      {isHovered && (
        <HoverMenu
          candidate={candidate}
          onMenuClick={(e) => e.stopPropagation()}
        />
      )}
    </div>
  )
}