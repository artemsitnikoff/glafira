import { useState } from 'react';
import { useProfile } from '@/api/hooks/useProfile';
import { useUpdateProfile } from '@/api/mutations/settings';
import { useClients } from '@/api/hooks/useClients';
import { useCreateClient, useUpdateClient, useDeleteClient } from '@/api/mutations/clients';
import { useGlafiraSettings, type TurnoverSource } from '@/api/hooks/useGlafiraSettings';
import { useUpdateGlafiraSettings } from '@/api/mutations/settings';
import { useBitrix24Status } from '@/api/hooks/useBitrix24Integration';
import { useBitrix24ImportEmployees, type Bitrix24ImportEmployeesResult } from '@/api/mutations/bitrix24Integration';
import { PageHead, Card, FormRow, Select, Radio } from '../components/FormComponents';
import { Icon } from '@/components/ui/Icon';
import { useAuthStore } from '@/store/authStore';
import type { ApiError } from '@/api/aliases';
import type { components } from '@/api/types';

type ClientOut = components['schemas']['ClientOut'];

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

type Notification = { type: 'success' | 'error'; message: string };

interface SettingsGeneralProps {
  readOnly?: boolean;
}

export function SettingsGeneral({ readOnly = false }: SettingsGeneralProps) {
  const { data: profile, isLoading } = useProfile();
  const updateProfileMutation = useUpdateProfile();

  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  // ── Локализация (существующий блок) ──────────────────────────────
  const [profileForm, setProfileForm] = useState<ExtendedProfile>(() => {
    const ext = (profile ?? {}) as ExtendedProfile;
    return {
      language: ext.language || 'ru',
      timezone: ext.timezone || 'Europe/Moscow',
      date_format: ext.date_format || 'DD.MM.YYYY'
    };
  });
  const [profileDirty, setProfileDirty] = useState(false);

  const handleProfileChange = (field: keyof ExtendedProfile, value: string) => {
    setProfileForm(prev => ({ ...prev, [field]: value }));
    setProfileDirty(true);
  };

  const handleProfileSave = async () => {
    try {
      // Cast: openapi не регенерён под language/timezone/date_format
      await updateProfileMutation.mutateAsync(profileForm as never);
      setProfileDirty(false);
    } catch {
      // Сохранение не удалось — dirty остаётся true (кнопка «Сохранить» активна).
    }
  };

  // ── Заказчики (клиенты) ──────────────────────────────────────────
  const { data: clients, isLoading: clientsLoading } = useClients();
  const createClient = useCreateClient();
  const updateClient = useUpdateClient();
  const deleteClient = useDeleteClient();

  const [clientsNotice, setClientsNotice] = useState<Notification | null>(null);

  const [creatingClient, setCreatingClient] = useState(false);
  const [newClientName, setNewClientName] = useState('');
  const [newClientContact, setNewClientContact] = useState('');

  const [editClientId, setEditClientId] = useState<string | null>(null);
  const [editClientName, setEditClientName] = useState('');
  const [editClientContact, setEditClientContact] = useState('');

  const clientErr = (e: unknown, fallback: string) => {
    const err = e as ApiError;
    setClientsNotice({ type: 'error', message: err.error?.message || fallback });
  };

  const handleCreateClient = async () => {
    if (!newClientName.trim()) return;
    try {
      await createClient.mutateAsync({
        name: newClientName.trim(),
        contact_person: newClientContact.trim() || null,
      });
      setNewClientName('');
      setNewClientContact('');
      setCreatingClient(false);
      setClientsNotice({ type: 'success', message: 'Заказчик добавлен' });
    } catch (e) {
      clientErr(e, 'Не удалось добавить заказчика');
    }
  };

  const startEditClient = (c: ClientOut) => {
    setEditClientId(c.id);
    setEditClientName(c.name);
    setEditClientContact(c.contact_person ?? '');
    setCreatingClient(false);
  };

  const handleSaveClient = async (id: string) => {
    if (!editClientName.trim()) return;
    try {
      await updateClient.mutateAsync({
        id,
        data: {
          name: editClientName.trim(),
          contact_person: editClientContact.trim() || null,
        },
      });
      setEditClientId(null);
      setClientsNotice({ type: 'success', message: 'Заказчик обновлён' });
    } catch (e) {
      clientErr(e, 'Не удалось обновить заказчика');
    }
  };

  const handleDeleteClient = async (c: ClientOut) => {
    if (!window.confirm(`Удалить заказчика «${c.name}»?`)) return;
    try {
      await deleteClient.mutateAsync(c.id);
      if (editClientId === c.id) setEditClientId(null);
      setClientsNotice({ type: 'success', message: 'Заказчик удалён' });
    } catch (e) {
      // 409 CONFLICT → показываем message бэка («Нельзя удалить: N вакансий…»)
      clientErr(e, 'Не удалось удалить заказчика');
    }
  };

  // ── Источник данных о текучке ────────────────────────────────────
  const { data: glafira, isLoading: glafiraLoading } = useGlafiraSettings();
  const updateGlafira = useUpdateGlafiraSettings();
  const { data: bitrixStatus } = useBitrix24Status();
  const importEmployees = useBitrix24ImportEmployees();

  const turnoverSource: TurnoverSource = glafira?.turnover_source ?? 'none';
  const bitrixConnected = !!bitrixStatus?.configured && !!bitrixStatus?.verified;

  const [turnoverNotice, setTurnoverNotice] = useState<Notification | null>(null);
  const [importResult, setImportResult] = useState<Bitrix24ImportEmployeesResult | null>(null);

  const handleTurnoverChange = async (value: TurnoverSource) => {
    if (value === turnoverSource) return;
    setTurnoverNotice(null);
    setImportResult(null);
    try {
      // Cast: turnover_source ещё не в сгенерированном GlafiraSettingsUpdate
      await updateGlafira.mutateAsync({ turnover_source: value } as never);
    } catch (e) {
      const err = e as ApiError;
      setTurnoverNotice({ type: 'error', message: err.error?.message || 'Не удалось сохранить источник текучки' });
    }
  };

  const handleImportEmployees = async () => {
    setTurnoverNotice(null);
    setImportResult(null);
    try {
      const result = await importEmployees.mutateAsync();
      setImportResult(result);
      setTurnoverNotice({
        type: 'success',
        message: `Создано ${result.created}, обновлено ${result.updated}, отмечено уволенными ${result.marked_left} (всего ${result.total})`,
      });
    } catch (e) {
      const err = e as ApiError;
      setTurnoverNotice({ type: 'error', message: err.error?.message || 'Не удалось импортировать сотрудников из Битрикс24' });
    }
  };

  if (isLoading) {
    return <div>Загрузка...</div>;
  }

  return (
    <div className="set-content-inner">
      <PageHead
        title="Общие настройки"
        subtitle="Локализация, заказчики и источник данных о текучке"
        dirty={profileDirty && !readOnly}
        onSave={readOnly ? undefined : handleProfileSave}
        saving={updateProfileMutation.isPending}
      />

      <Card title="Локализация и форматы">
        <div className="form-grid form-grid-2">
          <FormRow label="Язык интерфейса" required>
            <Select
              value={profileForm.language}
              options={LANGUAGES}
              onChange={readOnly ? undefined : (value) => handleProfileChange('language', value)}
              disabled={readOnly}
            />
          </FormRow>

          <FormRow label="Часовой пояс" required>
            <Select
              value={profileForm.timezone}
              options={TIMEZONES}
              onChange={readOnly ? undefined : (value) => handleProfileChange('timezone', value)}
              disabled={readOnly}
            />
          </FormRow>

          <FormRow label="Формат даты" required>
            <Select
              value={profileForm.date_format}
              options={DATE_FORMATS}
              onChange={readOnly ? undefined : (value) => handleProfileChange('date_format', value)}
              disabled={readOnly}
            />
          </FormRow>
        </div>
      </Card>

      {/* ── Заказчики (клиенты) ── */}
      <Card
        title="Заказчики"
        desc="Компании-заказчики, которые указываются в строке «Клиент» при создании вакансии"
      >
        {clientsNotice && (
          <div
            className={clientsNotice.type === 'success' ? 'info-banner' : 'error-banner'}
            style={{
              background: clientsNotice.type === 'success' ? 'var(--success-bg)' : 'var(--error-bg)',
              borderColor: clientsNotice.type === 'success' ? 'var(--success-border)' : 'var(--error-border)',
              color: clientsNotice.type === 'success' ? 'var(--success-fg)' : 'var(--error-fg)',
            }}
          >
            <Icon name={clientsNotice.type === 'success' ? 'check' : 'alert-circle'} size={16} />
            <div>{clientsNotice.message}</div>
          </div>
        )}

        <div className="tags-toolbar">
          <div style={{ flex: 1 }} />
          {!readOnly && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => {
                setNewClientName('');
                setNewClientContact('');
                setEditClientId(null);
                setCreatingClient((c) => !c);
              }}
            >
              <Icon name="plus" size={14} />
              Добавить заказчика
            </button>
          )}
        </div>

        {creatingClient && !readOnly && (
          <div className="tag-edit-row client-edit-row">
            <input
              className="tag-edit-input"
              placeholder="Название заказчика"
              value={newClientName}
              maxLength={200}
              autoFocus
              onChange={(e) => setNewClientName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreateClient()}
            />
            <input
              className="tag-edit-input"
              placeholder="Контактное лицо (необязательно)"
              value={newClientContact}
              maxLength={200}
              onChange={(e) => setNewClientContact(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreateClient()}
            />
            <button
              className="btn btn-primary btn-sm"
              onClick={handleCreateClient}
              disabled={createClient.isPending || !newClientName.trim()}
            >
              {createClient.isPending ? 'Сохранение…' : 'Создать'}
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => setCreatingClient(false)}>
              Отмена
            </button>
          </div>
        )}

        <div className="tags-table clients-table">
          <div className="tt-thead">
            <div>Заказчик</div>
            <div>Контактное лицо</div>
            <div></div>
          </div>

          {clientsLoading ? (
            <div className="tt-empty">Загрузка…</div>
          ) : (clients ?? []).length === 0 ? (
            <div className="tt-empty">Заказчиков пока нет — добавьте первого</div>
          ) : (
            (clients ?? []).map((c) =>
              editClientId === c.id ? (
                <div key={c.id} className="tag-edit-row client-edit-row">
                  <input
                    className="tag-edit-input"
                    value={editClientName}
                    maxLength={200}
                    autoFocus
                    onChange={(e) => setEditClientName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSaveClient(c.id)}
                  />
                  <input
                    className="tag-edit-input"
                    placeholder="Контактное лицо"
                    value={editClientContact}
                    maxLength={200}
                    onChange={(e) => setEditClientContact(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSaveClient(c.id)}
                  />
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleSaveClient(c.id)}
                    disabled={updateClient.isPending || !editClientName.trim()}
                  >
                    {updateClient.isPending ? 'Сохранение…' : 'Сохранить'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setEditClientId(null)}>
                    Отмена
                  </button>
                </div>
              ) : (
                <div key={c.id} className="tt-row">
                  <div style={{ fontWeight: 500 }}>{c.name}</div>
                  <div style={{ color: c.contact_person ? 'var(--fg-1)' : 'var(--fg-3)' }}>
                    {c.contact_person || '—'}
                  </div>
                  <div className="tt-actions">
                    {!readOnly && (
                      <>
                        <button className="row-icon-btn" title="Изменить" onClick={() => startEditClient(c)}>
                          <Icon name="edit" size={15} />
                        </button>
                        <button
                          className="row-icon-btn"
                          title="Удалить"
                          onClick={() => handleDeleteClient(c)}
                          disabled={deleteClient.isPending}
                        >
                          <Icon name="trash" size={15} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )
            )
          )}
        </div>
      </Card>

      {/* ── Источник данных о текучке ── */}
      <Card
        title="Источник данных о текучке"
        desc="Откуда система берёт сведения об увольнениях — для отчёта «Текучка после найма» в Аналитике"
      >
        {turnoverNotice && (
          <div
            className={turnoverNotice.type === 'success' ? 'info-banner' : 'error-banner'}
            style={{
              background: turnoverNotice.type === 'success' ? 'var(--success-bg)' : 'var(--error-bg)',
              borderColor: turnoverNotice.type === 'success' ? 'var(--success-border)' : 'var(--error-border)',
              color: turnoverNotice.type === 'success' ? 'var(--success-fg)' : 'var(--error-fg)',
            }}
          >
            <Icon name={turnoverNotice.type === 'success' ? 'check-circle' : 'alert-circle'} size={16} />
            <div>{turnoverNotice.message}</div>
          </div>
        )}

        {glafiraLoading ? (
          <div className="tt-empty">Загрузка…</div>
        ) : (
          <div className="src-radio-list">
            <Radio
              checked={turnoverSource === 'none'}
              onChange={readOnly ? undefined : () => handleTurnoverChange('none')}
              disabled={readOnly || updateGlafira.isPending}
              label="Нет"
              desc="Отчёт «Текучка после найма» в Аналитике и на Главной не считается"
            />
            <Radio
              checked={turnoverSource === 'bitrix24'}
              onChange={readOnly ? undefined : () => handleTurnoverChange('bitrix24')}
              disabled={readOnly || updateGlafira.isPending}
              label="Битрикс24"
              desc="Сведения об увольнениях берутся из Битрикс24"
              right={
                bitrixConnected ? (
                  <span className="conn-pill ok"><Icon name="check" size={12} />Подключено</span>
                ) : (
                  <span className="conn-pill bad">Не настроено</span>
                )
              }
            />
          </div>
        )}

        {turnoverSource === 'bitrix24' && (
          <div className="turnover-b24">
            {bitrixConnected ? (
              <>
                {isAdmin && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleImportEmployees}
                    disabled={importEmployees.isPending}
                  >
                    <Icon name="download" size={14} />
                    {importEmployees.isPending ? 'Импорт…' : 'Импортировать сотрудников из Б24'}
                  </button>
                )}

                {importResult && (
                  <div className="import-result-stats">
                    <span className="t-mono">Создано: {importResult.created}</span>
                    <span className="t-mono">Обновлено: {importResult.updated}</span>
                    <span className="t-mono">Отмечено уволенными: {importResult.marked_left}</span>
                    <span className="t-mono">Всего: {importResult.total}</span>
                  </div>
                )}

                <div className="info-banner small">
                  <Icon name="info" size={14} />
                  <div>
                    Битрикс24 не передаёт точную дату увольнения — текучка за первые 30 дней приблизительна
                    (считается по факту неактивности сотрудника).
                  </div>
                </div>
              </>
            ) : (
              <div className="info-banner muted">
                <Icon name="info" size={14} />
                <div>Сначала подключите Битрикс24 в разделе «Интеграции».</div>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
