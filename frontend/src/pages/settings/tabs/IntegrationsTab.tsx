import { useState, useEffect } from 'react';
import { useIntegrations } from '@/api/hooks/useIntegrations';
import { useUpdateIntegration } from '@/api/mutations/settings';
import { Icon } from '@/components/ui/Icon';

type Props = {
  onDirtyChange: (dirty: boolean) => void;
  onSaveHandler: (handler: (() => Promise<void>) | null) => void;
  onDiscardHandler: (handler: (() => void) | null) => void;
};

const INTEGRATION_CONFIGS = {
  hh: {
    name: 'hh.ru',
    logo: '🔍',
    description: 'Загрузка резюме и откликов с hh.ru',
    fields: [
      { key: 'api_key', label: 'API ключ', type: 'password', required: true },
      { key: 'regions', label: 'Регионы', type: 'text', placeholder: 'Москва, Санкт-Петербург' },
    ],
  },
  avito: {
    name: 'Авито Работа',
    logo: '💼',
    description: 'Интеграция с Авито Работа',
    fields: [
      { key: 'token', label: 'Токен доступа', type: 'password', required: true },
      { key: 'client_id', label: 'Client ID', type: 'text', required: true },
    ],
  },
  telegram: {
    name: 'Telegram',
    logo: '📱',
    description: 'Уведомления через Telegram бот',
    fields: [
      { key: 'bot_token', label: 'Токен бота', type: 'password' },
    ],
  },
  whatsapp: {
    name: 'WhatsApp Business',
    logo: '📞',
    description: 'Отправка сообщений через WhatsApp',
    fields: [
      { key: 'phone_number_id', label: 'Phone Number ID', type: 'text' },
      { key: 'access_token', label: 'Access Token', type: 'password' },
    ],
  },
  google_calendar: {
    name: 'Google Calendar',
    logo: '📅',
    description: 'Синхронизация интервью с календарем',
    fields: [
      { key: 'client_id', label: 'Client ID', type: 'text' },
      { key: 'client_secret', label: 'Client Secret', type: 'password' },
    ],
  },
};

export function IntegrationsTab({ onDirtyChange, onSaveHandler, onDiscardHandler }: Props) {
  const { data: integrations, isLoading } = useIntegrations();
  const updateIntegration = useUpdateIntegration();

  const [expandedIntegration, setExpandedIntegration] = useState<string | null>(null);
  const [configForms, setConfigForms] = useState<Record<string, Record<string, string>>>({});

  // IntegrationsTab doesn't have persistent dirty state
  useEffect(() => {
    onDirtyChange(false);
    onSaveHandler(null);
    onDiscardHandler(null);
  }, [onDirtyChange, onSaveHandler, onDiscardHandler]);

  // Initialize forms with integration configs
  useEffect(() => {
    if (integrations) {
      const forms: Record<string, Record<string, string>> = {};
      integrations.forEach(integration => {
        const config: Record<string, string> = {};
        if (integration.config && typeof integration.config === 'object') {
          Object.entries(integration.config).forEach(([key, value]) => {
            config[key] = String(value || '');
          });
        }
        forms[integration.provider] = config;
      });
      setConfigForms(forms);
    }
  }, [integrations]);

  // Removed unused function

  const getIntegrationByProvider = (provider: string) => {
    return integrations?.find(i => i.provider === provider);
  };

  const isIntegrationConnected = (provider: string) => {
    const integration = getIntegrationByProvider(provider);
    return integration?.status === 'connected';
  };

  const handleToggleExpand = (provider: string) => {
    setExpandedIntegration(expandedIntegration === provider ? null : provider);
  };

  const handleConfigChange = (provider: string, field: string, value: string) => {
    setConfigForms(prev => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        [field]: value,
      },
    }));
  };

  const handleSaveConfig = async (provider: string) => {
    const config = configForms[provider] || {};
    await updateIntegration.mutateAsync({
      provider,
      data: {
        config,
        status: 'connected',
      },
    });
  };

  const handleDisconnect = async (provider: string) => {
    await updateIntegration.mutateAsync({
      provider,
      data: {
        config: {},
        status: 'disconnected',
      },
    });
    setConfigForms(prev => ({
      ...prev,
      [provider]: {},
    }));
  };

  if (isLoading) {
    return <div className="settings-loading">Загрузка...</div>;
  }

  return (
    <div className="settings-content-inner">
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Интеграции</h2>
          <p className="settings-card-desc">Подключение внешних сервисов и источников кандидатов</p>
        </div>

        <div className="integrations-grid">
          {Object.entries(INTEGRATION_CONFIGS).map(([provider, config]) => {
            const isConnected = isIntegrationConnected(provider);
            const isExpanded = expandedIntegration === provider;
            const isRealIntegration = provider === 'hh' || provider === 'avito';

            return (
              <div key={provider} className={`integration-card ${isConnected ? 'connected' : ''}`}>
                <div className="integration-header" onClick={() => handleToggleExpand(provider)}>
                  <div className="integration-info">
                    <div className="integration-logo">{config.logo}</div>
                    <div className="integration-details">
                      <h3 className="integration-name">{config.name}</h3>
                      <p className="integration-description">{config.description}</p>
                    </div>
                  </div>
                  <div className="integration-status">
                    <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}>
                      {isConnected ? 'Подключено' : 'Не подключено'}
                    </span>
                    <Icon
                      name={isExpanded ? 'chevron-up' : 'chevron-down'}
                      size={16}
                      className="integration-chevron"
                    />
                  </div>
                </div>

                {isExpanded && (
                  <div className="integration-config">
                    {isRealIntegration ? (
                      <>
                        <div className="integration-fields">
                          {config.fields.map(field => (
                            <div key={field.key} className="form-field">
                              <label className="form-label">
                                {field.label}
                                {'required' in field && field.required && <span className="required">*</span>}
                              </label>
                              <input
                                type={field.type}
                                className="form-input"
                                value={configForms[provider]?.[field.key] || ''}
                                onChange={(e) => handleConfigChange(provider, field.key, e.target.value)}
                                placeholder={'placeholder' in field ? field.placeholder : ''}
                              />
                            </div>
                          ))}
                        </div>

                        <div className="integration-actions">
                          <button
                            className="btn btn-ghost btn-sm"
                            disabled
                            title="Скоро"
                          >
                            <Icon name="zap" size={14} />
                            Проверить подключение
                          </button>
                          {isConnected ? (
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleDisconnect(provider)}
                              disabled={updateIntegration.isPending}
                            >
                              Отключить
                            </button>
                          ) : (
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => handleSaveConfig(provider)}
                              disabled={updateIntegration.isPending}
                            >
                              {updateIntegration.isPending ? 'Подключение...' : 'Подключить'}
                            </button>
                          )}
                        </div>
                      </>
                    ) : (
                      <div className="integration-placeholder">
                        <Icon name="settings" size={24} />
                        <p>Интеграция находится в разработке</p>
                        {/* TODO: Implement when backend supports this provider */}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}