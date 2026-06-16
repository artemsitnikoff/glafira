import { Icon } from '@/components/ui/Icon';
import { PageHead, FormRow, TextInput, Select } from '../components/FormComponents';
import { useHhStatus } from '@/api/hooks/useHhIntegration';
import { useHhAuthorize, useHhDisconnect, useHhPollResponses } from '@/api/mutations/hhIntegration';
import type { HhPollResult } from '@/api/mutations/hhIntegration';
import { useSmtpStatus } from '@/api/hooks/useSmtpIntegration';
import { useSmtpSaveConfig, useSmtpTest, useSmtpDisconnect } from '@/api/mutations/smtpIntegration';
import { useBitrix24Status } from '@/api/hooks/useBitrix24Integration';
import { useBitrix24SaveConfig, useBitrix24Test, useBitrix24Disconnect } from '@/api/mutations/bitrix24Integration';
import { useTelegramStatus } from '@/api/hooks/useTelegramIntegration';
import { useTgSendCode, useTgResendCode, useTgConnectSession, useTgConfirmCode, useTgConfirmPassword, useTgTest, useTgDisconnect } from '@/api/mutations/telegramIntegration';
import { useMangoStatus } from '@/api/hooks/useMangoIntegration';
import { useMangoSaveConfig, useMangoTest, useMangoDisconnect } from '@/api/mutations/mangoIntegration';
import { useAuthStore } from '@/store/authStore';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { ApiError } from '@/api/aliases';

function IntegrationCard({
  ico,
  iconBg,
  name,
  desc,
  status,
  statusLabel,
  children
}: {
  ico: React.ReactNode;
  iconBg: string;
  name: string;
  desc: string;
  status: 'ok' | 'bad' | 'err';
  statusLabel?: string;
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
          {statusLabel ?? statusInfo.label}
        </div>
        <span className="integ-chev"><Icon name="chevD" size={16}/></span>
      </div>
      <div className="integ-content">{children}</div>
    </section>
  );
}

interface SettingsIntegrationsProps {
  readOnly?: boolean;
}

export function SettingsIntegrations({ readOnly = false }: SettingsIntegrationsProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const { data: hhStatus, isLoading: hhStatusLoading } = useHhStatus();
  const hhAuthorizeMutation = useHhAuthorize();
  const hhDisconnectMutation = useHhDisconnect();
  const hhPollMutation = useHhPollResponses();
  const [hhPollResult, setHhPollResult] = useState<HhPollResult | null>(null);

  const handleHhPollResponses = async () => {
    setHhPollResult(null);
    try {
      const res = await hhPollMutation.mutateAsync();
      setHhPollResult(res);
      if (res.vacancies === 0) {
        setNotification({
          type: 'error',
          message: 'Нет привязанных активных вакансий для опроса. Проверьте: вакансия привязана к hh.ru И активна (не закрыта/не на паузе).',
        });
      } else {
        setNotification({
          type: 'success',
          message: `Проверено вакансий: ${res.vacancies}. Создано: ${res.imported}, обновлено: ${res.updated ?? 0}, пропущено: ${res.skipped}.`,
        });
      }
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Не удалось забрать отклики с hh.ru' });
    }
  };

  // Обработка OAuth-возврата
  useEffect(() => {
    const hhParam = searchParams.get('hh');
    const hhMsg = searchParams.get('hh_msg');  // реальная причина из callback'а
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
          message = hhMsg || 'Ошибка при подключении hh.ru';
          type = 'error';
          break;
      }

      if (message) {
        setNotification({ type, message });
        // Убираем параметры из URL
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('hh');
        newParams.delete('hh_msg');
        setSearchParams(newParams);
      }
    }
  }, [searchParams, setSearchParams]);

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

  // ---------------- SMTP (почтовый сервер) ----------------
  const { data: smtpStatus, isLoading: smtpLoading } = useSmtpStatus();
  const smtpSaveMutation = useSmtpSaveConfig();
  const smtpTestMutation = useSmtpTest();
  const smtpDisconnectMutation = useSmtpDisconnect();

  const currentUserEmail = useAuthStore(s => s.user?.email) ?? '';

  const [smtpForm, setSmtpForm] = useState({
    host: '',
    port: '587',
    encryption: 'tls',
    username: '',
    password: '',
    from_email: '',
    from_name: '',
    reply_to: '',
  });
  const [smtpEdit, setSmtpEdit] = useState(false);
  const [smtpTestTo, setSmtpTestTo] = useState(currentUserEmail);

  const enterSmtpEdit = () => {
    setSmtpForm({
      host: smtpStatus?.host || '',
      port: smtpStatus?.port ? String(smtpStatus.port) : '587',
      encryption: smtpStatus?.encryption || 'tls',
      username: smtpStatus?.username || '',
      password: '',
      from_email: smtpStatus?.from_email || '',
      from_name: smtpStatus?.from_name || '',
      reply_to: smtpStatus?.reply_to || '',
    });
    setSmtpEdit(true);
  };

  const handleSmtpSave = async () => {
    try {
      await smtpSaveMutation.mutateAsync({
        host: smtpForm.host.trim(),
        port: parseInt(smtpForm.port, 10) || 0,
        encryption: smtpForm.encryption,
        username: smtpForm.username.trim(),
        password: smtpForm.password,
        from_email: smtpForm.from_email.trim(),
        from_name: smtpForm.from_name.trim(),
        reply_to: smtpForm.reply_to.trim(),
      });
      setSmtpEdit(false);
      setSmtpForm(prev => ({ ...prev, password: '' })); // не держим пароль в стейте
      setNotification({ type: 'success', message: 'Настройки SMTP сохранены. Отправьте тестовое письмо для проверки.' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Ошибка при сохранении настроек SMTP' });
    }
  };

  const handleSmtpTest = async () => {
    try {
      const res = await smtpTestMutation.mutateAsync({ to: smtpTestTo.trim() });
      setNotification({ type: 'success', message: `Тестовое письмо отправлено на ${res.sent_to}` });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Не удалось отправить тестовое письмо' });
    }
  };

  const handleSmtpDisconnect = async () => {
    try {
      await smtpDisconnectMutation.mutateAsync();
      setNotification({ type: 'success', message: 'SMTP отключён' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Ошибка при отключении SMTP' });
    }
  };

  // ---------------- Битрикс24 (входящий вебхук) ----------------
  const { data: b24Status, isLoading: b24Loading } = useBitrix24Status();
  const b24SaveMutation = useBitrix24SaveConfig();
  const b24TestMutation = useBitrix24Test();
  const b24DisconnectMutation = useBitrix24Disconnect();

  const [b24Url, setB24Url] = useState('');
  const [b24Edit, setB24Edit] = useState(false);

  const handleB24Save = async () => {
    try {
      await b24SaveMutation.mutateAsync({ webhook_url: b24Url.trim() });
      setB24Edit(false);
      setB24Url(''); // не держим секрет в стейте
      setNotification({ type: 'success', message: 'Вебхук Битрикс24 сохранён. Нажмите «Проверить подключение».' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Ошибка при сохранении вебхука Битрикс24' });
    }
  };

  const handleB24Test = async () => {
    try {
      const res = await b24TestMutation.mutateAsync();
      setNotification({
        type: 'success',
        message: `Подключение к Битрикс24 успешно${res.user_count != null ? ` · сотрудников на портале: ${res.user_count}` : ''}`,
      });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Не удалось подключиться к Битрикс24' });
    }
  };

  const handleB24Disconnect = async () => {
    try {
      await b24DisconnectMutation.mutateAsync();
      setNotification({ type: 'success', message: 'Битрикс24 отключён' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Ошибка при отключении Битрикс24' });
    }
  };

  // ---------------- Telegram (user-аккаунт, MTProto) ----------------
  const { data: tgStatus, isLoading: tgLoading } = useTelegramStatus();
  const tgSendCodeMutation = useTgSendCode();
  const tgResendCodeMutation = useTgResendCode();
  const tgConnectSessionMutation = useTgConnectSession();
  const tgConfirmCodeMutation = useTgConfirmCode();
  const tgConfirmPasswordMutation = useTgConfirmPassword();
  const tgTestMutation = useTgTest();
  const tgDisconnectMutation = useTgDisconnect();

  const [tgPhone, setTgPhone] = useState('');
  const [tgCode, setTgCode] = useState('');
  const [tgPassword, setTgPassword] = useState('');
  const [tgSession, setTgSession] = useState('');
  const [tgShowSession, setTgShowSession] = useState(false);
  // Ошибка показывается ИНЛАЙН в карточке Telegram (карточка внизу страницы —
  // верхний notification-баннер вне зоны видимости при работе с ней).
  const [tgError, setTgError] = useState<string | null>(null);

  // ---------------- Mango Office (телефония) ----------------
  const { data: mangoStatus, isLoading: mangoLoading } = useMangoStatus();
  const mangoSaveMutation = useMangoSaveConfig();
  const mangoTestMutation = useMangoTest();
  const mangoDisconnectMutation = useMangoDisconnect();

  const [mangoForm, setMangoForm] = useState({
    api_key: '',
    api_salt: '',
    vpbx_api_url: 'https://app.mango-office.ru/vpbx/',
  });
  const [mangoEdit, setMangoEdit] = useState(false);

  const enterMangoEdit = () => {
    setMangoForm({
      api_key: '',
      api_salt: '',
      vpbx_api_url: mangoStatus?.vpbx_api_url || 'https://app.mango-office.ru/vpbx/',
    });
    setMangoEdit(true);
  };

  const handleMangoSave = async () => {
    try {
      await mangoSaveMutation.mutateAsync({
        api_key: mangoForm.api_key.trim(),
        api_salt: mangoForm.api_salt.trim(),
        vpbx_api_url: mangoForm.vpbx_api_url.trim(),
      });
      setMangoEdit(false);
      setMangoForm(prev => ({ ...prev, api_key: '', api_salt: '' })); // не держим секреты в стейте
      setNotification({ type: 'success', message: 'Настройки Манго сохранены. Нажмите «Проверить подключение».' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Ошибка при сохранении настроек Манго' });
    }
  };

  const handleMangoTest = async () => {
    try {
      await mangoTestMutation.mutateAsync();
      setNotification({ type: 'success', message: `Подключение к Манго успешно проверено` });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Не удалось подключиться к Манго' });
    }
  };

  const handleMangoDisconnect = async () => {
    try {
      await mangoDisconnectMutation.mutateAsync();
      setNotification({ type: 'success', message: 'Манго отключён' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Ошибка при отключении Манго' });
    }
  };

  const handleTgSendCode = async () => {
    setTgError(null);
    try {
      await tgSendCodeMutation.mutateAsync({ phone: tgPhone.trim() });
      setTgCode('');
      setNotification({ type: 'success', message: `Код отправлен в Telegram на ${tgPhone.trim()}` });
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Не удалось отправить код');
    }
  };

  const handleTgConnectSession = async () => {
    setTgError(null);
    try {
      await tgConnectSessionMutation.mutateAsync({ session: tgSession.trim() });
      setTgSession('');
      setTgShowSession(false);
      setNotification({ type: 'success', message: 'Telegram подключён по сессии.' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Не удалось подключиться по строке сессии');
    }
  };

  const handleTgResendCode = async () => {
    setTgError(null);
    try {
      await tgResendCodeMutation.mutateAsync();
      setNotification({ type: 'success', message: 'Код отправлен повторно.' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Не удалось переотправить код');
    }
  };

  const handleTgConfirmCode = async () => {
    setTgError(null);
    try {
      const res = await tgConfirmCodeMutation.mutateAsync({ code: tgCode.trim() });
      setTgCode('');
      if (res.state === 'pending_password') {
        setNotification({ type: 'success', message: 'Код принят. Введите облачный пароль (2FA).' });
      } else {
        setNotification({ type: 'success', message: 'Telegram подключён.' });
      }
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Неверный код');
    }
  };

  const handleTgConfirmPassword = async () => {
    setTgError(null);
    try {
      await tgConfirmPasswordMutation.mutateAsync({ password: tgPassword });
      setTgPassword('');
      setNotification({ type: 'success', message: 'Telegram подключён.' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Неверный пароль 2FA');
    }
  };

  const handleTgTest = async () => {
    setTgError(null);
    try {
      await tgTestMutation.mutateAsync();
      setNotification({ type: 'success', message: 'Тестовое сообщение отправлено вам в «Избранное».' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Не удалось отправить тестовое сообщение');
    }
  };

  const handleTgDisconnect = async () => {
    setTgError(null);
    try {
      await tgDisconnectMutation.mutateAsync();
      setTgPhone('');
      setNotification({ type: 'success', message: 'Telegram отключён.' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Ошибка при отключении Telegram');
    }
  };

  return (
    <div className="set-content-inner">
      <PageHead title="Интеграции"
        subtitle="Внешние сервисы, с которыми работает Глафира"/>

      {/* Уведомление о режиме "только чтение" для не-админов уже показано в SettingsPage */}

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

      <div className={`integ-list ${readOnly ? 'integ-readonly' : ''}`}>
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
                    className="btn btn-primary btn-sm"
                    onClick={readOnly ? undefined : handleHhPollResponses}
                    disabled={hhPollMutation.isPending || readOnly}
                  >
                    {hhPollMutation.isPending ? 'Забираем…' : 'Забрать отклики'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={readOnly ? undefined : handleHhDisconnect}
                    disabled={hhDisconnectMutation.isPending || readOnly}
                  >
                    {hhDisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
                {hhPollResult && (
                  <div className="info-banner small" style={{ marginTop: 10 }}>
                    <Icon name="check" size={14} />
                    <div>
                      Импортировано новых: <strong>{hhPollResult.imported}</strong>, пропущено (уже были):{' '}
                      <strong>{hhPollResult.skipped}</strong>. Проверено вакансий: {hhPollResult.vacancies}.
                      {hhPollResult.details && hhPollResult.details.length > 0 && (
                        <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                          {hhPollResult.details.map((d, i) => (
                            <li key={i} style={{ fontSize: 12, marginBottom: 2 }}>
                              «{d.name}» (hh {d.hh_id}, {d.status}):{' '}
                              {d.error ? (
                                <span style={{ color: 'var(--ark-red-600)' }}>ошибка hh — {d.error}</span>
                              ) : (
                                <>
                                  на hh: <strong>{d.found ?? '—'}</strong>
                                  {d.by_collection && (
                                    <>
                                      {' '}(Отклик: {d.by_collection.response ?? 0}, Отказ:{' '}
                                      {Object.entries(d.by_collection)
                                        .filter(([k]) => k.startsWith('discard'))
                                        .reduce((s, [, v]) => s + (v ?? 0), 0)})
                                    </>
                                  )}
                                  , создано: <strong>{d.imported}</strong>, обновлено: <strong>{d.updated ?? 0}</strong>
                                </>
                              )}
                              {d.all_collections && Object.keys(d.all_collections).length > 0 && (
                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)', wordBreak: 'break-all', marginTop: 2 }}>
                                  коллекции hh: {Object.entries(d.all_collections).map(([k, v]) => `${k}=${v ?? '?'}`).join(', ')}
                                </div>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                      {hhPollResult.details && hhPollResult.details.length > 0 && (
                        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--fg-3)' }}>
                          Неразобранные отклики → этап «Отклик», отклонённые на hh → этап «Отказ».
                          Часть откликов hh может скрывать до оплаты просмотра на их стороне.
                        </div>
                      )}
                    </div>
                  </div>
                )}
                <div className="info-banner small" style={{ marginTop: 10 }}>
                  <Icon name="alert-triangle" size={14} />
                  <div>
                    Тянутся отклики на ваши размещённые вакансии (привязанные и активные) → в этап «Отклик».
                    Авто-забор — каждые ~5 мин (если на сервере настроен cron), либо вручную кнопкой выше.
                  </div>
                </div>
              </div>
            ) : (
              // Не подключено: ключ приложения Глафиры — в .env на сервере, вводить
              // ничего не нужно. Один OAuth-app авторизует любого работодателя.
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  Приложение Глафиры авторизует ваш аккаунт работодателя на hh.ru —
                  ничего вводить не нужно. Нажмите «Подключить» и подтвердите доступ на hh.ru.
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={readOnly ? undefined : handleHhConnect}
                    disabled={hhAuthorizeMutation.isPending || readOnly || !hhStatus?.configured}
                  >
                    {hhAuthorizeMutation.isPending ? 'Подключение...' : 'Подключить hh.ru'}
                  </button>
                </div>
                {hhStatus && !hhStatus.configured && (
                  <div className="info-banner small" style={{ marginTop: 10 }}>
                    <Icon name="alert-triangle" size={14} />
                    <div>hh.ru не настроен на сервере: задайте HH_CLIENT_ID / HH_CLIENT_SECRET / HH_REDIRECT_URI в .env (обратитесь к администратору).</div>
                  </div>
                )}
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
          status={smtpStatus?.verified ? 'ok' : (smtpStatus?.last_test_error ? 'err' : 'bad')}
          statusLabel={
            smtpStatus?.verified ? undefined
              : smtpStatus?.last_test_error ? 'Ошибка отправки'
              : smtpStatus?.configured ? 'Настроено'
              : undefined
          }>
          <div className="integ-section">
            {smtpLoading ? (
              <div style={{ padding: '16px 0', color: 'var(--fg-3)' }}>Загрузка статуса...</div>
            ) : (smtpStatus?.configured && !smtpEdit) ? (
              // Настроено — сводка + тест-отправка
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  <div>
                    <strong className="t-mono">{smtpStatus.host}:{smtpStatus.port}</strong>
                    {' · '}
                    {smtpStatus.encryption === 'tls' ? 'TLS (STARTTLS)' : smtpStatus.encryption === 'ssl' ? 'SSL' : 'без шифрования'}
                  </div>
                  <div style={{ marginTop: '2px' }}>
                    Отправитель: {smtpStatus.from_name ? `${smtpStatus.from_name} · ` : ''}
                    <span className="t-mono">{smtpStatus.from_email}</span>
                  </div>
                  {smtpStatus.verified && smtpStatus.last_test_at && (
                    <div style={{ fontSize: '12px', color: 'var(--ark-green-600)', marginTop: '4px' }}>
                      ✓ Проверено: тест отправлен {new Date(smtpStatus.last_test_at).toLocaleString('ru')}
                    </div>
                  )}
                  {!smtpStatus.verified && smtpStatus.last_test_error && (
                    <div style={{ fontSize: '12px', color: 'var(--ark-red-600)', marginTop: '4px' }}>
                      Последний тест не прошёл: {smtpStatus.last_test_error}
                    </div>
                  )}
                  {!smtpStatus.verified && !smtpStatus.last_test_error && (
                    <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginTop: '4px' }}>
                      Ещё не проверено — отправьте тестовое письмо.
                    </div>
                  )}
                </div>
                <div className="form-grid form-grid-2">
                  <FormRow label="Кому отправить тест" span={2}>
                    <TextInput
                      value={smtpTestTo}
                      onChange={(v) => setSmtpTestTo(v)}
                      placeholder="email получателя"
                      mono
                    />
                  </FormRow>
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleSmtpTest}
                    disabled={smtpTestMutation.isPending || !smtpTestTo.trim()}
                  >
                    {smtpTestMutation.isPending ? 'Отправка...' : 'Отправить тестовое письмо'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={enterSmtpEdit}
                    disabled={smtpTestMutation.isPending}
                  >
                    Изменить настройки
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleSmtpDisconnect}
                    disabled={smtpDisconnectMutation.isPending}
                  >
                    {smtpDisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
              </div>
            ) : (
              // Не настроено или редактирование — форма
              <div>
                <div className="form-grid form-grid-2">
                  <FormRow label="SMTP-сервер" required>
                    <TextInput value={smtpForm.host} onChange={(v) => setSmtpForm(p => ({ ...p, host: v }))} placeholder="smtp.yandex.ru" mono />
                  </FormRow>
                  <FormRow label="Порт" required>
                    <TextInput value={smtpForm.port} onChange={(v) => setSmtpForm(p => ({ ...p, port: v.replace(/[^0-9]/g, '') }))} placeholder="587" mono />
                  </FormRow>
                  <FormRow label="Шифрование">
                    <Select
                      value={smtpForm.encryption}
                      options={[{ value: 'tls', label: 'TLS (STARTTLS, обычно 587)' }, { value: 'ssl', label: 'SSL (обычно 465)' }, { value: 'none', label: 'Без шифрования' }]}
                      onChange={(v) => setSmtpForm(p => ({ ...p, encryption: v }))}
                    />
                  </FormRow>
                  <FormRow label="Reply-to">
                    <TextInput value={smtpForm.reply_to} onChange={(v) => setSmtpForm(p => ({ ...p, reply_to: v }))} placeholder="hr@company.ru" mono />
                  </FormRow>
                  <FormRow label="Email отправителя" required>
                    <TextInput value={smtpForm.from_email} onChange={(v) => setSmtpForm(p => ({ ...p, from_email: v }))} placeholder="hr@company.ru" mono />
                  </FormRow>
                  <FormRow label="Имя отправителя">
                    <TextInput value={smtpForm.from_name} onChange={(v) => setSmtpForm(p => ({ ...p, from_name: v }))} placeholder="HR · Моя компания" />
                  </FormRow>
                  <FormRow label="Логин SMTP">
                    <TextInput value={smtpForm.username} onChange={(v) => setSmtpForm(p => ({ ...p, username: v }))} placeholder="hr@company.ru" mono />
                  </FormRow>
                  <FormRow label="Пароль" required={!smtpStatus?.configured}>
                    <TextInput
                      type="password"
                      value={smtpForm.password}
                      onChange={(v) => setSmtpForm(p => ({ ...p, password: v }))}
                      placeholder={smtpStatus?.configured ? 'Оставьте пустым, чтобы не менять' : 'Пароль или app-пароль'}
                      mono
                    />
                  </FormRow>
                </div>
                <div className="info-banner small">
                  <Icon name="alert-triangle" size={14} />
                  <div>Для Яндекс/Gmail используйте <strong>пароль приложения</strong> (app password), а не основной пароль аккаунта. После сохранения отправьте тестовое письмо.</div>
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleSmtpSave}
                    disabled={
                      smtpSaveMutation.isPending ||
                      !smtpForm.host.trim() ||
                      !smtpForm.port ||
                      !smtpForm.from_email.trim() ||
                      (!smtpStatus?.configured && !smtpForm.password)
                    }
                  >
                    {smtpSaveMutation.isPending ? 'Сохранение...' : 'Сохранить настройки'}
                  </button>
                  {smtpEdit && (
                    <button className="btn btn-secondary btn-sm" onClick={() => setSmtpEdit(false)} disabled={smtpSaveMutation.isPending}>
                      Отмена
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </IntegrationCard>

        {/* B24 */}
        <IntegrationCard
          ico={<span className="integ-emoji">🔵</span>}
          iconBg="#EAF3FE"
          name="Битрикс·24"
          desc="Импорт сотрудников из Битрикс24 через входящий вебхук"
          status={b24Status?.verified ? 'ok' : (b24Status?.last_test_error ? 'err' : 'bad')}
          statusLabel={
            b24Status?.verified ? undefined
              : b24Status?.last_test_error ? 'Ошибка подключения'
              : b24Status?.configured ? 'Настроено'
              : undefined
          }>
          <div className="integ-section">
            {b24Loading ? (
              <div style={{ padding: '16px 0', color: 'var(--fg-3)' }}>Загрузка статуса...</div>
            ) : (b24Status?.configured && !b24Edit) ? (
              // Настроено — проверка/управление
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  <div>Портал: <span className="t-mono">{b24Status.portal}</span> · вебхук сохранён</div>
                  {b24Status.verified && b24Status.last_test_at && (
                    <div style={{ fontSize: '12px', color: 'var(--ark-green-600)', marginTop: '4px' }}>
                      ✓ Подключено{b24Status.user_count != null ? ` · сотрудников: ${b24Status.user_count}` : ''}
                      {' · '}{new Date(b24Status.last_test_at).toLocaleString('ru')}
                    </div>
                  )}
                  {!b24Status.verified && b24Status.last_test_error && (
                    <div style={{ fontSize: '12px', color: 'var(--ark-red-600)', marginTop: '4px' }}>
                      Последняя проверка не прошла: {b24Status.last_test_error}
                    </div>
                  )}
                  {!b24Status.verified && !b24Status.last_test_error && (
                    <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginTop: '4px' }}>
                      Ещё не проверено — нажмите «Проверить подключение».
                    </div>
                  )}
                </div>
                <div className="integ-actions">
                  <button className="btn btn-primary btn-sm" onClick={handleB24Test} disabled={b24TestMutation.isPending}>
                    {b24TestMutation.isPending ? 'Проверка...' : 'Проверить подключение'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => { setB24Url(''); setB24Edit(true); }} disabled={b24TestMutation.isPending}>
                    Изменить вебхук
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={handleB24Disconnect} disabled={b24DisconnectMutation.isPending}>
                    {b24DisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
                <div className="info-banner small">
                  <Icon name="sparkle" size={14} />
                  <div>Импорт сотрудников в Глафиру и отчёт «Текучка» — следующий этап (вебхук уже читает данные с портала).</div>
                </div>
              </div>
            ) : (
              // Не настроено или изменение вебхука — форма
              <div>
                <div className="form-grid form-grid-2">
                  <FormRow label="URL входящего вебхука" required span={2}>
                    <TextInput
                      value={b24Url}
                      onChange={(v) => setB24Url(v)}
                      placeholder="https://портал.bitrix24.ru/rest/1/код/"
                      mono
                    />
                  </FormRow>
                </div>
                <div className="info-banner small">
                  <Icon name="alert-triangle" size={14} />
                  <div>В Битрикс24: <strong>Приложения → Разработчикам → Другое → Входящий вебхук</strong>. Дайте права <strong>user</strong> (и <strong>department</strong>), скопируйте URL и вставьте сюда. Код вебхука — секрет, хранится зашифрованным.</div>
                </div>
                <div className="integ-actions">
                  <button className="btn btn-primary btn-sm" onClick={handleB24Save} disabled={b24SaveMutation.isPending || !b24Url.trim()}>
                    {b24SaveMutation.isPending ? 'Сохранение...' : 'Сохранить'}
                  </button>
                  {b24Edit && (
                    <button className="btn btn-secondary btn-sm" onClick={() => setB24Edit(false)} disabled={b24SaveMutation.isPending}>
                      Отмена
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </IntegrationCard>

        {/* MANGO OFFICE (телефония) */}
        <IntegrationCard
          ico={<Icon name="phone" size={18}/>}
          iconBg="#FFEBEA"
          name="Манго Телеком"
          desc="Телефония: звонки кандидатам, запись и AI-разбор"
          status={mangoStatus?.verified ? 'ok' : (mangoStatus?.last_test_error ? 'err' : 'bad')}
          statusLabel={
            mangoStatus?.verified ? undefined
              : mangoStatus?.last_test_error ? 'Ошибка подключения'
              : mangoStatus?.configured ? 'Настроено'
              : undefined
          }>
          <div className="integ-section">
            {mangoLoading ? (
              <div style={{ padding: '16px 0', color: 'var(--fg-3)' }}>Загрузка статуса...</div>
            ) : (mangoStatus?.configured && !mangoEdit) ? (
              // Настроено — проверка/управление
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  <div>API URL: <span className="t-mono">{mangoStatus.vpbx_api_url}</span></div>
                  {mangoStatus.verified && mangoStatus.last_test_at && (
                    <div style={{ fontSize: '12px', color: 'var(--ark-green-600)', marginTop: '4px' }}>
                      ✓ Подключение проверено {new Date(mangoStatus.last_test_at).toLocaleString('ru')}
                    </div>
                  )}
                  {!mangoStatus.verified && mangoStatus.last_test_error && (
                    <div style={{ fontSize: '12px', color: 'var(--ark-red-600)', marginTop: '4px' }}>
                      Последняя проверка не прошла: {mangoStatus.last_test_error}
                    </div>
                  )}
                  {!mangoStatus.verified && !mangoStatus.last_test_error && (
                    <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginTop: '4px' }}>
                      Ещё не проверено — нажмите «Проверить подключение».
                    </div>
                  )}
                </div>
                <div className="integ-actions">
                  <button className="btn btn-primary btn-sm" onClick={readOnly ? undefined : handleMangoTest} disabled={mangoTestMutation.isPending || readOnly}>
                    {mangoTestMutation.isPending ? 'Проверка...' : 'Проверить подключение'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={readOnly ? undefined : enterMangoEdit} disabled={mangoTestMutation.isPending || readOnly}>
                    Изменить настройки
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={readOnly ? undefined : handleMangoDisconnect} disabled={mangoDisconnectMutation.isPending || readOnly}>
                    {mangoDisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
              </div>
            ) : (
              // Не настроено или изменение настроек — форма
              <div>
                <div className="form-grid form-grid-2">
                  <FormRow label="API Key" required>
                    <TextInput
                      type="password"
                      value={mangoForm.api_key}
                      onChange={(v) => setMangoForm(p => ({ ...p, api_key: v }))}
                      placeholder={mangoStatus?.configured ? '••••••••' : 'Введите API Key'}
                      mono
                    />
                  </FormRow>
                  <FormRow label="API Salt" required>
                    <TextInput
                      type="password"
                      value={mangoForm.api_salt}
                      onChange={(v) => setMangoForm(p => ({ ...p, api_salt: v }))}
                      placeholder={mangoStatus?.configured ? '••••••••' : 'Введите API Salt'}
                      mono
                    />
                  </FormRow>
                  <FormRow label="VPBX API URL" required span={2}>
                    <TextInput
                      value={mangoForm.vpbx_api_url}
                      onChange={(v) => setMangoForm(p => ({ ...p, vpbx_api_url: v }))}
                      placeholder="https://app.mango-office.ru/vpbx/"
                      mono
                    />
                  </FormRow>
                </div>
                <div className="info-banner small">
                  <Icon name="alert-triangle" size={14} />
                  <div>В личном кабинете Манго получите <strong>API Key</strong> и <strong>API Salt</strong> для интеграции. После сохранения проверьте подключение.</div>
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={readOnly ? undefined : handleMangoSave}
                    disabled={
                      mangoSaveMutation.isPending ||
                      (!mangoStatus?.configured && (!mangoForm.api_key.trim() || !mangoForm.api_salt.trim())) ||
                      !mangoForm.vpbx_api_url.trim() ||
                      readOnly
                    }
                  >
                    {mangoSaveMutation.isPending ? 'Сохранение...' : 'Сохранить'}
                  </button>
                  {mangoEdit && (
                    <button className="btn btn-secondary btn-sm" onClick={() => setMangoEdit(false)} disabled={mangoSaveMutation.isPending}>
                      Отмена
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </IntegrationCard>

        {/* TELEGRAM (user-аккаунт, MTProto) */}
        <IntegrationCard
          ico={<span className="integ-emoji">✈️</span>}
          iconBg="#EAF3FE"
          name="Telegram (аккаунт)"
          desc="Сообщения кандидатам из-под вашего аккаунта Telegram"
          status={tgStatus?.connected ? 'ok' : (tgStatus?.last_test_error ? 'err' : 'bad')}
          statusLabel={
            tgStatus?.connected ? undefined
              : tgStatus?.state === 'pending_code' ? 'Введите код'
              : tgStatus?.state === 'pending_password' ? 'Пароль 2FA'
              : tgStatus?.last_test_error ? 'Ошибка отправки'
              : undefined
          }>
          <div className="integ-section">
            {tgError && (
              <div className="error-banner" style={{ marginBottom: 12 }}>
                <Icon name="alert-triangle" size={16} />
                <div>{tgError}</div>
                <button type="button" onClick={() => setTgError(null)} aria-label="Закрыть">
                  <Icon name="x" size={14} />
                </button>
              </div>
            )}
            {tgLoading ? (
              <div style={{ padding: '16px 0', color: 'var(--fg-3)' }}>Загрузка статуса...</div>
            ) : tgStatus?.connected ? (
              // Подключено
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  Подключён{tgStatus.tg_username ? ` как @${tgStatus.tg_username}` : ''}
                  {tgStatus.phone ? ` (${tgStatus.phone})` : ''}.
                  {tgStatus.last_test_ok && tgStatus.last_test_at && (
                    <span style={{ color: 'var(--ark-green-600)' }}> ✓ тест отправлен {new Date(tgStatus.last_test_at).toLocaleString('ru')}</span>
                  )}
                  {tgStatus.last_test_error && (
                    <span style={{ color: 'var(--ark-red-600)' }}> Последний тест: {tgStatus.last_test_error}</span>
                  )}
                </div>
                <div className="integ-actions">
                  <button className="btn btn-primary btn-sm" onClick={handleTgTest} disabled={tgTestMutation.isPending || readOnly}>
                    {tgTestMutation.isPending ? 'Отправка...' : 'Отправить тестовое сообщение'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={handleTgDisconnect} disabled={tgDisconnectMutation.isPending || readOnly}>
                    {tgDisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
              </div>
            ) : tgStatus?.state === 'pending_code' ? (
              // Ввод кода
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  {tgStatus.code_type === 'SentCodeTypeApp' ? (
                    <>Код отправлен <strong>в приложение Telegram</strong> — откройте чат <strong>«Telegram»</strong> (служебные сообщения, отправитель 42777). Это <strong>не SMS</strong>. </>
                  ) : tgStatus.code_type === 'SentCodeTypeSms' || tgStatus.code_type === 'SentCodeTypeFragmentSms' ? (
                    <>Код отправлен по <strong>SMS</strong> на <span className="t-mono">{tgStatus.phone}</span>. </>
                  ) : tgStatus.code_type === 'SentCodeTypeCall' ? (
                    <>Вам <strong>позвонят</strong> и продиктуют код на <span className="t-mono">{tgStatus.phone}</span>. </>
                  ) : tgStatus.code_type === 'SentCodeTypeMissedCall' ? (
                    <>Будет <strong>сброшенный звонок</strong> — код это последние цифры входящего номера. </>
                  ) : (
                    <>Код отправлен на <span className="t-mono">{tgStatus.phone}</span>. Проверьте <strong>приложение Telegram</strong> (чат «Telegram») и SMS. </>
                  )}
                  Введите его:
                </div>
                <div className="form-grid form-grid-2">
                  <FormRow label="Код из Telegram" required>
                    <TextInput value={tgCode} onChange={(v) => setTgCode(v)} placeholder="12345" mono />
                  </FormRow>
                </div>
                <div className="integ-actions">
                  <button className="btn btn-primary btn-sm" onClick={handleTgConfirmCode} disabled={tgConfirmCodeMutation.isPending || !tgCode.trim() || readOnly}>
                    {tgConfirmCodeMutation.isPending ? 'Проверка...' : 'Подтвердить'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={handleTgResendCode} disabled={tgResendCodeMutation.isPending || readOnly}>
                    {tgResendCodeMutation.isPending ? 'Отправка...' : 'Отправить заново'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={handleTgDisconnect} disabled={readOnly}>Отмена</button>
                </div>
              </div>
            ) : tgStatus?.state === 'pending_password' ? (
              // 2FA облачный пароль
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  У аккаунта включён облачный пароль (2FA). Введите его:
                </div>
                <div className="form-grid form-grid-2">
                  <FormRow label="Облачный пароль (2FA)" required>
                    <TextInput type="password" value={tgPassword} onChange={(v) => setTgPassword(v)} placeholder="••••••••" mono />
                  </FormRow>
                </div>
                <div className="integ-actions">
                  <button className="btn btn-primary btn-sm" onClick={handleTgConfirmPassword} disabled={tgConfirmPasswordMutation.isPending || !tgPassword || readOnly}>
                    {tgConfirmPasswordMutation.isPending ? 'Проверка...' : 'Подтвердить'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={handleTgDisconnect} disabled={readOnly}>Отмена</button>
                </div>
              </div>
            ) : (
              // Не подключено — ввод номера
              <div>
                <div className="form-grid form-grid-2">
                  <FormRow label="Номер телефона" required>
                    <TextInput value={tgPhone} onChange={(v) => setTgPhone(v)} placeholder="+79991234567" mono />
                  </FormRow>
                </div>
                <div className="info-banner small">
                  <Icon name="alert-triangle" size={14} />
                  <div>Вход в <strong>ваш аккаунт Telegram</strong> для отправки сообщений из-под него. Код обычно приходит <strong>в приложение Telegram</strong> (чат «Telegram»), а не по SMS. ⚠️ Автоматизация аккаунта против правил Telegram — есть риск ограничений/бана.</div>
                </div>
                <div className="integ-actions">
                  <button className="btn btn-primary btn-sm" onClick={handleTgSendCode} disabled={tgSendCodeMutation.isPending || !tgPhone.trim() || readOnly}>
                    {tgSendCodeMutation.isPending ? 'Отправка...' : 'Получить код'}
                  </button>
                </div>

                {!tgShowSession ? (
                  <button
                    type="button"
                    onClick={() => setTgShowSession(true)}
                    disabled={readOnly}
                    style={{ marginTop: 12, background: 'none', border: 'none', color: 'var(--accent)', cursor: readOnly ? 'default' : 'pointer', fontSize: 12, padding: 0 }}
                  >
                    Код не приходит? Подключить готовой строкой сессии →
                  </button>
                ) : (
                  <div style={{ marginTop: 12 }}>
                    <div className="info-banner small">
                      <Icon name="alert-triangle" size={14} />
                      <div>Строка сессии (StringSession) = <strong>полный доступ к аккаунту</strong>, вставляйте только свою. На сервере <strong>api_id/api_hash</strong> должны совпадать с теми, которыми сгенерирована сессия (иначе не подойдёт).</div>
                    </div>
                    <div className="form-grid form-grid-2">
                      <FormRow label="Строка сессии (StringSession)" required span={2}>
                        <TextInput type="password" value={tgSession} onChange={(v) => setTgSession(v)} placeholder="1ApWapz…" mono />
                      </FormRow>
                    </div>
                    <div className="integ-actions">
                      <button className="btn btn-primary btn-sm" onClick={handleTgConnectSession} disabled={tgConnectSessionMutation.isPending || !tgSession.trim() || readOnly}>
                        {tgConnectSessionMutation.isPending ? 'Подключение...' : 'Подключить по сессии'}
                      </button>
                      <button className="btn btn-secondary btn-sm" onClick={() => { setTgShowSession(false); setTgSession(''); }} disabled={readOnly}>
                        Отмена
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </IntegrationCard>
      </div>

      <div className="info-banner muted">
        <Icon name="sparkle" size={14}/>
        <div>В будущих релизах сюда добавится карточка <b>Авито Работа</b>.</div>
      </div>
    </div>
  );
}