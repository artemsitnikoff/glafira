import { Icon } from '@/components/ui/Icon';
import { PageHead, FormRow, TextInput, Select, Switch } from '../components/FormComponents';
import { useHhStatus } from '@/api/hooks/useHhIntegration';
import { useHhSaveConfig, useHhAuthorize, useHhDisconnect } from '@/api/mutations/hhIntegration';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { ApiError } from '@/api/aliases';

function IntegrationCard({
  ico,
  iconBg,
  name,
  desc,
  status,
  children
}: {
  ico: React.ReactNode;
  iconBg: string;
  name: string;
  desc: string;
  status: 'ok' | 'bad' | 'err';
  children: React.ReactNode;
}) {
  const statusInfo = {
    ok: { label: 'Подключено', cls: 'ok' },
    bad: { label: 'Не настроено', cls: 'bad' },
    err: { label: 'Ошибка авторизации', cls: 'err' },
  }[status];

  return (
    <section className="integ-card">
      <div className="integ-head">
        <div className="integ-ico" style={{ background: iconBg }}>{ico}</div>
        <div className="integ-body">
          <div className="integ-name">{name}</div>
          <div className="integ-desc">{desc}</div>
        </div>
        <div className={`conn-pill ${statusInfo.cls}`}>
          {status === 'ok' && <Icon name="check" size={12}/>}
          {status === 'err' && <Icon name="x" size={12}/>}
          {statusInfo.label}
        </div>
        <span className="integ-chev"><Icon name="chevD" size={16}/></span>
      </div>
      <div className="integ-content">{children}</div>
    </section>
  );
}

export function SettingsIntegrations() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const { data: hhStatus, isLoading: hhStatusLoading } = useHhStatus();
  const hhSaveConfigMutation = useHhSaveConfig();
  const hhAuthorizeMutation = useHhAuthorize();
  const hhDisconnectMutation = useHhDisconnect();

  // Состояние формы hh.ru
  const [hhForm, setHhForm] = useState({
    client_id: '',
    client_secret: '',
    redirect_uri: `${window.location.origin}/api/v1/integrations/hh/callback`
  });
  // Режим повторного ввода настроек (когда уже configured, но хотим сменить креды)
  const [editConfig, setEditConfig] = useState(false);

  // Обработка OAuth-возврата
  useEffect(() => {
    const hhParam = searchParams.get('hh');
    if (hhParam) {
      let message = '';
      let type: 'success' | 'error' = 'success';

      switch (hhParam) {
        case 'connected':
          message = 'hh.ru успешно подключён';
          type = 'success';
          break;
        case 'denied':
          message = 'Подключение hh.ru отклонено';
          type = 'error';
          break;
        case 'error':
          message = 'Ошибка при подключении hh.ru';
          type = 'error';
          break;
      }

      if (message) {
        setNotification({ type, message });
        // Убираем параметр из URL
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('hh');
        setSearchParams(newParams);
      }
    }
  }, [searchParams, setSearchParams]);

  const handleHhSaveConfig = async () => {
    try {
      const response = await hhSaveConfigMutation.mutateAsync(hhForm);
      window.location.href = response.authorize_url;
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({
        type: 'error',
        message: e.error?.message || 'Ошибка при сохранении настроек hh.ru'
      });
    }
  };

  const handleHhConnect = async () => {
    try {
      const response = await hhAuthorizeMutation.mutateAsync();
      window.location.href = response.authorize_url;
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({
        type: 'error',
        message: e.error?.message || 'Ошибка при подключении к hh.ru'
      });
    }
  };

  const handleHhDisconnect = async () => {
    try {
      await hhDisconnectMutation.mutateAsync();
      setNotification({
        type: 'success',
        message: 'hh.ru успешно отключён'
      });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({
        type: 'error',
        message: e.error?.message || 'Ошибка при отключении hh.ru'
      });
    }
  };

  return (
    <div className="set-content-inner">
      <PageHead title="Интеграции"
        subtitle="Внешние сервисы, с которыми работает Глафира"/>

      {notification && (
        <div className={notification.type === 'success' ? 'info-banner' : 'error-banner'}
             style={{
               background: notification.type === 'success' ? 'var(--success-bg)' : 'var(--error-bg)',
               borderColor: notification.type === 'success' ? 'var(--success-border)' : 'var(--error-border)',
               color: notification.type === 'success' ? 'var(--success-fg)' : 'var(--error-fg)'
             }}>
          <Icon name={notification.type === 'success' ? 'check' : 'x'} size={16} />
          <div>{notification.message}</div>
        </div>
      )}

      <div className="info-banner">
        <Icon name="bell" size={16} />
        <div>
          <b>Скоро.</b> Функциональность находится в разработке.
        </div>
      </div>

      <div className="integ-list">
        {/* HH.RU */}
        <IntegrationCard
          ico={<span className="integ-emoji">🔍</span>}
          iconBg="#FFF1C8"
          name="hh.ru"
          desc="Публикация вакансий и привязка существующих вакансий с hh.ru"
          status={hhStatusLoading ? 'bad' : (hhStatus?.connected ? 'ok' : 'bad')}>
          <div className="integ-section">
            <div className="integ-section-title">Подключение и управление</div>

            {hhStatusLoading ? (
              <div style={{ padding: '16px 0', color: 'var(--fg-3)' }}>Загрузка статуса...</div>
            ) : hhStatus?.connected ? (
              // Состояние 3: Подключено
              <div>
                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '13px', color: 'var(--fg-2)' }}>
                    <strong>Подключён</strong> как работодатель ID: {hhStatus.hh_employer_id}
                  </div>
                  {hhStatus.connected_at && (
                    <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginTop: '4px' }}>
                      Подключён: {new Date(hhStatus.connected_at).toLocaleString('ru')}
                    </div>
                  )}
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleHhDisconnect}
                    disabled={hhDisconnectMutation.isPending}
                  >
                    {hhDisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
              </div>
            ) : hhStatus?.configured && !editConfig ? (
              // Состояние 2: Настроено, но не подключено — одна синяя кнопка «Подключить»
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  Настроено: Client ID <span className="t-mono">{hhStatus.client_id_masked}</span>.
                  Осталось пройти авторизацию на hh.ru.
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleHhConnect}
                    disabled={hhAuthorizeMutation.isPending}
                  >
                    {hhAuthorizeMutation.isPending ? 'Подключение...' : 'Подключить'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      if (hhStatus.redirect_uri) {
                        setHhForm(prev => ({ ...prev, redirect_uri: hhStatus.redirect_uri! }));
                      }
                      setEditConfig(true);
                    }}
                    disabled={hhAuthorizeMutation.isPending}
                  >
                    Изменить настройки
                  </button>
                </div>
              </div>
            ) : (
              // Состояние 1: Не настроено (или повторный ввод настроек) — одна синяя «Сохранить и подключить»
              <div>
                <div className="form-grid form-grid-2">
                  <FormRow label="Client ID" required>
                    <TextInput
                      value={hhForm.client_id}
                      onChange={(value) => setHhForm(prev => ({ ...prev, client_id: value }))}
                      placeholder="Введите Client ID"
                      mono
                    />
                  </FormRow>
                  <FormRow label="Client Secret" required>
                    <TextInput
                      type="password"
                      value={hhForm.client_secret}
                      onChange={(value) => setHhForm(prev => ({ ...prev, client_secret: value }))}
                      placeholder="Введите Client Secret"
                      mono
                    />
                  </FormRow>
                  <FormRow label="Redirect URI" required span={2}>
                    <TextInput
                      value={hhForm.redirect_uri}
                      onChange={(value) => setHhForm(prev => ({ ...prev, redirect_uri: value }))}
                      mono
                    />
                  </FormRow>
                </div>
                <div className="info-banner small">
                  <Icon name="alert-triangle" size={14} />
                  <div>Зарегистрируйте приложение на <strong>dev.hh.ru</strong>, укажите этот Redirect URI, и вставьте Client ID / Client Secret.</div>
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleHhSaveConfig}
                    disabled={
                      hhSaveConfigMutation.isPending ||
                      !hhForm.client_id ||
                      !hhForm.client_secret ||
                      !hhForm.redirect_uri
                    }
                  >
                    {hhSaveConfigMutation.isPending ? 'Сохранение...' : 'Сохранить и подключить'}
                  </button>
                  {editConfig && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setEditConfig(false)}
                      disabled={hhSaveConfigMutation.isPending}
                    >
                      Отмена
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </IntegrationCard>

        {/* SMTP */}
        <IntegrationCard
          ico={<Icon name="mail" size={18}/>}
          iconBg="#FFF1C8"
          name="Почтовый сервер (SMTP)"
          desc="Отправка писем кандидатам и системных уведомлений"
          status="bad">
          <div className="integ-section">
            <div className="form-grid form-grid-2">
              <FormRow label="SMTP-сервер" required>
                <TextInput value="smtp.yandex.ru" mono locked />
              </FormRow>
              <FormRow label="Порт">
                <TextInput value="587" mono locked />
              </FormRow>
              <FormRow label="Шифрование">
                <Select value="tls"
                  options={[{value:'tls',label:'TLS (рекомендуется)'},{value:'ssl',label:'SSL'},{value:'none',label:'Без шифрования'}]}
                  disabled />
              </FormRow>
              <FormRow label="Reply-to">
                <TextInput placeholder="hr@company.ru" locked />
              </FormRow>
              <FormRow label="Email отправителя" required>
                <TextInput value="hr@company.ru" mono locked />
              </FormRow>
              <FormRow label="Имя отправителя">
                <TextInput value="HR · ООО Логос" locked />
              </FormRow>
              <FormRow label="Логин SMTP">
                <TextInput value="hr@company.ru" mono locked />
              </FormRow>
              <FormRow label="Пароль">
                <TextInput value="••••••••••••" type="password" mono locked />
              </FormRow>
            </div>
            <div className="integ-actions">
              <button className="btn btn-secondary btn-sm" disabled>Отправить тестовое письмо</button>
              <button className="btn btn-primary btn-sm" disabled>Сохранить и подключить</button>
            </div>
          </div>
        </IntegrationCard>

        {/* B24 */}
        <IntegrationCard
          ico={<span className="integ-emoji">🔵</span>}
          iconBg="#EAF3FE"
          name="Битрикс·24"
          desc="Импорт пользователей и данные о текучке"
          status="ok">
          <div className="integ-section">
            <div className="form-grid form-grid-2">
              <FormRow label="URL портала Битрикс·24" required span={2}>
                <TextInput value="https://logos.bitrix24.ru" mono locked />
              </FormRow>
            </div>

            <div className="integ-section-title" style={{marginTop:8}}>Авторизация · OAuth-приложение</div>
            <div className="form-grid form-grid-2" style={{marginTop:8}}>
              <FormRow label="Client ID">
                <TextInput placeholder="local.61f8…" mono locked />
              </FormRow>
              <FormRow label="Client Secret">
                <TextInput type="password" placeholder="••••••••••" mono locked />
              </FormRow>
              <FormRow span={2}>
                <button className="btn btn-secondary btn-sm" disabled>Авторизоваться в Битрикс·24</button>
              </FormRow>
            </div>
          </div>

          <div className="integ-divider"/>

          <div className="integ-section">
            <div className="integ-section-title">Что синхронизируется</div>
            <div className="sync-list">
              <Switch value={true} disabled label="Импортировать пользователей" desc="Настройки в разделе «Общие → Импорт пользователей»"/>
              <Switch value={true} disabled label="Получать данные о текучке" desc="Статусы сотрудников и даты увольнения для отчёта «Текучка»"/>
              <Switch value={false} disabled label="Создавать дело в Б24 при найме кандидата"/>
            </div>
          </div>
        </IntegrationCard>
      </div>

      <div className="info-banner muted">
        <Icon name="sparkle" size={14}/>
        <div>В будущих релизах сюда добавятся карточки <b>Авито Работа</b> и публикация в <b>Telegram-каналы</b>.</div>
      </div>
    </div>
  );
}