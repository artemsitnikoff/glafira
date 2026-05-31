import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { SettingsTopTabs } from './components/SettingsTopTabs';
import { SettingsProfile } from './tabs/SettingsProfile';
import { SettingsGeneral } from './tabs/SettingsGeneral';
import { SettingsFunnel } from './tabs/SettingsFunnel';
import { SettingsAccess } from './tabs/SettingsAccess';
import { SettingsTags } from './tabs/SettingsTags';
import { SettingsIntegrations } from './tabs/SettingsIntegrations';
import './Settings.css';

type SettingsTab = 'profile' | 'general' | 'funnel' | 'access' | 'tags' | 'integrations';

const SET_SECTIONS = [
  { id: 'profile', label: 'Профиль', adminOnly: false },
  { id: 'general', label: 'Общие', adminOnly: true },
  { id: 'funnel', label: 'Воронка по умолчанию', adminOnly: true },
  { id: 'access', label: 'Права доступа', adminOnly: true },
  { id: 'tags', label: 'Теги', adminOnly: false },
  { id: 'integrations', label: 'Интеграции', adminOnly: true },
] as const;

export default function SettingsPage() {
  const location = useLocation();
  const navigate = useNavigate();

  // Parse active tab from URL
  const searchParams = new URLSearchParams(location.search);
  const urlTab = searchParams.get('tab') as SettingsTab;
  const [activeTab, setActiveTab] = useState<SettingsTab>(urlTab || 'profile');

  // Admin check - TODO: get from auth context
  const isAdmin = true;

  // Update URL when tab changes
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    if (activeTab !== 'profile') {
      searchParams.set('tab', activeTab);
    } else {
      searchParams.delete('tab');
    }
    const newSearch = searchParams.toString();
    const newPath = newSearch ? `${location.pathname}?${newSearch}` : location.pathname;
    if (newPath !== `${location.pathname}${location.search}`) {
      navigate(newPath, { replace: true });
    }
  }, [activeTab, location.pathname, location.search, navigate]);

  const handleTabChange = (tab: SettingsTab) => {
    setActiveTab(tab);
  };

  const renderActiveTab = () => {
    switch (activeTab) {
      case 'profile':
        return <SettingsProfile />;
      case 'general':
        return <SettingsGeneral />;
      case 'funnel':
        return <SettingsFunnel />;
      case 'access':
        return <SettingsAccess />;
      case 'tags':
        return <SettingsTags />;
      case 'integrations':
        return <SettingsIntegrations />;
      default:
        return <SettingsProfile />;
    }
  };

  return (
    <div className="settings-shell">
      <div className="set-content">
        <SettingsTopTabs active={activeTab} onChange={handleTabChange} isAdmin={isAdmin} sections={SET_SECTIONS} />
        {renderActiveTab()}
      </div>
    </div>
  );
}