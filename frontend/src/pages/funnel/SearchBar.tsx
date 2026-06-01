import { Icon } from '@/components/ui/Icon';

type Props = {
  search?: string;
  onSearchChange: (search: string) => void;
  onFiltersOpen?: () => void;
  filtersCount?: number;
};

export default function SearchBar({ search = '', onSearchChange }: Props) {
  return (
    <div className="submenu-search" style={{ width: 280, height: 30 }}>
      <Icon name="search" size={14} style={{ color: 'var(--fg-3)', flex: 'none' }} />
      <input
        placeholder="Поиск по ФИО…"
        value={search}
        onChange={e => onSearchChange(e.target.value)}
      />
    </div>
  );
}