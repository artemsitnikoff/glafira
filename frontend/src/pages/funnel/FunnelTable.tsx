import { useApplications, type ApplicationFilters } from '@/api/hooks/useApplications';
import { Skeleton } from '@/components/ui/Skeleton';
import { Avatar } from '@/components/ui/Avatar';
import { StageChip } from '@/components/ui/StageChip';
import { MessIconRound } from '@/components/ui/MessIconRound';
import { messengerChannel } from '@/lib/messengers';
import { Icon } from '@/components/ui/Icon';

// Score-бейдж 1:1 по эталону: светлый пастельный фон + тёмный текст, фикс-бокс по score-{size}.
// Использует scoped-классы .score-badge/.score-green/.score-lg из Funnel.css.
// Общий components/ui/ScoreBadge — другой стиль (сплошной фон + белый текст), его НЕ трогаем (юзают другие экраны).
function scoreColorClass(s: number | null | undefined): string {
  if (s == null) return '';
  if (s >= 80) return 'score-green';
  if (s >= 50) return 'score-yellow';
  return 'score-red';
}

function ScoreBadge({ value, size = 'lg' }: { value: number | null | undefined; size?: 'sm' | 'md' | 'lg' }) {
  return (
    <span className={`score-badge ${scoreColorClass(value)} score-${size}`} title="Почему такая оценка">
      {value == null ? '—' : value}
    </span>
  );
}

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

  // Строки (ФИО/Город) и этап начинают с возрастания (А-Я / порядок воронки);
  // числовые (AI/Телефон/ЗП) и дата — с убывания. Повторный клик — переключает направление.
  const ASC_FIRST = new Set(['full_name', 'city', 'stage']);
  const handleSort = (field: string) => {
    const firstOrder = ASC_FIRST.has(field) ? 'asc' : 'desc';
    const newOrder = filters.sort === field
      ? (filters.order === 'asc' ? 'desc' : 'asc')
      : firstOrder;
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
      <div className="cand-table">
        <div className="cand-scroll">
          <div className="cand-thead">
            <div className="ct-profile">
              <div className="ct-prof-label">Профиль</div>
              <div className="ct-prof-sorts">
                <div className="ct-prof-head ct-prof-name">
                  <span>ФИО</span>
                </div>
                <div className="ct-prof-head ct-prof-ai">
                  <span>AI</span>
                </div>
              </div>
            </div>
            {!detailMode && (
              <div className="ct-rest">
                <div className="ct-col" style={{ width: 200 }}>Телефон</div>
                <div className="ct-col" style={{ width: 120 }}>ЗП</div>
                <div className="ct-col" style={{ width: 140 }}>Город</div>
                <div className="ct-col" style={{ width: 120 }}>Дата отбора</div>
                <div className="ct-col" style={{ width: 200 }}>Этап</div>
              </div>
            )}
          </div>
          <div className="cand-tbody">
            <div className="empty-pane" style={{ height: 280 }}>
              <div className="empty-illust">
                <Icon name="users" size={36} />
              </div>
              <h3>На этапе «{filters.stage || 'выбранном'}» пока никого</h3>
              <p>Кандидаты появятся, как только Глафира продвинет их по воронке.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="cand-table">
      <div className="cand-scroll">
        <div className="cand-thead">
          <div className="ct-profile">
            <div className="ct-prof-label">Профиль</div>
            <div className="ct-prof-sorts">
              <div
                className={`ct-prof-head ct-prof-name ${filters.sort === 'full_name' ? 'on' : ''}`}
                onClick={() => handleSort('full_name')}
              >
                <span>ФИО</span>
                <span className={`ct-sort ${filters.sort === 'full_name' ? 'on' : ''}`}>
                  <span className={`ct-sort-arr ${filters.sort === 'full_name' && filters.order === 'asc' ? 'active' : ''}`}>▲</span>
                  <span className={`ct-sort-arr ${filters.sort === 'full_name' && filters.order === 'desc' ? 'active' : ''}`}>▼</span>
                </span>
              </div>
              <div
                className={`ct-prof-head ct-prof-ai ${filters.sort === 'ai_score' ? 'on' : ''}`}
                onClick={() => handleSort('ai_score')}
              >
                <span>AI</span>
                <span className={`ct-sort ${filters.sort === 'ai_score' ? 'on' : ''}`}>
                  <span className={`ct-sort-arr ${filters.sort === 'ai_score' && filters.order === 'asc' ? 'active' : ''}`}>▲</span>
                  <span className={`ct-sort-arr ${filters.sort === 'ai_score' && filters.order === 'desc' ? 'active' : ''}`}>▼</span>
                </span>
              </div>
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

          {detailMode && data.items.length > 0 && (
            <div className="ct-rest cd-thead-spacer" />
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
        <Avatar name={candidate.full_name} size="md" src={candidate.avatar_url} />
        <div className="prof-text">
          <div className="prof-name">
            {candidate.display_number && (
              <span className="prof-num">#{candidate.display_number}</span>
            )}
            <span>{candidate.full_name}</span>
            {candidate.has_pdn && (
              <span className="pdn-badge pdn-sm" title="Согласие на обработку персональных данных подписано">
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                  <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                ПдН
              </span>
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
                {candidate.messengers?.map((m: any, i: number) => {
                  const ch = messengerChannel(m); // messengers: строки (seed) ИЛИ {type,url} (форма)
                  return <MessIconRound key={`${ch}-${i}`} channel={ch} size="sm" />;
                })}
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