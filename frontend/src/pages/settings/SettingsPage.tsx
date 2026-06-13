import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { AccessDenied } from '@/components/ui/AccessDenied';
import { Icon } from '@/components/ui/Icon';
import { SettingsTopTabs } from './components/SettingsTopTabs';
import { SettingsProfile } from './tabs/SettingsProfile';
import { SettingsGeneral } from './tabs/SettingsGeneral';
import { SettingsFunnel } from './tabs/SettingsFunnel';
import { SettingsAccess } from './tabs/SettingsAccess';
import { SettingsTags } from './tabs/SettingsTags';
import { SettingsIntegrations } from './tabs/SettingsIntegrations';
import { SettingsAI } from './tabs/SettingsAI';
import { SettingsMessageTemplates } from './tabs/SettingsMessageTemplates';
import './Settings.css';

type SettingsTab = 'profile' | 'general' | 'funnel' | 'access' | 'tags' | 'message-templates' | 'integrations' | 'ai';

const SET_SECTIONS = [
  { id: 'profile', label: 'Профиль', adminOnly: false },
  { id: 'general', label: 'Общие', adminOnly: true },
  { id: 'funnel', label: 'Воронка по умолчанию', adminOnly: true },
  { id: 'access', label: 'Права доступа', adminOnly: true },
  { id: 'tags', label: 'Теги', adminOnly: false },
  { id: 'message-templates', label: 'Шаблоны сообщений', adminOnly: false },
  { id: 'integrations', label: 'Интеграции', adminOnly: true },
  { id: 'ai', label: 'AI', adminOnly: true },
] as const;

export default function SettingsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  // Parse active tab from URL
  const searchParams = new URLSearchParams(location.search);
  const urlTab = searchParams.get('tab') as SettingsTab;
  const [activeTab, setActiveTab] = useState<SettingsTab>(urlTab || 'profile');

  const isAdmin = user?.role === 'admin';
  const isRecruiter = user?.role === 'recruiter';

  // manager вообще не должен сюда попасть (есть RoleGuard), но для страховки
  if (user?.role === 'manager') {
    return (
      <AccessDenied
        title="Нет доступа к настройкам"
        description="Настройки системы доступны только администраторам и рекрутёрам. Обратитесь к администратору."
      />
    );
  }

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
    const readOnly = !isAdmin; // рекрутёр видит настройки в режиме "только чтение"

    switch (activeTab) {
      case 'profile':
        return <SettingsProfile readOnly={readOnly} />;
      case 'general':
        return <SettingsGeneral readOnly={readOnly} />;
      case 'funnel':
        return <SettingsFunnel readOnly={readOnly} />;
      case 'access':
        return <SettingsAccess readOnly={readOnly} />;
      case 'tags':
        return <SettingsTags readOnly={readOnly} />;
      case 'message-templates':
        return <SettingsMessageTemplates readOnly={!(isAdmin || isRecruiter)} />;
      case 'integrations':
        return <SettingsIntegrations readOnly={readOnly} />;
      case 'ai':
        return <SettingsAI readOnly={readOnly} />;
      default:
        return <SettingsProfile readOnly={readOnly} />;
    }
  };

  return (
    <div className="settings-shell">
      <div className="set-content">
        <SettingsTopTabs active={activeTab} onChange={handleTabChange} isAdmin={isAdmin} sections={SET_SECTIONS} />

        {/* Баннер для рекрутёра о режиме "только чтение" */}
        {isRecruiter && (
          <div className="set-content-inner">
            <div className="info-banner">
              <Icon name="activity" size={16} />
              <div>
                <strong>Только просмотр</strong> — изменения доступны администратору
              </div>
            </div>
          </div>
        )}

        {renderActiveTab()}
      </div>
    </div>
  );
}