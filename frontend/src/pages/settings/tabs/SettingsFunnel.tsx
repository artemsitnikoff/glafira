import { useState, useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/ui/Icon';
import { api } from '@/api/client';
import { useDefaultFunnel, type DefaultFunnelStage } from '@/api/hooks/useDefaultFunnel';
import { useFunnelTemplates } from '@/api/hooks/useFunnelTemplates';
import { useFunnelTemplateStages } from '@/api/hooks/useFunnelTemplateStages';
import { useRejectReasons, type RejectReasonOut } from '@/api/hooks/useRejectReasons';
import { PageHead, Card } from '../components/FormComponents';
import type { ApiError } from '@/api/aliases';

// Защищённые (системные) этапы — зеркало с бэкенда (core/stages.py PROTECTED_STAGE_KEYS).
const PROTECTED_STAGE_KEYS = new Set(['hired', 'rejected', 'added', 'response']);

type StageTypeKey = 'start' | 'system' | 'middle' | 'finalOk' | 'finalBad';

const FUNNEL_STAGE_TYPES: Record<StageTypeKey, { label: string; dot: string; bg: string; fg: string }> = {
  start: { label: 'Стартовый', dot: '#2A8AF0', bg: '#EAF3FE', fg: '#1865BE' },
  system: { label: 'Системный', dot: '#7E5CF0', bg: '#F0EAFE', fg: '#5C3FBE' },
  middle: { label: 'Промежуточный', dot: '#9AA3AE', bg: '#ECEFF2', fg: '#3A4452' },
  finalOk: { label: 'Финальный · успех', dot: '#16A34A', bg: '#DEF5E5', fg: '#128640' },
  finalBad: { label: 'Финальный · отказ', dot: '#DC4646', bg: '#FCE3E3', fg: '#B83030' },
};
const MIDDLE_FALLBACK = FUNNEL_STAGE_TYPES.middle;

type StageDraft = { stage_key: string; label: string; is_terminal: boolean };
type ReasonDraft = { key: string; id?: string; side: 'candidate' | 'company'; label: string; order_index: number; is_system: boolean };

function deriveStageType(stage: StageDraft, index: number): StageTypeKey {
  if (index === 0) return 'start';
  if (stage.is_terminal) {
    return stage.stage_key === 'hired' || stage.label.toLowerCase().includes('нанят') ? 'finalOk' : 'finalBad';
  }
  if (PROTECTED_STAGE_KEYS.has(stage.stage_key)) return 'system';
  return 'middle';
}

const STAGE_DESCRIPTIONS: Record<string, string> = {
  response: 'Кандидат пришёл с источника. Глафира делает первичный скрининг и зовёт в чат.',
  added: 'Кандидат добавлен рекрутером вручную из общей базы. Системный этап, не удаляется.',
  selected: 'Глафира посчитала кандидата подходящим — ждём контакта рекрутера.',
  recruiter: 'Назначен/проведён звонок-знакомство.',
  interview: 'Техническое или профильное интервью.',
  manager: 'Финальная встреча с заказчиком.',
  offer: 'Оффер выслан и согласовывается.',
  hired: 'Кандидат вышел на работу. Стартует Пульс-Онбординг.',
  rejected: 'Завершение по причине из справочника.',
};

function stageDescription(stageKey: string, type: StageTypeKey): string {
  return STAGE_DESCRIPTIONS[stageKey] ||
    (type === 'finalOk' ? 'Успешное завершение процесса подбора.' :
     type === 'finalBad' ? 'Завершение процесса по причине отказа.' :
     type === 'system' ? 'Системный этап воронки.' :
     'Этап процесса подбора.');
}

// --- Диффы черновик↔сервер. basePath: '/settings/default-funnel' или
//     '/settings/funnel-templates/{id}/stages' — оба используют {base}/{key} и {base}/reorder. ---
async function applyStageDiff(draft: StageDraft[], server: DefaultFunnelStage[], basePath: string): Promise<void> {
  const serverByKey = new Map(server.map(s => [s.stage_key, s]));
  const draftKeys = new Set(draft.map(s => s.stage_key));

  for (const s of server) {
    if (!draftKeys.has(s.stage_key) && !PROTECTED_STAGE_KEYS.has(s.stage_key)) {
      await api.delete(`${basePath}/${s.stage_key}`);
    }
  }
  for (let i = 0; i < draft.length; i++) {
    const s = draft[i];
    if (!serverByKey.has(s.stage_key)) {
      await api.post(basePath, {
        stage_key: s.stage_key,
        label: s.label.trim().substring(0, 60),
        order_index: i + 1,
        is_terminal: s.is_terminal,
      });
    }
  }
  for (const s of draft) {
    const orig = serverByKey.get(s.stage_key);
    if (orig && orig.label !== s.label.trim()) {
      await api.patch(`${basePath}/${s.stage_key}`, { label: s.label.trim().substring(0, 60) });
    }
  }
  const draftOrder = draft.map(s => s.stage_key);
  const serverOrder = server.map(s => s.stage_key);
  if (draftOrder.join(' ') !== serverOrder.join(' ')) {
    await api.put(`${basePath}/reorder`, { order: draftOrder });
  }
}

async function applyReasonDiff(draft: ReasonDraft[], server: RejectReasonOut[]): Promise<void> {
  const serverById = new Map(server.map(r => [r.id, r]));
  const draftIds = new Set(draft.filter(r => r.id).map(r => r.id));

  for (const r of server) {
    if (!draftIds.has(r.id) && !(r as RejectReasonOut).is_system) {
      await api.delete(`/settings/reject-reasons/${r.id}`);
    }
  }
  for (const r of draft) {
    if (!r.id) {
      await api.post('/settings/reject-reasons', { side: r.side, label: r.label.trim().substring(0, 120), order_index: r.order_index });
    }
  }
  for (const r of draft) {
    if (r.id) {
      const orig = serverById.get(r.id);
      if (orig && orig.label !== r.label.trim()) {
        await api.patch(`/settings/reject-reasons/${r.id}`, { label: r.label.trim().substring(0, 120) });
      }
    }
  }
}

interface SettingsFunnelProps {
  readOnly?: boolean;
}

export function SettingsFunnel({ readOnly = false }: SettingsFunnelProps) {
  const queryClient = useQueryClient();
  const { data: templates } = useFunnelTemplates();
  const [selected, setSelected] = useState<string>('default'); // 'default' | id шаблона
  const isDefault = selected === 'default';

  const { data: defaultStages, isLoading: dLoading } = useDefaultFunnel();
  const { data: tplStages, isLoading: tLoading } = useFunnelTemplateStages(isDefault ? undefined : selected);
  const serverStages = isDefault ? defaultStages : tplStages;
  const stagesLoading = isDefault ? dLoading : tLoading;
  const stageBasePath = isDefault ? '/settings/default-funnel' : `/settings/funnel-templates/${selected}/stages`;

  const { data: serverReasons, isLoading: reasonsLoading } = useRejectReasons();

  const [draftStages, setDraftStages] = useState<StageDraft[] | null>(null);
  const [draftReasons, setDraftReasons] = useState<ReasonDraft[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const newStageCounter = useRef(0);
  const newReasonCounter = useRef(0);

  useEffect(() => {
    if (serverStages && !dirty) {
      setDraftStages(serverStages.map(s => ({ stage_key: s.stage_key, label: s.label, is_terminal: s.is_terminal })));
    }
  }, [serverStages, dirty]);

  useEffect(() => {
    if (serverReasons && !dirty) {
      setDraftReasons(serverReasons.map(r => ({
        key: r.id, id: r.id, side: r.side === 'company' ? 'company' : 'candidate',
        label: r.label, order_index: r.order_index ?? 0, is_system: !!(r as RejectReasonOut).is_system,
      })));
    }
  }, [serverReasons, dirty]);

  const markDirty = () => setDirty(true);

  const renameStage = (idx: number, label: string) => {
    setDraftStages(prev => prev ? prev.map((s, i) => i === idx ? { ...s, label } : s) : prev);
    markDirty();
  };
  const deleteStage = (idx: number) => {
    setDraftStages(prev => prev ? prev.filter((_, i) => i !== idx) : prev);
    markDirty();
  };
  const addStage = () => {
    setDraftStages(prev => {
      if (!prev) return prev;
      const stage_key = `s_${Date.now().toString(36)}${newStageCounter.current++}`;
      const next = prev.slice();
      next.splice(Math.max(prev.length - 2, 1), 0, { stage_key, label: 'Новый этап', is_terminal: false });
      return next;
    });
    markDirty();
  };
  const moveStage = (idx: number, dir: number) => {
    setDraftStages(prev => {
      if (!prev) return prev;
      const j = idx + dir;
      if (j < 1 || j > prev.length - 2) return prev;
      if (idx === 0 || idx >= prev.length - 2) return prev;
      const next = prev.slice();
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
    markDirty();
  };

  const renameReason = (key: string, label: string) => {
    setDraftReasons(prev => prev ? prev.map(r => r.key === key ? { ...r, label } : r) : prev);
    markDirty();
  };
  const deleteReason = (key: string) => {
    setDraftReasons(prev => prev ? prev.filter(r => r.key !== key) : prev);
    markDirty();
  };
  const addReason = (side: 'candidate' | 'company') => {
    setDraftReasons(prev => {
      if (!prev) return prev;
      const count = prev.filter(r => r.side === side).length;
      return [...prev, { key: `new-${newReasonCounter.current++}`, side, label: 'Новая причина', order_index: count, is_system: false }];
    });
    markDirty();
  };

  const reseedFromServer = useCallback(() => {
    setDirty(false);
    setError(null);
    if (serverStages) setDraftStages(serverStages.map(s => ({ stage_key: s.stage_key, label: s.label, is_terminal: s.is_terminal })));
    if (serverReasons) setDraftReasons(serverReasons.map(r => ({
      key: r.id, id: r.id, side: r.side === 'company' ? 'company' : 'candidate',
      label: r.label, order_index: r.order_index ?? 0, is_system: !!(r as RejectReasonOut).is_system,
    })));
  }, [serverStages, serverReasons]);

  const handleSave = useCallback(async () => {
    if (!draftStages || !serverStages) return;
    if (draftStages.some(s => !s.label.trim()) || (isDefault && draftReasons && draftReasons.some(r => !r.label.trim()))) {
      setError('Название этапа или причины не может быть пустым');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await applyStageDiff(draftStages, serverStages, stageBasePath);
      if (isDefault && draftReasons && serverReasons) {
        await applyReasonDiff(draftReasons, serverReasons);
        await queryClient.invalidateQueries({ queryKey: ['settings', 'reject-reasons'] });
        await queryClient.invalidateQueries({ queryKey: ['settings', 'default-funnel'] });
      } else {
        await queryClient.invalidateQueries({ queryKey: ['settings', 'funnel-templates', selected, 'stages'] });
      }
      setDirty(false);
    } catch (e: any) {
      const error = e as ApiError;
      setError(error.error?.message || 'Не удалось сохранить изменения');
    } finally {
      setSaving(false);
    }
  }, [draftStages, draftReasons, serverStages, serverReasons, stageBasePath, isDefault, selected, queryClient]);

  // --- Управление шаблонами (метаданные — немедленно; блокируем при несохранённых правках этапов) ---
  const selectTemplate = (id: string) => {
    if (dirty || id === selected) return;
    setSelected(id);
  };
  const createTemplate = async () => {
    if (dirty) return;
    try {
      const res = await api.post('/settings/funnel-templates', { name: 'Новый шаблон' });
      await queryClient.invalidateQueries({ queryKey: ['settings', 'funnel-templates'] });
      setSelected(res.data.id);
    } catch (e: any) {
      const error = e as ApiError;
      setError(error.error?.message || 'Не удалось создать шаблон');
    }
  };
  const renameTemplate = async (id: string, name: string) => {
    const trimmed = name.trim().substring(0, 60);
    if (!trimmed) return;
    try {
      await api.patch(`/settings/funnel-templates/${id}`, { name: trimmed });
      await queryClient.invalidateQueries({ queryKey: ['settings', 'funnel-templates'] });
    } catch (e: any) {
      const error = e as ApiError;
      setError(error.error?.message || 'Не удалось переименовать шаблон');
    }
  };
  const deleteTemplate = async (id: string) => {
    try {
      await api.delete(`/settings/funnel-templates/${id}`);
      await queryClient.invalidateQueries({ queryKey: ['settings', 'funnel-templates'] });
      setSelected('default');
      setDirty(false);
    } catch (e: any) {
      const error = e as ApiError;
      setError(error.error?.message || 'Не удалось удалить шаблон');
    }
  };

  if (stagesLoading || (isDefault && reasonsLoading) || !draftStages) {
    return <div className="set-content-inner"><div>Загрузка...</div></div>;
  }

  const selectedTemplate = templates?.find(t => t.id === selected);
  const candidateReasons = (draftReasons || []).filter(r => r.side === 'candidate');
  const companyReasons = (draftReasons || []).filter(r => r.side === 'company');

  const renderReasonChips = (reasonsList: ReasonDraft[], side: 'candidate' | 'company') => (
    <div className="reason-chips">
      {reasonsList.map((reason) => (
        <span key={reason.key} className={`reason-chip reason-chip-${side === 'candidate' ? 'cand' : 'co'}`}>
          <span className={`r-bullet ${side === 'company' ? 'co' : ''}`} />
          <input className="reason-chip-input" value={reason.label} size={Math.max(reason.label.length, 4)}
            onChange={readOnly ? undefined : (e) => renameReason(reason.key, e.target.value)}
            disabled={readOnly} />
          {reason.is_system ? (
            <span className="reason-chip-lock" title="Системная причина — нельзя удалить"><Icon name="lock" size={11} /></span>
          ) : !readOnly ? (
            <button className="reason-chip-x" aria-label="Удалить" onClick={() => deleteReason(reason.key)}><Icon name="x" size={11} /></button>
          ) : null}
        </span>
      ))}
      {!readOnly && <button className="reason-chip-add" onClick={() => addReason(side)}><Icon name="plus" size={12} />Добавить</button>}
    </div>
  );

  return (
    <div className="set-content-inner">
      <PageHead
        title="Воронки и шаблоны"
        subtitle="«По умолчанию» применяется к новым вакансиям. Остальные шаблоны — пресеты для выбора в форме. Изменения этапов вступают в силу по кнопке «Сохранить изменения»"
        dirty={dirty && !readOnly}
        onSave={readOnly ? undefined : handleSave}
        onDiscard={dirty && !readOnly ? reseedFromServer : undefined}
        saving={saving}
      />

      {error && <div className="error-banner" role="alert">{error}</div>}

      <div className="tpl-switch">
        {[{ id: 'default', name: 'По умолчанию' }, ...(templates || [])].map(t => (
          <button
            key={t.id}
            className={`tpl-chip ${selected === t.id ? 'active' : ''}`}
            disabled={dirty && selected !== t.id}
            title={dirty && selected !== t.id ? 'Сначала сохраните или отмените изменения' : undefined}
            onClick={() => selectTemplate(t.id)}
          >
            {t.name}
          </button>
        ))}
        <button className="tpl-add" disabled={dirty || readOnly} onClick={readOnly ? undefined : createTemplate} title={readOnly ? 'Только просмотр' : (dirty ? 'Сначала сохраните или отмените изменения' : undefined)}>
          <Icon name="plus" size={12} /> Шаблон
        </button>
      </div>

      {!isDefault && selectedTemplate && (
        <div className="tpl-bar">
          <input
            className="tpl-name"
            defaultValue={selectedTemplate.name}
            key={`${selectedTemplate.id}-${selectedTemplate.name}`}
            onBlur={(e) => { if (e.target.value.trim() && e.target.value !== selectedTemplate.name) renameTemplate(selectedTemplate.id, e.target.value); }}
          />
          <button className="btn btn-secondary btn-sm" disabled={dirty || readOnly} onClick={readOnly ? undefined : () => deleteTemplate(selectedTemplate.id)}>
            Удалить шаблон
          </button>
        </div>
      )}

      <Card
        title="Этапы воронки"
        desc="Используйте стрелки ▲▼ чтобы менять порядок. Первый и финальные этапы закреплены."
      >
        <div className="funnel-editor">
          {draftStages.map((stage, idx) => {
            const type = deriveStageType(stage, idx);
            const stageType = FUNNEL_STAGE_TYPES[type] || MIDDLE_FALLBACK;
            const isFinal = type === 'finalOk' || type === 'finalBad';
            const isFirst = idx === 0;
            const isProtected = PROTECTED_STAGE_KEYS.has(stage.stage_key) || isFirst || isFinal;

            return (
              <div key={stage.stage_key} className={`fn-stage ${isFinal ? 'fn-final' : ''}`}>
                <div className="nv-fn-arrows">
                  <button className="nv-fn-arr" disabled={isProtected || idx <= 1 || readOnly} title={readOnly ? 'Только просмотр' : (isProtected ? 'Этап зафиксирован' : 'Выше')} onClick={readOnly ? undefined : () => moveStage(idx, -1)}>▲</button>
                  <button className="nv-fn-arr" disabled={isProtected || idx >= draftStages.length - 3 || readOnly} title={readOnly ? 'Только просмотр' : (isProtected ? 'Этап зафиксирован' : 'Ниже')} onClick={readOnly ? undefined : () => moveStage(idx, 1)}>▼</button>
                </div>
                <div className="fn-num">{idx + 1}</div>
                <div className="fn-body">
                  <div className="fn-row1">
                    <input className="fn-name" value={stage.label} onChange={readOnly ? undefined : (e) => renameStage(idx, e.target.value)} disabled={isProtected || readOnly} />
                    <span className="stage-type-pill" style={{ background: stageType.bg, color: stageType.fg }}>
                      <span className="st-dot" style={{ background: stageType.dot }} />
                      {stageType.label}
                    </span>
                    {isProtected && (
                      <span className="nv-locked-pill" title="Зафиксирован"><Icon name="lock" size={11} />закреплён</span>
                    )}
                  </div>
                  <div className="fn-desc">{stageDescription(stage.stage_key, type)}</div>
                </div>
                <button className="row-icon-btn" disabled={isProtected || readOnly} onClick={readOnly ? undefined : () => deleteStage(idx)} title={readOnly ? 'Только просмотр' : (isProtected ? 'Этап нельзя удалить' : 'Удалить этап')}>
                  <Icon name="x" size={14} />
                </button>
              </div>
            );
          })}
          <button className="fn-add" disabled={readOnly} onClick={readOnly ? undefined : addStage}><Icon name="plus" size={14} />Добавить этап</button>
        </div>
      </Card>

      {isDefault && (
        <div className="form-grid form-grid-2 reason-grid">
          <Card title="Причины отказа от кандидата" desc="Видны при нажатии «Отклонить» в карточке кандидата">
            {renderReasonChips(candidateReasons, 'candidate')}
          </Card>
          <Card title="Причины отказа со стороны компании" desc="Используются в Аналитике (отчёт «Причины отказов»)">
            {renderReasonChips(companyReasons, 'company')}
          </Card>
        </div>
      )}
    </div>
  );
}
