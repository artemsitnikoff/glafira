import { useState, useEffect, useMemo } from 'react';
import { useProfile } from '@/api/hooks/useProfile';
import { useUpdateProfile, useChangePassword } from '@/api/mutations/settings';
import { FieldDot } from '../components/FieldDot';
import { Avatar } from '@/components/ui/Avatar';
import { Icon } from '@/components/ui/Icon';
import type { ProfileOut } from '@/api/aliases';

type Props = {
  onDirtyChange: (dirty: boolean) => void;
  onSaveHandler: (handler: (() => Promise<void>) | null) => void;
  onDiscardHandler: (handler: (() => void) | null) => void;
};

// Static list of timezones (IANA)
const TIMEZONES = [
  'Europe/Moscow',
  'Europe/Kaliningrad',
  'Asia/Yekaterinburg',
  'Asia/Omsk',
  'Asia/Krasnoyarsk',
  'Asia/Irkutsk',
  'Asia/Yakutsk',
  'Asia/Vladivostok',
  'Asia/Magadan',
  'Asia/Kamchatka',
];

export function ProfileTab({ onDirtyChange, onSaveHandler, onDiscardHandler }: Props) {
  const { data: profile, isLoading } = useProfile();
  const updateProfile = useUpdateProfile();
  const changePassword = useChangePassword();

  const [formData, setFormData] = useState<Partial<ProfileOut>>({});
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    new_password: '',
    new_password_confirm: '',
  });
  const [showPassword, setShowPassword] = useState({
    current: false,
    new: false,
    confirm: false,
  });

  // Initialize form with profile data
  useEffect(() => {
    if (profile) {
      setFormData(profile);
    }
  }, [profile]);

  // Check if form is dirty
  const isDirty = useMemo(() => {
    if (!profile) return false;

    return Object.keys(formData).some((key) => {
      const profileKey = key as keyof ProfileOut;
      return formData[profileKey] !== profile[profileKey];
    });
  }, [formData, profile]);

  const isPasswordFormFilled = Boolean(passwordForm.current_password || passwordForm.new_password || passwordForm.new_password_confirm);

  useEffect(() => {
    onDirtyChange(isDirty || isPasswordFormFilled);
  }, [isDirty, isPasswordFormFilled, onDirtyChange]);

  const handleSave = async () => {
    if (isDirty && profile) {
      const updates: Record<string, any> = {};
      Object.keys(formData).forEach((key) => {
        const profileKey = key as keyof ProfileOut;
        if (formData[profileKey] !== profile[profileKey]) {
          updates[key] = formData[profileKey];
        }
      });

      if (Object.keys(updates).length > 0) {
        await updateProfile.mutateAsync(updates);
      }
    }

    if (isPasswordFormFilled) {
      if (passwordForm.new_password !== passwordForm.new_password_confirm) {
        throw new Error('Пароли не совпадают');
      }
      await changePassword.mutateAsync(passwordForm);
      setPasswordForm({
        current_password: '',
        new_password: '',
        new_password_confirm: '',
      });
    }
  };

  const handleDiscard = () => {
    if (profile) {
      setFormData(profile);
    }
    setPasswordForm({
      current_password: '',
      new_password: '',
      new_password_confirm: '',
    });
  };

  useEffect(() => {
    onSaveHandler(handleSave);
    onDiscardHandler(handleDiscard);
  }, [formData, passwordForm, profile, onSaveHandler, onDiscardHandler]);

  const updateField = (field: keyof ProfileOut, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const updatePasswordField = (field: keyof typeof passwordForm, value: string) => {
    setPasswordForm(prev => ({ ...prev, [field]: value }));
  };

  const isFieldDirty = (field: keyof ProfileOut) => {
    return profile ? formData[field] !== profile[field] : false;
  };

  if (isLoading) {
    return <div className="settings-loading">Загрузка...</div>;
  }

  return (
    <div className="settings-content-inner">
      {/* Profile Card */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Основные данные</h2>
          <p className="settings-card-desc">Ваш профиль и контактная информация</p>
        </div>
        <div className="settings-card-body">
          {/* Avatar */}
          <div className="profile-avatar-section">
            <div className="profile-avatar-area">
              <Avatar
                name={formData.full_name || ''}
                src={formData.avatar_url}
                size="lg"
              />
              <button className="btn btn-secondary btn-sm">
                <Icon name="upload" size={16} />
                Изменить аватар
              </button>
            </div>
          </div>

          {/* Form Fields */}
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label">
                <FieldDot dirty={isFieldDirty('full_name')} />
                ФИО <span className="required">*</span>
              </label>
              <input
                type="text"
                className="form-input"
                value={formData.full_name || ''}
                onChange={(e) => updateField('full_name', e.target.value)}
                placeholder="Введите полное имя"
              />
            </div>

            <div className="form-field">
              <label className="form-label">
                <FieldDot dirty={isFieldDirty('position')} />
                Должность
              </label>
              <input
                type="text"
                className="form-input"
                value={formData.position || ''}
                onChange={(e) => updateField('position', e.target.value)}
                placeholder="Ваша должность"
              />
            </div>

            <div className="form-field">
              <label className="form-label">
                <FieldDot dirty={isFieldDirty('email')} />
                Email <span className="required">*</span>
              </label>
              <input
                type="email"
                className="form-input"
                value={formData.email || ''}
                onChange={(e) => updateField('email', e.target.value)}
                placeholder="email@company.ru"
              />
            </div>

            <div className="form-field">
              <label className="form-label">
                <FieldDot dirty={isFieldDirty('phone')} />
                Телефон
              </label>
              <input
                type="tel"
                className="form-input"
                value={formData.phone || ''}
                onChange={(e) => updateField('phone', e.target.value)}
                placeholder="+7 (999) 123-45-67"
              />
            </div>

            <div className="form-field form-field-full">
              <label className="form-label">
                <FieldDot dirty={isFieldDirty('timezone')} />
                Часовой пояс
              </label>
              <select
                className="form-select"
                value={formData.timezone || ''}
                onChange={(e) => updateField('timezone', e.target.value)}
              >
                <option value="">Выберите часовой пояс</option>
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Password Change Card */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Смена пароля</h2>
          <p className="settings-card-desc">Обновите пароль для входа в систему</p>
        </div>
        <div className="settings-card-body">
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label">Текущий пароль</label>
              <div className="password-field">
                <input
                  type={showPassword.current ? 'text' : 'password'}
                  className="form-input"
                  value={passwordForm.current_password}
                  onChange={(e) => updatePasswordField('current_password', e.target.value)}
                  placeholder="Введите текущий пароль"
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword(prev => ({ ...prev, current: !prev.current }))}
                >
                  <Icon name={showPassword.current ? 'x' : 'x'} size={16} />
                </button>
              </div>
            </div>

            <div className="form-field">
              <label className="form-label">Новый пароль</label>
              <div className="password-field">
                <input
                  type={showPassword.new ? 'text' : 'password'}
                  className="form-input"
                  value={passwordForm.new_password}
                  onChange={(e) => updatePasswordField('new_password', e.target.value)}
                  placeholder="Введите новый пароль"
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword(prev => ({ ...prev, new: !prev.new }))}
                >
                  <Icon name={showPassword.new ? 'x' : 'x'} size={16} />
                </button>
              </div>
            </div>

            <div className="form-field">
              <label className="form-label">Подтверждение пароля</label>
              <div className="password-field">
                <input
                  type={showPassword.confirm ? 'text' : 'password'}
                  className="form-input"
                  value={passwordForm.new_password_confirm}
                  onChange={(e) => updatePasswordField('new_password_confirm', e.target.value)}
                  placeholder="Повторите новый пароль"
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword(prev => ({ ...prev, confirm: !prev.confirm }))}
                >
                  <Icon name={showPassword.confirm ? 'x' : 'x'} size={16} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}