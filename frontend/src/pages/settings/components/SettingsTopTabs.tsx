type SettingsTab = 'profile' | 'general' | 'funnel' | 'access' | 'tags' | 'integrations';

type Section = {
  id: SettingsTab;
  label: string;
  adminOnly: boolean;
};

type Props = {
  active: SettingsTab;
  onChange: (tab: SettingsTab) => void;
  isAdmin: boolean;
  sections: readonly Section[];
};

export function SettingsTopTabs({ active, onChange, isAdmin, sections }: Props) {
  const visibleSections = sections.filter(s => isAdmin || !s.adminOnly);

  return (
    <div className="set-toptabs">
      {visibleSections.map(s => (
        <button key={s.id}
          className={`set-toptab ${active === s.id ? 'active' : ''}`}
          onClick={() => onChange(s.id)}>
          {s.label}
        </button>
      ))}
    </div>
  );
}