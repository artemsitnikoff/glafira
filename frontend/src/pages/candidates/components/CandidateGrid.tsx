import { useEffect, useRef } from 'react'
import { CandidateCard } from './CandidateCard'
import type { CandidateGridItem } from '../../../api/aliases'

interface Props {
  candidates: CandidateGridItem[]
  isLoading: boolean
  isFetchingNextPage: boolean
  hasNextPage: boolean
  onLoadMore: () => void
}

export function CandidateGrid({
  candidates,
  isLoading,
  isFetchingNextPage,
  hasNextPage,
  onLoadMore
}: Props) {
  const sentinelRef = useRef<HTMLDivElement>(null)

  // Intersection observer for infinite scroll
  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || !hasNextPage || isFetchingNextPage) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          onLoadMore()
        }
      },
      { threshold: 0.1 }
    )

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, onLoadMore])

  const renderSkeletons = (count: number) => {
    return Array.from({ length: count }, (_, i) => (
      <div key={`skeleton-${i}`} className="candidate-card skeleton">
        <div className="card-header">
          <div className="avatar-and-name">
            <div className="avatar skeleton-element" />
            <div className="name skeleton-element" />
          </div>
          <div className="score-badge skeleton-element" />
        </div>
        <div className="card-profile">
          <div className="profile-text skeleton-element" />
        </div>
        <div className="card-divider" />
        <div className="card-vacancy">
          <div className="vacancy-info">
            <div className="vacancy-name skeleton-element" />
          </div>
          <div className="stage-chip skeleton-element" />
        </div>
      </div>
    ))
  }

  return (
    <div className="candidates-grid">
      <div className="grid-container">
        {/* Initial loading skeletons */}
        {isLoading && candidates.length === 0 && renderSkeletons(24)}

        {/* Candidate cards */}
        {candidates.map((candidate) => (
          <CandidateCard key={candidate.id} candidate={candidate} />
        ))}

        {/* Loading more skeletons */}
        {isFetchingNextPage && renderSkeletons(8)}

        {/* Intersection observer sentinel */}
        {hasNextPage && <div ref={sentinelRef} className="load-more-sentinel" />}
      </div>

      {/* Empty state */}
      {!isLoading && candidates.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">👤</div>
          <h3>В базе пока нет кандидатов</h3>
          <p>Добавьте первого кандидата, чтобы начать работу</p>
          <div className="empty-actions">
            <button className="btn btn-primary">+ Добавить кандидата</button>
            <button className="btn btn-secondary" disabled title="Скоро">
              Импорт из файла
            </button>
          </div>
        </div>
      )}

      {/* Not found state (when filters applied but no results) */}
      {!isLoading && candidates.length === 0 && (
        // This would be shown when filters are applied but yield no results
        // Implementation depends on how we track filter state
        <div className="not-found-state" style={{ display: 'none' }}>
          <div className="empty-icon">🔍</div>
          <h3>По заданным фильтрам ничего не найдено</h3>
          <p>Попробуйте изменить или сбросить фильтры</p>
          <button className="btn btn-secondary">Сбросить фильтры</button>
        </div>
      )}
    </div>
  )
}