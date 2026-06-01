import { useState, useEffect } from 'react';
import { useProfile } from '@/api/hooks/useProfile';
import { useUpdateProfile } from '@/api/mutations/settings';
import { PageHead, Card, FormRow, Select } from '../components/FormComponents';

// Extended profile type with new fields
type ExtendedProfile = {
  language?: string;
  timezone?: string;
  date_format?: string;
};

const LANGUAGES = [
  { value: 'ru', label: 'Русский' },
  { value: 'en', label: 'English' }
];

const TIMEZONES = [
  { value: 'Europe/Moscow', label: 'Москва (UTC+3)' },
  { value: 'Asia/Yekaterinburg', label: 'Екатеринбург (UTC+5)' },
  { value: 'Asia/Novosibirsk', label: 'Новосибирск (UTC+7)' }
];

const DATE_FORMATS = [
  { value: 'DD.MM.YYYY', label: 'DD.MM.YYYY' },
  { value: 'YYYY-MM-DD', label: 'YYYY-MM-DD' },
  { value: 'DD месяц YYYY', label: 'DD месяц YYYY' }
];

interface SettingsGeneralProps {
  readOnly?: boolean;
}

export function SettingsGeneral({ readOnly = false }: SettingsGeneralProps) {
  const { data: profile, isLoading } = useProfile();
  const updateProfileMutation = useUpdateProfile();

  const [dirty, setDirty] = useState(false);
  const [form, setForm] = useState<ExtendedProfile>({
    language: 'ru',
    timezone: 'Europe/Moscow',
    date_format: 'DD.MM.YYYY'
  });

  // Initialize form when profile loads
  useEffect(() => {
    if (profile) {
      const extendedProfile = profile as ExtendedProfile;
      setForm({
        language: extendedProfile.language || 'ru',
        timezone: extendedProfile.timezone || 'Europe/Moscow',
        date_format: extendedProfile.date_format || 'DD.MM.YYYY'
      });
    }
  }, [profile]);

  const handleChange = (field: keyof ExtendedProfile, value: string) => {
    setForm(prev => ({ ...prev, [field]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    try {
      // Cast to bypass TypeScript validation since openapi not regenerated
      await updateProfileMutation.mutateAsync(form as any);
      setDirty(false);
    } catch {
      // Сохранение не удалось — dirty остаётся true (кнопка «Сохранить» активна),
      // пользователь видит, что не сохранилось. (Тост-системы в проекте нет.)
    }
  };

  if (isLoading) {
    return <div>Загрузка...</div>;
  }

  return (
    <div className="set-content-inner">
      <PageHead
        title="Общие настройки"
        subtitle="Персональные настройки пользователя: язык интерфейса, часовой пояс и формат даты"
        dirty={dirty && !readOnly}
        onSave={readOnly ? undefined : handleSave}
      />

      <Card title="Локализация и форматы">
        <div className="form-grid form-grid-2">
          <FormRow label="Язык интерфейса" required>
            <Select
              value={form.language}
              options={LANGUAGES}
              onChange={readOnly ? undefined : (value) => handleChange('language', value)}
              disabled={readOnly}
            />
          </FormRow>

          <FormRow label="Часовой пояс" required>
            <Select
              value={form.timezone}
              options={TIMEZONES}
              onChange={readOnly ? undefined : (value) => handleChange('timezone', value)}
              disabled={readOnly}
            />
          </FormRow>

          <FormRow label="Формат даты" required>
            <Select
              value={form.date_format}
              options={DATE_FORMATS}
              onChange={readOnly ? undefined : (value) => handleChange('date_format', value)}
              disabled={readOnly}
            />
          </FormRow>
        </div>
      </Card>
    </div>
  );
}