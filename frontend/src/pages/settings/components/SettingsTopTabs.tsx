import { Icon } from '@/components/ui/Icon';

type SettingsTab = 'profile' | 'team' | 'integrations' | 'glafira' | 'templates' | 'funnel' | 'billing' | 'other';

const TABS = [
  { id: 'profile', label: 'Профиль', icon: 'user' },
  { id: 'team', label: 'Команда', icon: 'users' },
  { id: 'integrations', label: 'Интеграции', icon: 'link' },
  { id: 'glafira', label: 'Глафира', icon: 'bot' },
  { id: 'templates', label: 'Шаблоны', icon: 'mail' },
  { id: 'funnel', label: 'Воронка', icon: 'funnel' },
  { id: 'billing', label: 'Биллинг', icon: 'x' },
  { id: 'other', label: 'Прочее', icon: 'settings' },
] as const;

type Props = {
  active: SettingsTab;
  onChange: (tab: SettingsTab) => void;
};

export function SettingsTopTabs({ active, onChange }: Props) {
  return (
    <div className="settings-tabs">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          className={`settings-tab ${active === tab.id ? 'active' : ''}`}
          onClick={() => onChange(tab.id as SettingsTab)}
        >
          <Icon name={tab.icon} size={16} />
          {tab.label}
        </button>
      ))}
    </div>
  );
}