import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { SettingsTopTabs } from './components/SettingsTopTabs';
import { DirtyBanner } from './components/DirtyBanner';
import { ProfileTab } from './tabs/ProfileTab';
import { TeamTab } from './tabs/TeamTab';
import { IntegrationsTab } from './tabs/IntegrationsTab';
import { GlafiraTab } from './tabs/GlafiraTab';
import { TemplatesTab } from './tabs/TemplatesTab';
import { FunnelTab } from './tabs/FunnelTab';
import { BillingTab } from './tabs/BillingTab';
import { OtherTab } from './tabs/OtherTab';
import './Settings.css';

type SettingsTab = 'profile' | 'team' | 'integrations' | 'glafira' | 'templates' | 'funnel' | 'billing' | 'other';

export default function SettingsPage() {
  const location = useLocation();
  const navigate = useNavigate();

  // Parse active tab from URL
  const searchParams = new URLSearchParams(location.search);
  const urlTab = searchParams.get('tab') as SettingsTab;
  const [activeTab, setActiveTab] = useState<SettingsTab>(urlTab || 'profile');

  // Dirty tracking for all forms
  const [isDirty, setIsDirty] = useState(false);
  const [dirtyHandler, setDirtyHandler] = useState<(() => Promise<void>) | null>(null);
  const [discardHandler, setDiscardHandler] = useState<(() => void) | null>(null);

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
    const tabProps = {
      onDirtyChange: setIsDirty,
      onSaveHandler: setDirtyHandler,
      onDiscardHandler: setDiscardHandler,
    };

    switch (activeTab) {
      case 'profile':
        return <ProfileTab {...tabProps} />;
      case 'team':
        return <TeamTab {...tabProps} />;
      case 'integrations':
        return <IntegrationsTab {...tabProps} />;
      case 'glafira':
        return <GlafiraTab {...tabProps} />;
      case 'templates':
        return <TemplatesTab {...tabProps} />;
      case 'funnel':
        return <FunnelTab {...tabProps} />;
      case 'billing':
        return <BillingTab {...tabProps} />;
      case 'other':
        return <OtherTab {...tabProps} />;
      default:
        return <ProfileTab {...tabProps} />;
    }
  };

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1 className="settings-title">Настройки</h1>
        <SettingsTopTabs active={activeTab} onChange={handleTabChange} />
      </div>

      {isDirty && (
        <DirtyBanner
          onSave={dirtyHandler ? () => dirtyHandler() : undefined}
          onDiscard={discardHandler ? () => discardHandler() : undefined}
        />
      )}

      <div className="settings-content">
        {renderActiveTab()}
      </div>
    </div>
  );
}