import { useEffect, useMemo, useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { PageHead, Card, FormRow, TextInput, Select, Switch } from '../components/FormComponents';
import { useProfile } from '@/api/hooks/useProfile';
import { useUpdateProfile } from '@/api/mutations/settings';
import { useAuthStore } from '@/store/authStore';
import { ChangePasswordModal } from './components/ChangePasswordModal';
import type { ApiError } from '@/api/aliases';

interface SettingsProfileProps {
  readOnly?: boolean;
}

// openapi НЕ регенерён: сгенерённый ProfileOut/ProfileUpdate в types.ts отстал и не
// содержит language/date_format, хотя бэк их поддерживает. Доступ — через локальные типы.
type ProfileExtra = { language?: string; date_format?: string };

// Часовые пояса РФ (value = IANA, label = город/смещение). Текущий tz пользователя
// добавляется в список, если его здесь нет — чтобы Select не оказался пустым.
const TZ_OPTIONS: { value: string; label: string }[] = [
  { value: 'Europe/Kaliningrad', label: 'Калининград (UTC+2)' },
  { value: 'Europe/Moscow', label: 'Москва (UTC+3)' },
  { value: 'Europe/Samara', label: 'Самара (UTC+4)' },
  { value: 'Asia/Yekaterinburg', label: 'Екатеринбург (UTC+5)' },
  { value: 'Asia/Omsk', label: 'Омск (UTC+6)' },
  { value: 'Asia/Novosibirsk', label: 'Новосибирск (UTC+7)' },
  { value: 'Asia/Irkutsk', label: 'Иркутск (UTC+8)' },
  { value: 'Asia/Yakutsk', label: 'Якутск (UTC+9)' },
  { value: 'Asia/Vladivostok', label: 'Владивосток (UTC+10)' },
  { value: 'Asia/Magadan', label: 'Магадан (UTC+11)' },
  { value: 'Asia/Kamchatka', label: 'Камчатка (UTC+12)' },
];

const LANG_OPTIONS = [
  { value: 'ru', label: 'Русский' },
  { value: 'en', label: 'English' },
];

type FormState = {
  full_name: string;
  position: string;
  email: string;
  phone: string;
  timezone: string;
  language: string;
};

const ROLE_LABELS: Record<string, string> = {
  admin: 'Администратор',
  recruiter: 'Рекрутёр',
  manager: 'Нанимающий менеджер',
};

export function SettingsProfile({ readOnly = false }: SettingsProfileProps) {
  const { data: profile, isLoading } = useProfile();
  const updateProfile = useUpdateProfile();
  const setUser = useAuthStore((s) => s.setUser);
  const currentUser = useAuthStore((s) => s.user);

  const [form, setForm] = useState<FormState | null>(null);
  const [initial, setInitial] = useState<FormState | null>(null);
  const [showPwdModal, setShowPwdModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (profile) {
      const f: FormState = {
        full_name: profile.full_name ?? '',
        position: profile.position ?? '',
        email: profile.email ?? '',
        phone: profile.phone ?? '',
        timezone: profile.timezone ?? 'Europe/Moscow',
        language: (profile as ProfileExtra).language ?? 'ru',
      };
      setForm(f);
      setInitial(f);
    }
  }, [profile]);

  const tzOptions = useMemo(() => {
    if (form && form.timezone && !TZ_OPTIONS.some((o) => o.value === form.timezone)) {
      return [{ value: form.timezone, label: form.timezone }, ...TZ_OPTIONS];
    }
    return TZ_OPTIONS;
  }, [form]);

  const dirty = useMemo(() => {
    if (!form || !initial) return false;
    return (Object.keys(form) as (keyof FormState)[]).some((k) => form[k] !== initial[k]);
  }, [form, initial]);

  const set = (key: keyof FormState, value: string) => {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
    setError(null);
  };

  const handleSave = async () => {
    if (!form || !dirty) return;
    setError(null);
    if (!form.full_name.trim()) {
      setError('ФИО не может быть пустым');
      return;
    }
    if (!form.email.trim()) {
      setError('Email не может быть пустым');
      return;
    }
    try {
      // payload включает language (бэк поддерживает) — cast вокруг устаревшего ProfileUpdate
      const payload = {
        full_name: form.full_name.trim(),
        position: form.position.trim() || null,
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        timezone: form.timezone,
        language: form.language,
      };
      const updated = await updateProfile.mutateAsync(
        payload as Parameters<typeof updateProfile.mutateAsync>[0]
      );
      // Синхронизируем authStore — чтобы сайдбар/аватар сразу показали новое имя
      if (currentUser) {
        const u = updated as { full_name?: string; position?: string | null; email?: string; timezone?: string };
        setUser({
          ...currentUser,
          full_name: u.full_name ?? form.full_name,
          position: u.position ?? (form.position || null),
          email: u.email ?? form.email,
          timezone: u.timezone ?? form.timezone,
        });
      }
      setInitial(form);
    } catch (err) {
      const e = err as unknown as ApiError;
      setError(e.error?.message || 'Не удалось сохранить профиль');
    }
  };

  const handleDiscard = () => {
    setForm(initial);
    setError(null);
  };

  if (isLoading || !form || !profile) {
    return (
      <div className="set-content-inner">
        <PageHead title="Мой профиль" subtitle="Личные данные и безопасность" />
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--fg-3)' }}>
          Загрузка профиля…
        </div>
      </div>
    );
  }

  const locked = readOnly;

  return (
    <div className="set-content-inner">
      <PageHead
        title="Мой профиль"
        subtitle="Личные данные и безопасность"
        dirty={dirty && !locked}
        saving={updateProfile.isPending}
        onSave={handleSave}
        onDiscard={handleDiscard}
      />

      {error && (
        <div className="error-banner" style={{ marginBottom: 16 }}>
          <Icon name="alert-circle" size={16} />
          <span>{error}</span>
        </div>
      )}

      <Card title="Аватар и основные данные">
        <div className="profile-avatar-row">
          <div className="big-avatar">
            <Avatar name={form.full_name || profile.full_name} size="lg" />
          </div>
          <div className="avatar-actions">
            <button className="btn btn-secondary btn-sm" disabled>Загрузить фото</button>
            <button className="btn btn-ghost btn-sm" disabled>Удалить</button>
            <div className="t-caption" style={{ marginTop: 6 }}>
              Загрузка фото — скоро. Пока отображаются инициалы.
            </div>
          </div>
        </div>
        <div className="form-grid form-grid-2">
          <FormRow label="ФИО" required>
            <TextInput value={form.full_name} onChange={(v) => set('full_name', v)} locked={locked} />
          </FormRow>
          <FormRow label="Должность">
            <TextInput value={form.position} onChange={(v) => set('position', v)} locked={locked} />
          </FormRow>
          <FormRow label="Email" required hint="На этот адрес приходят уведомления и приглашения">
            <TextInput type="email" value={form.email} onChange={(v) => set('email', v)} locked={locked} />
          </FormRow>
          <FormRow label="Телефон">
            <TextInput value={form.phone} onChange={(v) => set('phone', v)} locked={locked} />
          </FormRow>
          <FormRow label="Часовой пояс">
            <Select value={form.timezone} options={tzOptions} onChange={(v) => set('timezone', v)} disabled={locked} />
          </FormRow>
          <FormRow label="Язык интерфейса">
            <Select value={form.language} options={LANG_OPTIONS} onChange={(v) => set('language', v)} disabled={locked} />
          </FormRow>
          <FormRow label="Роль">
            <TextInput value={ROLE_LABELS[profile.role] || profile.role} locked />
          </FormRow>
        </div>
      </Card>

      <Card title="Безопасность">
        <div className="action-row">
          <div>
            <div className="ar-title">Пароль</div>
            <div className="ar-desc">Регулярно обновляйте пароль для безопасности аккаунта.</div>
          </div>
          <button className="btn btn-secondary" onClick={() => setShowPwdModal(true)} disabled={locked}>
            Сменить пароль
          </button>
        </div>
      </Card>

      <Card title="Уведомления" desc="Каналы доставки и события, по которым вам приходят оповещения">
        <div className="info-banner muted" style={{ marginBottom: 12 }}>
          <Icon name="bell" size={16} />
          <div><b>Скоро.</b> Настройка уведомлений появится позже.</div>
        </div>
        <div className="notif-table">
          <div className="notif-thead">
            <div>Событие</div>
            <div>Email</div>
            <div>Telegram</div>
            <div>Push</div>
          </div>
          {[
            ['Новый отклик на мою вакансию', true, true, false],
            ['Глафира квалифицировала кандидата', true, true, true],
            ['Кандидат перешёл на этап «Оффер»', true, false, true],
            ['Заказчик оставил оценку', true, true, false],
            ['Ежедневный дайджест по почте', true, false, false],
            ['Еженедельный отчёт', true, false, false],
          ].map((r, i) => (
            <div key={i} className="notif-row">
              <div className="notif-evt">{r[0]}</div>
              <div><Switch value={r[1] as boolean} disabled /></div>
              <div><Switch value={r[2] as boolean} disabled /></div>
              <div><Switch value={r[3] as boolean} disabled /></div>
            </div>
          ))}
        </div>
      </Card>

      <ChangePasswordModal isOpen={showPwdModal} onClose={() => setShowPwdModal(false)} />
    </div>
  );
}
