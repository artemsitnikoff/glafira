import { Icon } from '@/components/ui/Icon';

type Props = {
  search?: string;
  onSearchChange: (search: string) => void;
  onFiltersOpen: () => void;
  filtersCount: number;
};

export default function SearchBar({ search = '', onSearchChange, onFiltersOpen, filtersCount }: Props) {
  return (
    <div className="cand-controls">
      <div className="submenu-search" style={{ width: 280, height: 30, background: '#fff', border: '1px solid var(--border-1)' }}>
        <Icon name="search" size={14} style={{ color: 'var(--fg-3)', flex: 'none' }} />
        <input
          placeholder="Поиск по ФИО…"
          value={search}
          onChange={e => onSearchChange(e.target.value)}
        />
      </div>

      <div style={{ flex: 1 }} />

      <button
        className={`btn btn-secondary btn-sm ${filtersCount > 0 ? 'has-filters' : ''}`}
        onClick={onFiltersOpen}
      >
        <Icon name="filter" size={14} /> Фильтры
        {filtersCount > 0 && <span className="filter-badge">{filtersCount}</span>}
      </button>
    </div>
  );
}