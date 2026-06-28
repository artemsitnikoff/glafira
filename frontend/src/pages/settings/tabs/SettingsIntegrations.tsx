import { Icon } from '@/components/ui/Icon';
import { PageHead, FormRow, TextInput, Select } from '../components/FormComponents';
import { PhoneInput } from '@/components/ui/PhoneInput';
import { useHhStatus } from '@/api/hooks/useHhIntegration';
import { useHhAuthorize, useHhDisconnect, useHhPollResponses } from '@/api/mutations/hhIntegration';
import type { HhPollResult } from '@/api/mutations/hhIntegration';
import { useSmtpStatus } from '@/api/hooks/useSmtpIntegration';
import { useSmtpSaveConfig, useSmtpTest, useSmtpDisconnect } from '@/api/mutations/smtpIntegration';
import { useBitrix24Status } from '@/api/hooks/useBitrix24Integration';
import { useBitrix24SaveConfig, useBitrix24Test, useBitrix24Disconnect } from '@/api/mutations/bitrix24Integration';
import { useTelegramStatus, useTelegramQrStart, useTelegramQrStatus } from '@/api/hooks/useTelegramIntegration';
import { useTgSendCode, useTgResendCode, useTgConnectSession, useTgConfirmCode, useTgConfirmPassword, useTgTest, useTgDisconnect } from '@/api/mutations/telegramIntegration';
import { useMangoStatus } from '@/api/hooks/useMangoIntegration';
import { useMangoSaveConfig, useMangoTest, useMangoDisconnect } from '@/api/mutations/mangoIntegration';
import { useHabrStatus } from '@/api/hooks/useHabrIntegration';
import { useHabrAuthorize, useHabrDisconnect, useHabrPollResponses } from '@/api/mutations/habrIntegration';
import type { HabrPollResult } from '@/api/mutations/habrIntegration';
import { useAvitoStatus } from '@/api/hooks/useAvitoIntegration';
import { useAvitoSaveConfig, useAvitoPollResponses, useAvitoDisconnect } from '@/api/mutations/avitoIntegration';
import type { AvitoPollResult } from '@/api/mutations/avitoIntegration';
import { useAuthStore } from '@/store/authStore';
import { useBackfillPhotos } from '@/api/hooks/useCandidatePhotos';
import { useQueryClient } from '@tanstack/react-query';
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
  const qc = useQueryClient();

  const { data: hhStatus, isLoading: hhStatusLoading } = useHhStatus();
  const hhAuthorizeMutation = useHhAuthorize();
  const hhDisconnectMutation = useHhDisconnect();
  const hhPollMutation = useHhPollResponses();
  const [hhPollResult, setHhPollResult] = useState<HhPollResult | null>(null);

  // Бэкфилл фото кандидатов с hh (admin-only)
  const backfillPhotosMutation = useBackfillPhotos();
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoProgress, setPhotoProgress] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

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

    // Обработка возврата от Хабр Карьера OAuth
    const habrParam = searchParams.get('habr');
    const habrMsg = searchParams.get('habr_msg');
    if (habrParam) {
      let habrMessage = '';
      let habrType: 'success' | 'error' = 'success';

      switch (habrParam) {
        case 'connected':
          habrMessage = 'Хабр Карьера успешно подключён';
          habrType = 'success';
          break;
        case 'denied':
          habrMessage = 'Подключение Хабр Карьера отклонено';
          habrType = 'error';
          break;
        case 'error':
          habrMessage = habrMsg || 'Ошибка при подключении Хабр Карьера';
          habrType = 'error';
          break;
      }

      if (habrMessage) {
        setNotification({ type: habrType, message: habrMessage });
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('habr');
        newParams.delete('habr_msg');
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

  const handleBackfillPhotos = async () => {
    if (photoBusy || readOnly) return;
    setPhotoBusy(true);
    setPhotoError(null);
    setPhotoProgress('Подтягиваем фото…');
    let totalUpdated = 0;
    try {
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const res = await backfillPhotosMutation.mutateAsync();
        totalUpdated += res.updated;
        if (res.quota_exhausted) {
          setPhotoProgress(
            `Суточный лимит просмотров hh исчерпан. Подтянуто ${totalUpdated}, осталось ~${res.remaining} — продолжите завтра.`
          );
          break;
        }
        if (res.remaining <= 0) {
          setPhotoProgress(`Готово: подтянуто ${totalUpdated} фото.`);
          break;
        }
        setPhotoProgress(`Подтянуто ${totalUpdated} фото… осталось ~${res.remaining}`);
        await new Promise((r) => setTimeout(r, 300));
      }
    } catch (error) {
      const e = error as unknown as ApiError;
      setPhotoError(e.error?.message || 'Не удалось подтянуть фото с hh');
      setPhotoProgress(null);
    } finally {
      setPhotoBusy(false);
    }
  };

  // ---------------- SMTP (почтовый сервер) ----------------
  const { data: smtpStatus, isLoading: smtpLoading } = useSmtpStatus();
  const smtpSaveMutation = useSmtpSaveConfig();
  const smtpTestMutation = useSmtpTest();
  const smtpDisconnectMutation = useSmtpDisconnect();

  const currentUserEmail = useAuthStore(s => s.user?.email) ?? '';
  const currentUser = useAuthStore(s => s.user);

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

  // QR-логин: режим (null=выбор, 'qr'=QR-поток, 'phone'=телефон+код)
  const [tgLoginMode, setTgLoginMode] = useState<null | 'qr' | 'phone'>(null);
  // QR-изображение: сначала из qr/start, потом может обновляться из qr/status
  const [tgQrImage, setTgQrImage] = useState<string | null>(null);
  // Поллинг активен если есть QR-изображение и аккаунт ещё не подключён
  const tgQrPollingEnabled =
    tgLoginMode === 'qr' &&
    tgQrImage !== null &&
    !tgStatus?.connected;

  const tgQrStartMutation = useTelegramQrStart();
  const { data: tgQrStatusData } = useTelegramQrStatus(tgQrPollingEnabled);
  // Пароль 2FA для QR-потока (отдельный стейт — чтобы не мешался с phone-потоком)
  const [tgQrPassword, setTgQrPassword] = useState('');

  // Обновляем QR-изображение из поллинга и инвалидируем статус при подключении
  useEffect(() => {
    if (!tgQrStatusData) return;
    if (tgQrStatusData.qr_image) {
      setTgQrImage(tgQrStatusData.qr_image);
    }
    if (tgQrStatusData.state === 'connected') {
      qc.invalidateQueries({ queryKey: ['integrations', 'telegram', 'status'] });
      setTgLoginMode(null);
      setTgQrImage(null);
      setNotification({ type: 'success', message: 'Telegram подключён через QR.' });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tgQrStatusData?.state, tgQrStatusData?.qr_image]);

  const handleTgQrStart = async () => {
    setTgError(null);
    setTgQrImage(null);
    try {
      const res = await tgQrStartMutation.mutateAsync();
      setTgQrImage(res.qr_image);
      setTgLoginMode('qr');
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Не удалось запустить QR-авторизацию');
    }
  };

  const handleTgQrConfirmPassword = async () => {
    setTgError(null);
    try {
      await tgConfirmPasswordMutation.mutateAsync({ password: tgQrPassword });
      setTgQrPassword('');
      setTgLoginMode(null);
      setTgQrImage(null);
      setNotification({ type: 'success', message: 'Telegram подключён.' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setTgError(e.error?.message || 'Неверный пароль 2FA');
    }
  };

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

  // ---------------- Хабр Карьера (OAuth + синхронизация откликов) ----------------
  const { data: habrStatus, isLoading: habrStatusLoading } = useHabrStatus();
  const habrAuthorizeMutation = useHabrAuthorize();
  const habrDisconnectMutation = useHabrDisconnect();
  const habrPollMutation = useHabrPollResponses();
  const [habrPollResult, setHabrPollResult] = useState<HabrPollResult | null>(null);

  const handleHabrPollResponses = async () => {
    setHabrPollResult(null);
    try {
      const res = await habrPollMutation.mutateAsync();
      setHabrPollResult(res);
      if (res.vacancies === 0) {
        setNotification({
          type: 'error',
          message: 'Нет привязанных активных вакансий для опроса. Проверьте: вакансия привязана к Хабр Карьера.',
        });
      } else {
        setNotification({
          type: 'success',
          message: `Проверено вакансий: ${res.vacancies}. Создано: ${res.imported}, пропущено: ${res.skipped}.`,
        });
      }
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Не удалось забрать отклики с Хабр Карьера' });
    }
  };

  const handleHabrConnect = async () => {
    try {
      const response = await habrAuthorizeMutation.mutateAsync();
      window.location.href = response.authorize_url;
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({
        type: 'error',
        message: e.error?.message || 'Ошибка при подключении к Хабр Карьера',
      });
    }
  };

  const handleHabrDisconnect = async () => {
    try {
      await habrDisconnectMutation.mutateAsync();
      setNotification({ type: 'success', message: 'Хабр Карьера отключён' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({
        type: 'error',
        message: e.error?.message || 'Ошибка при отключении Хабр Карьера',
      });
    }
  };

  // ---------------- Авито Работа (client_credentials) ----------------
  const { data: avitoStatus, isLoading: avitoStatusLoading } = useAvitoStatus();
  const avitoSaveConfigMutation = useAvitoSaveConfig();
  const avitoPollMutation = useAvitoPollResponses();
  const avitoDisconnectMutation = useAvitoDisconnect();

  const [avitoForm, setAvitoForm] = useState({ client_id: '', client_secret: '' });
  const [avitoPollResult, setAvitoPollResult] = useState<AvitoPollResult | null>(null);

  const handleAvitoSaveConfig = async () => {
    try {
      await avitoSaveConfigMutation.mutateAsync({
        client_id: avitoForm.client_id.trim(),
        client_secret: avitoForm.client_secret,
      });
      setAvitoForm({ client_id: '', client_secret: '' });
      setNotification({ type: 'success', message: 'Авито Работа подключена. Привяжите вакансии и заберите отклики.' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Ошибка при сохранении настроек Авито' });
    }
  };

  const handleAvitoPollResponses = async () => {
    setAvitoPollResult(null);
    try {
      const res = await avitoPollMutation.mutateAsync();
      setAvitoPollResult(res);
      if (res.vacancies === 0) {
        setNotification({
          type: 'error',
          message: 'Нет привязанных вакансий для опроса. Привяжите вакансию к Авито в редакторе вакансии.',
        });
      } else {
        setNotification({
          type: 'success',
          message: `Проверено вакансий: ${res.vacancies}. Создано: ${res.imported}, обновлено: ${res.updated ?? 0}, пропущено: ${res.skipped}.`,
        });
      }
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Не удалось забрать отклики с Авито Работа' });
    }
  };

  const handleAvitoDisconnect = async () => {
    try {
      await avitoDisconnectMutation.mutateAsync();
      setNotification({ type: 'success', message: 'Авито Работа отключена' });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({ type: 'error', message: e.error?.message || 'Ошибка при отключении Авито Работа' });
    }
  };

  const handleTgSendCode = async () => {
    setTgError(null);
    try {
      await tgSendCodeMutation.mutateAsync({ phone: tgPhone });
      setTgCode('');
      setNotification({ type: 'success', message: `Код отправлен в Telegram на ${tgPhone}` });
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
                {currentUser?.role === 'admin' && (
                  <div className="integ-section" style={{ marginTop: 16 }}>
                    <div className="integ-section-title">Фото кандидатов с hh</div>
                    <p style={{ fontSize: '13px', color: 'var(--fg-2)', marginBottom: '12px' }}>
                      Подтянуть фотографии для уже имеющихся откликов с hh. Каждый кандидат расходует 1 просмотр из суточного лимита hh.
                    </p>
                    <div className="integ-actions">
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={handleBackfillPhotos}
                        disabled={photoBusy || readOnly}
                      >
                        {photoBusy ? 'Подтягиваем…' : 'Подтянуть фото с hh'}
                      </button>
                    </div>
                    {photoProgress && (
                      <div className="info-banner small" style={{ marginTop: 10 }}>
                        {photoProgress}
                      </div>
                    )}
                    {photoError && (
                      <div className="error-banner" role="alert" style={{ marginTop: 10 }}>
                        {photoError}
                      </div>
                    )}
                  </div>
                )}
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

        {/* ХАБР КАРЬЕРА */}
        <IntegrationCard
          ico={<span style={{ fontWeight: 700, fontSize: 13, color: 'var(--ark-gray-600)', letterSpacing: '-0.03em' }}>ХК</span>}
          iconBg="var(--ark-gray-100)"
          name="Хабр Карьера"
          desc="Подключение аккаунта работодателя и синхронизация откликов"
          status={habrStatusLoading ? 'bad' : (habrStatus?.connected ? 'ok' : 'bad')}>
          <div className="integ-section">
            <div className="integ-section-title">Подключение и управление</div>

            <div className="info-banner small" style={{ marginBottom: 14 }}>
              <Icon name="sparkle" size={14} />
              <div>
                <strong>Бета.</strong> Синхронизация откликов работает для привязанных вакансий. Список вакансий Хабра появится после одобрения приложения Глафиры на стороне Хабра.
              </div>
            </div>

            {habrStatusLoading ? (
              <div style={{ padding: '16px 0', color: 'var(--fg-3)' }}>Загрузка статуса...</div>
            ) : habrStatus?.connected ? (
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  <strong>Подключено</strong>
                  {habrStatus.expires_at && (
                    <span style={{ fontSize: '12px', color: 'var(--fg-3)', marginLeft: '8px' }}>
                      токен действует до {new Date(habrStatus.expires_at).toLocaleString('ru')}
                    </span>
                  )}
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={readOnly ? undefined : handleHabrPollResponses}
                    disabled={habrPollMutation.isPending || readOnly}
                  >
                    {habrPollMutation.isPending ? 'Забираем…' : 'Забрать отклики'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={readOnly ? undefined : handleHabrDisconnect}
                    disabled={habrDisconnectMutation.isPending || readOnly}
                  >
                    {habrDisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
                {habrPollResult && (
                  <div className="info-banner small" style={{ marginTop: 10 }}>
                    <Icon name="check" size={14} />
                    <div>
                      Импортировано новых: <strong>{habrPollResult.imported}</strong>, пропущено (уже были):{' '}
                      <strong>{habrPollResult.skipped}</strong>. Проверено вакансий: {habrPollResult.vacancies}.
                    </div>
                  </div>
                )}
                <div className="info-banner small" style={{ marginTop: 10 }}>
                  <Icon name="alert-triangle" size={14} />
                  <div>
                    Тянутся отклики на привязанные к Хабр Карьера вакансии → этап «Отклик».
                    Привязку вакансии настройте в редакторе вакансии (шаг «Публикация»).
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  Нажмите «Подключить» — вас перенаправят на Хабр Карьера для подтверждения доступа.
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={readOnly ? undefined : handleHabrConnect}
                    disabled={habrAuthorizeMutation.isPending || readOnly}
                  >
                    {habrAuthorizeMutation.isPending ? 'Подключение...' : 'Подключить Хабр Карьера'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </IntegrationCard>

        {/* АВИТО РАБОТА (client_credentials) */}
        <IntegrationCard
          ico={<span style={{ fontWeight: 700, fontSize: 13, color: 'var(--src-avito)', letterSpacing: '-0.02em' }}>Ав</span>}
          iconBg="var(--ark-blue-50)"
          name="Авито Работа"
          desc="Синхронизация откликов кандидатов с Авито Работа"
          status={avitoStatusLoading ? 'bad' : (avitoStatus?.connected ? 'ok' : 'bad')}>
          <div className="integ-section">
            <div className="integ-section-title">Подключение и управление</div>

            {avitoStatusLoading ? (
              <div style={{ padding: '16px 0', color: 'var(--fg-3)' }}>Загрузка статуса...</div>
            ) : avitoStatus?.connected ? (
              // Подключено
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  <strong>Подключено</strong> — ключи API сохранены.
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={readOnly ? undefined : handleAvitoPollResponses}
                    disabled={avitoPollMutation.isPending || readOnly}
                  >
                    {avitoPollMutation.isPending ? 'Забираем…' : 'Забрать отклики Авито'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={readOnly ? undefined : handleAvitoDisconnect}
                    disabled={avitoDisconnectMutation.isPending || readOnly}
                  >
                    {avitoDisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
                {avitoPollResult && (
                  <div className="info-banner small" style={{ marginTop: 10 }}>
                    <Icon name="check" size={14} />
                    <div>
                      Импортировано новых: <strong>{avitoPollResult.imported}</strong>, обновлено:{' '}
                      <strong>{avitoPollResult.updated ?? 0}</strong>, пропущено (уже были):{' '}
                      <strong>{avitoPollResult.skipped}</strong>. Проверено вакансий: {avitoPollResult.vacancies}.
                    </div>
                  </div>
                )}
                <div className="info-banner small" style={{ marginTop: 10 }}>
                  <Icon name="alert-triangle" size={14} />
                  <div>
                    Тянутся отклики на привязанные к Авито вакансии → этап «Отклик».
                    Телефон кандидата приходит бесплатно в теле отклика — отдельно открывать не нужно.
                    Привязку вакансии настройте в редакторе вакансии (шаг «Автоматизация»).
                  </div>
                </div>
              </div>
            ) : (
              // Не подключено — форма client_id + client_secret
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  Введите Client ID и Client Secret из личного кабинета разработчика Авито.
                  Подключение использует OAuth 2.0 Client Credentials — без перенаправления браузера.
                </div>
                <div className="form-grid form-grid-2">
                  <FormRow label="Client ID" required>
                    <TextInput
                      value={avitoForm.client_id}
                      onChange={(v) => setAvitoForm(p => ({ ...p, client_id: v }))}
                      placeholder="Введите Client ID"
                      mono
                    />
                  </FormRow>
                  <FormRow label="Client Secret" required>
                    <TextInput
                      type="password"
                      value={avitoForm.client_secret}
                      onChange={(v) => setAvitoForm(p => ({ ...p, client_secret: v }))}
                      placeholder="Введите Client Secret"
                      mono
                    />
                  </FormRow>
                </div>
                <div className="info-banner small">
                  <Icon name="alert-triangle" size={14} />
                  <div>
                    Получите ключи в личном кабинете Авито:{' '}
                    <strong>Настройки → API → Мои приложения</strong>. Секрет хранится в зашифрованном виде.
                  </div>
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={readOnly ? undefined : handleAvitoSaveConfig}
                    disabled={
                      avitoSaveConfigMutation.isPending ||
                      !avitoForm.client_id.trim() ||
                      !avitoForm.client_secret.trim() ||
                      readOnly
                    }
                  >
                    {avitoSaveConfigMutation.isPending ? 'Подключение...' : 'Подключить'}
                  </button>
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
              : tgLoginMode === 'qr' && tgQrStatusData?.state === 'need_password' ? 'Пароль 2FA'
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

            ) : tgLoginMode === 'qr' ? (
              // QR-поток
              tgQrStatusData?.state === 'need_password' ? (
                // QR отсканирован, нужен 2FA-пароль
                <div>
                  <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                    QR отсканирован. У аккаунта включён облачный пароль (2FA). Введите его:
                  </div>
                  <div className="form-grid form-grid-2">
                    <FormRow label="Облачный пароль (2FA)" required>
                      <TextInput type="password" value={tgQrPassword} onChange={(v) => setTgQrPassword(v)} placeholder="••••••••" mono />
                    </FormRow>
                  </div>
                  <div className="integ-actions">
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={handleTgQrConfirmPassword}
                      disabled={tgConfirmPasswordMutation.isPending || !tgQrPassword || readOnly}
                    >
                      {tgConfirmPasswordMutation.isPending ? 'Проверка...' : 'Подтвердить'}
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => { setTgLoginMode(null); setTgQrImage(null); setTgQrPassword(''); }}
                      disabled={readOnly}
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              ) : (
                // Показываем QR и ждём сканирования
                <div>
                  <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                    В Telegram на телефоне: <strong>Настройки → Устройства → Подключить устройство</strong> → отсканируйте QR.
                    QR автоматически обновляется каждые ~30 секунд.
                  </div>
                  {tgQrImage ? (
                    <div style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: '12px',
                      border: '1px solid var(--border-1)',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--bg-elevated)',
                      marginBottom: '12px',
                    }}>
                      <img
                        src={tgQrImage}
                        alt="QR для входа в Telegram"
                        width={220}
                        height={220}
                        style={{ display: 'block' }}
                      />
                    </div>
                  ) : (
                    <div style={{
                      width: 220,
                      height: 220,
                      border: '1px solid var(--border-1)',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--bg-3)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--fg-3)',
                      fontSize: '13px',
                      marginBottom: '12px',
                    }}>
                      Генерация QR…
                    </div>
                  )}
                  <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginBottom: '12px' }}>
                    Ожидание сканирования…
                  </div>
                  <div className="integ-actions">
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => { setTgLoginMode(null); setTgQrImage(null); }}
                      disabled={readOnly}
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              )

            ) : tgLoginMode === 'phone' || tgStatus?.state === 'pending_code' ? (
              // Телефон+код поток (вторичный)
              tgStatus?.state === 'pending_code' ? (
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
                // 2FA облачный пароль (phone-поток)
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
                // Ввод номера телефона
                <div>
                  <button
                    type="button"
                    onClick={() => setTgLoginMode(null)}
                    disabled={readOnly}
                    style={{ marginBottom: 12, background: 'none', border: 'none', color: 'var(--fg-3)', cursor: readOnly ? 'default' : 'pointer', fontSize: 12, padding: 0 }}
                  >
                    ← Назад к выбору способа входа
                  </button>
                  <div className="form-grid form-grid-2">
                    <FormRow label="Номер телефона" required>
                      <PhoneInput
                        value={tgPhone || null}
                        onChange={(v) => setTgPhone(v ?? '')}
                        disabled={readOnly}
                      />
                    </FormRow>
                  </div>
                  <div className="info-banner small">
                    <Icon name="alert-triangle" size={14} />
                    <div>Вход в <strong>ваш аккаунт Telegram</strong> для отправки сообщений из-под него. Код обычно приходит <strong>в приложение Telegram</strong> (чат «Telegram»), а не по SMS. ⚠️ Автоматизация аккаунта против правил Telegram — есть риск ограничений/бана.</div>
                  </div>
                  <div className="integ-actions">
                    <button className="btn btn-primary btn-sm" onClick={handleTgSendCode} disabled={tgSendCodeMutation.isPending || !tgPhone || readOnly}>
                      {tgSendCodeMutation.isPending ? 'Отправка...' : 'Получить код'}
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => setTgLoginMode(null)} disabled={readOnly}>Отмена</button>
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
              )

            ) : tgStatus?.state === 'pending_password' ? (
              // 2FA — pending_password без явного режима (после phone+code снаружи)
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
              // Не подключено — выбор способа входа (QR — первичный)
              <div>
                <div style={{ marginBottom: '16px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  Подключите аккаунт Telegram для отправки сообщений кандидатам.
                  Рекомендуем войти через QR — надёжнее, чем ожидать SMS/код.
                </div>
                <div className="integ-actions" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleTgQrStart}
                    disabled={tgQrStartMutation.isPending || readOnly}
                    style={{ minWidth: 220 }}
                  >
                    {tgQrStartMutation.isPending ? 'Генерация QR…' : 'Подключить через QR'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setTgLoginMode('phone'); setTgPhone(''); setTgCode(''); }}
                    disabled={readOnly}
                    style={{ background: 'none', border: 'none', color: 'var(--fg-3)', cursor: readOnly ? 'default' : 'pointer', fontSize: 12, padding: 0 }}
                  >
                    Войти по коду (если QR не подходит) →
                  </button>
                </div>
                <div className="info-banner small" style={{ marginTop: 12 }}>
                  <Icon name="alert-triangle" size={14} />
                  <div>⚠️ Автоматизация аккаунта против правил Telegram — есть риск ограничений/бана.</div>
                </div>
              </div>
            )}
          </div>
        </IntegrationCard>

      </div>
    </div>
  );
}