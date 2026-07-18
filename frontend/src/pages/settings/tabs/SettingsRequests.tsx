import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import {
  useRequestStages, useCreateRequestStage, useUpdateRequestStage, useDeleteRequestStage,
  useRequestSettings, usePatchRequestSettings, useRequestFormLink, useRotateFormLink,
  type RequestStage, type RequestSettings,
} from '@/api/hooks/useRequests';
import '../../requests/requests.css';

function Toggle({ label, desc, value, onChange, disabled }: {
  label: string; desc: string; value: boolean; onChange: (v: boolean) => void; disabled?: boolean;
}) {
  return (
    <label style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '10px 0', cursor: disabled ? 'default' : 'pointer' }}>
      <input type="checkbox" checked={value} disabled={disabled}
        onChange={(e) => onChange(e.target.checked)} style={{ marginTop: 2, width: 16, height: 16 }} />
      <span>
        <span style={{ fontWeight: 600, fontSize: 13.5, color: 'var(--fg-1)' }}>{label}</span>
        <span style={{ display: 'block', fontSize: 12.5, color: 'var(--fg-3)', marginTop: 2 }}>{desc}</span>
      </span>
    </label>
  );
}

export function SettingsRequests({ readOnly = false }: { readOnly?: boolean }) {
  const { data: stages } = useRequestStages();
  const createStage = useCreateRequestStage();
  const updateStage = useUpdateRequestStage();
  const deleteStage = useDeleteRequestStage();

  const { data: settings } = useRequestSettings();
  const patchSettings = usePatchRequestSettings();

  const { data: formLink } = useRequestFormLink();
  const rotateLink = useRotateFormLink();

  const [newLabel, setNewLabel] = useState('');
  const [copied, setCopied] = useState(false);

  const setToggle = (patch: Partial<RequestSettings>) => {
    if (readOnly) return;
    patchSettings.mutate(patch);
  };

  const addStage = () => {
    const label = newLabel.trim();
    if (!label) return;
    createStage.mutate({ label }, { onSuccess: () => setNewLabel('') });
  };

  const copyLink = async () => {
    let url = formLink?.url;
    if (!url || !formLink?.enabled) {
      const res = await rotateLink.mutateAsync();
      url = res.url || undefined;
    }
    if (url) {
      try { await navigator.clipboard.writeText(url); } catch { /* clipboard недоступен */ }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const fixed = (stages || []).filter((s) => !s.custom);
  const custom = (stages || []).filter((s) => s.custom);

  return (
    <div className="set-content-inner">
      <div className="set-h1">Воронка заявок</div>

      {/* Этапы */}
      <div className="set-card">
        <div className="set-card-head">
          <div className="set-card-title">Этапы воронки заявок</div>
          <div className="set-card-desc">
            Закреплённые этапы (Новая, В работе, В подборе, Закрыта, Отклонена) изменить нельзя.
            Свои этапы добавляются между «В работе» и «В подборе» (например, «На согласовании»).
          </div>
        </div>
        <div className="set-card-body">
          <div className="reason-chips">
            {fixed.map((s: RequestStage) => (
              <span key={s.key} className="reason-chip reason-chip-co">
                <span className="r-bullet" style={{ background: s.color }} />
                <span className="reason-chip-input" style={{ padding: '0 4px' }}>{s.label}</span>
                <span className="reason-chip-lock" title="Закреплённый этап — нельзя изменить"><Icon name="lock" size={11} /></span>
              </span>
            ))}
            {custom.map((s: RequestStage) => (
              <span key={s.key} className="reason-chip reason-chip-cand">
                <span className="r-bullet" style={{ background: s.color }} />
                <input className="reason-chip-input" defaultValue={s.label}
                  size={Math.max(s.label.length, 4)} disabled={readOnly}
                  onBlur={(e) => {
                    const v = e.target.value.trim();
                    if (v && v !== s.label) updateStage.mutate({ key: s.key, label: v });
                  }} />
                {!readOnly && (
                  <button className="reason-chip-x" aria-label="Удалить"
                    onClick={() => deleteStage.mutate(s.key)}><Icon name="x" size={11} /></button>
                )}
              </span>
            ))}
          </div>
          {!readOnly && (
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <input className="nv-input" placeholder="Название своего этапа" value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addStage()}
                style={{ maxWidth: 280, height: 34 }} />
              <button className="btn btn-secondary btn-sm" disabled={!newLabel.trim() || createStage.isPending}
                onClick={addStage}><Icon name="plus" size={13} /> Добавить этап</button>
            </div>
          )}
        </div>
      </div>

      {/* Правила */}
      <div className="set-card">
        <div className="set-card-head">
          <div className="set-card-title">Правила</div>
        </div>
        <div className="set-card-body">
          <Toggle label="Автозакрытие при найме всех позиций"
            desc="Когда нанятых станет столько, сколько нужно по заявке, она закроется автоматически."
            value={!!settings?.autoclose_on} disabled={readOnly}
            onChange={(v) => setToggle({ autoclose_on: v })} />
          <Toggle label="Вопрос в треде из «Новой» переводит в «В работе»"
            desc="Как только рекрутер или менеджер задаёт первый вопрос по новой заявке, она берётся в работу."
            value={!!settings?.question_moves_to_work} disabled={readOnly}
            onChange={(v) => setToggle({ question_moves_to_work: v })} />
          <Toggle label="Уведомлять менеджера при смене этапа"
            desc="Менеджеру-пользователю Глафиры уходит письмо на email при изменении статуса его заявки. Заявителям с публичной формы авто-уведомления не отправляются — рекрутер связывается по оставленному контакту."
            value={!!settings?.notify_manager_on_stage} disabled={readOnly}
            onChange={(v) => setToggle({ notify_manager_on_stage: v })} />
        </div>
      </div>

      {/* Публичная форма */}
      <div className="set-card">
        <div className="set-card-head">
          <div className="set-card-title">Ссылка на форму заявки</div>
          <div className="set-card-desc">
            Длинная непубличная ссылка — отправьте её нанимающим менеджерам, чтобы они подавали заявки
            без входа в систему. Заявки с формы помечаются «по ссылке-форме». Обновление ссылки делает
            старую недействительной.
          </div>
        </div>
        <div className="set-card-body">
          <Toggle label="Приём заявок по ссылке включён"
            desc="Пока выключено — форма по ссылке отдаёт «форма не найдена»."
            value={!!settings?.form_enabled} disabled={readOnly}
            onChange={(v) => setToggle({ form_enabled: v })} />
          <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <input className="nv-input" readOnly value={formLink?.url || 'Ссылка ещё не создана'}
              style={{ flex: 1, minWidth: 240, height: 34, color: formLink?.url ? 'var(--fg-1)' : 'var(--fg-3)' }} />
            <button className="btn btn-secondary btn-sm" onClick={copyLink} disabled={readOnly}>
              <Icon name={copied ? 'check' : 'link'} size={13} /> {copied ? 'Скопировано' : 'Скопировать'}
            </button>
            {!readOnly && (
              <button className="btn btn-secondary btn-sm" onClick={() => rotateLink.mutate()} disabled={rotateLink.isPending}>
                <Icon name="refresh" size={13} /> Обновить ссылку
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
