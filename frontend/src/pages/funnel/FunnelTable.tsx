import { useApplications, type ApplicationFilters } from '@/api/hooks/useApplications';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Avatar } from '@/components/ui/Avatar';
import { ScoreBadge } from '@/components/ui/ScoreBadge';
import { StageChip } from '@/components/ui/StageChip';
import { MessIconRound } from '@/components/ui/MessIconRound';
import { Badge } from '@/components/ui/Badge';

type Props = {
  vacancyId: string;
  filters: ApplicationFilters;
  onFiltersChange: (filters: ApplicationFilters) => void;
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
  activeCandidateId?: string;
  detailMode: boolean;
  onCandidateSelect: (candidateId: string) => void;
};

export default function FunnelTable({
  vacancyId,
  filters,
  onFiltersChange,
  selectedIds,
  onSelectionChange,
  activeCandidateId,
  detailMode,
  onCandidateSelect,
}: Props) {
  const { data, isLoading } = useApplications(vacancyId, filters);

  const handleSort = (field: string) => {
    const newOrder = filters.sort === field && filters.order === 'desc' ? 'asc' : 'desc';
    onFiltersChange({
      ...filters,
      sort: field,
      order: newOrder,
    });
  };

  const handleRowSelect = (id: string) => {
    const newIds = new Set(selectedIds);
    if (newIds.has(id)) {
      newIds.delete(id);
    } else {
      newIds.add(id);
    }
    onSelectionChange(newIds);
  };

  const handleSelectAll = () => {
    if (selectedIds.size === data?.items?.length) {
      onSelectionChange(new Set());
    } else {
      onSelectionChange(new Set(data?.items?.map(item => item.id) || []));
    }
  };

  if (isLoading) {
    return (
      <div className="cand-table">
        <div className="cand-scroll">
          <Skeleton height={40} />
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} height={64} style={{ marginTop: 8 }} />
          ))}
        </div>
      </div>
    );
  }

  if (!data?.items?.length) {
    return (
      <EmptyState
        icon="users"
        title={`На этапе «${filters.stage || 'выбранном'}» пока никого`}
        description="Кандидаты появятся, как только Глафира продвинет их по воронке."
      />
    );
  }

  return (
    <div className="cand-table">
      <div className="cand-scroll">
        <div className="cand-thead">
          <div className="ct-profile">
            <input
              type="checkbox"
              checked={selectedIds.size === data.items.length && data.items.length > 0}
              onChange={handleSelectAll}
            />
            <div className="ct-prof-label">Профиль</div>
            <div className="ct-prof-sorts">
              <SortableHeader
                label="ФИО"
                field="full_name"
                currentSort={filters.sort}
                currentOrder={filters.order}
                onSort={handleSort}
              />
              <SortableHeader
                label="AI"
                field="ai_score"
                currentSort={filters.sort}
                currentOrder={filters.order}
                onSort={handleSort}
              />
            </div>
          </div>

          {!detailMode && (
            <div className="ct-rest">
              <SortableHeader
                label="Телефон"
                field="phone"
                currentSort={filters.sort}
                currentOrder={filters.order}
                onSort={handleSort}
                width={200}
              />
              <SortableHeader
                label="ЗП"
                field="salary_expectation"
                currentSort={filters.sort}
                currentOrder={filters.order}
                onSort={handleSort}
                width={120}
              />
              <SortableHeader
                label="Город"
                field="city"
                currentSort={filters.sort}
                currentOrder={filters.order}
                onSort={handleSort}
                width={140}
              />
              <SortableHeader
                label="Дата отбора"
                field="selected_at"
                currentSort={filters.sort}
                currentOrder={filters.order}
                onSort={handleSort}
                width={120}
              />
              <SortableHeader
                label="Этап"
                field="stage"
                currentSort={filters.sort}
                currentOrder={filters.order}
                onSort={handleSort}
                width={200}
              />
            </div>
          )}
        </div>

        <div className="cand-tbody">
          {data.items.map(candidate => (
            <FunnelRow
              key={candidate.id}
              candidate={candidate}
              isSelected={selectedIds.has(candidate.id)}
              isActive={candidate.candidate_id === activeCandidateId}
              detailMode={detailMode}
              onSelect={() => handleRowSelect(candidate.id)}
              onOpen={() => onCandidateSelect(candidate.candidate_id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function SortableHeader({
  label,
  field,
  currentSort,
  currentOrder,
  onSort,
  width,
}: {
  label: string;
  field: string;
  currentSort?: string;
  currentOrder?: string;
  onSort: (field: string) => void;
  width?: number;
}) {
  const isActive = currentSort === field;

  return (
    <div
      className={`ct-col ct-sort-head ${isActive ? 'on' : ''}`}
      style={width ? { width } : {}}
      onClick={() => onSort(field)}
    >
      <span>{label}</span>
      <span className={`ct-sort ${isActive ? 'on' : ''}`}>
        <span className={`ct-sort-arr ${isActive && currentOrder === 'asc' ? 'active' : ''}`}>
          ▲
        </span>
        <span className={`ct-sort-arr ${isActive && currentOrder === 'desc' ? 'active' : ''}`}>
          ▼
        </span>
      </span>
    </div>
  );
}

function FunnelRow({
  candidate,
  isSelected,
  isActive,
  detailMode,
  onSelect,
  onOpen,
}: {
  candidate: any;
  isSelected: boolean;
  isActive: boolean;
  detailMode: boolean;
  onSelect: () => void;
  onOpen: () => void;
}) {
  const formatSalary = (amount: number) => {
    return amount.toLocaleString('ru-RU').replace(/,/g, ' ');
  };

  return (
    <div
      className={`cand-row ${isSelected ? 'selected' : ''} ${isActive ? 'open' : ''}`}
      style={{ '--stage-color': candidate.stage_color } as React.CSSProperties}
      onClick={onOpen}
    >
      <div className="ct-profile">
        <input
          type="checkbox"
          className="row-check"
          checked={isSelected}
          onChange={onSelect}
          onClick={e => e.stopPropagation()}
        />
        <Avatar name={candidate.full_name} size="sm" src={candidate.avatar_url} />
        <div className="prof-text">
          <div className="prof-name">
            {candidate.display_number && (
              <span className="prof-num">#{candidate.display_number}</span>
            )}
            <span>{candidate.full_name}</span>
            {candidate.has_pdn && (
              <Badge variant="success" size="sm">
                ✓ ПдН
              </Badge>
            )}
            {candidate.stage !== 'response' && (
              <span
                className="stage-pip"
                style={{ background: candidate.stage_color }}
              />
            )}
          </div>
          <div className="prof-meta-2l">
            <div className="prof-meta-line">
              {candidate.age ? `${candidate.age} лет` : 'Возраст не указан'}
            </div>
            <div className="prof-meta-line">{candidate.last_position || 'Опыт не указан'}</div>
          </div>
        </div>
        <ScoreBadge value={candidate.ai_score} size="lg" />
      </div>

      {!detailMode && (
        <div className="ct-rest">
          <div className="ct-col" style={{ width: 200 }}>
            <div className="phone-cell">
              <span className="t-mono">{candidate.phone || 'Не указан'}</span>
              <div className="mess-row">
                {candidate.messengers?.map((messenger: string) => (
                  <MessIconRound key={messenger} channel={messenger as any /* messenger from API as valid channel */} size="sm" />
                ))}
              </div>
            </div>
          </div>

          <div className="ct-col t-mono" style={{ width: 120 }}>
            {candidate.salary_expectation
              ? `${formatSalary(candidate.salary_expectation)} ₽`
              : '—'}
          </div>

          <div className="ct-col" style={{ width: 140 }}>
            {candidate.city || 'Не указан'}
          </div>

          <div className="ct-col t-mono" style={{ width: 120, color: 'var(--fg-2)' }}>
            {candidate.selected_at
              ? new Date(candidate.selected_at).toLocaleDateString('ru-RU')
              : '—'}
          </div>

          <div className="ct-col" style={{ width: 200 }}>
            <StageChip stage={candidate.stage} size="sm" />
          </div>
        </div>
      )}
    </div>
  );
}