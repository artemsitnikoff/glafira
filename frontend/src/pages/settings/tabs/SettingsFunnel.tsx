import { useCallback } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useDefaultFunnel, type DefaultFunnelStage } from '@/api/hooks/useDefaultFunnel';
import {
  useAddDefaultFunnelStage,
  useRenameDefaultFunnelStage,
  useDeleteDefaultFunnelStage,
  useReorderDefaultFunnelStages
} from '@/api/mutations/defaultFunnel';
import { useRejectReasons } from '@/api/hooks/useRejectReasons';
import {
  useCreateRejectReason,
  useDeleteRejectReason
} from '@/api/mutations/settings';
import { PageHead, Card } from '../components/FormComponents';

// Защищённые (системные) этапы — зеркало с бэкенда (core/stages.py PROTECTED_STAGE_KEYS).
const PROTECTED_STAGE_KEYS = new Set(['hired', 'rejected', 'added', 'response']);

type StageTypeKey = 'start' | 'system' | 'middle' | 'finalOk' | 'finalBad';

// Цвета пилюль типов этапов — 1:1 с формой вакансии (VacancyFormPage FUNNEL_STAGE_TYPES).
const FUNNEL_STAGE_TYPES: Record<StageTypeKey, { label: string; dot: string; bg: string; fg: string }> = {
  start: { label: 'Стартовый', dot: '#2A8AF0', bg: '#EAF3FE', fg: '#1865BE' },
  system: { label: 'Системный', dot: '#7E5CF0', bg: '#F0EAFE', fg: '#5C3FBE' },
  middle: { label: 'Промежуточный', dot: '#9AA3AE', bg: '#ECEFF2', fg: '#3A4452' },
  finalOk: { label: 'Финальный · успех', dot: '#16A34A', bg: '#DEF5E5', fg: '#128640' },
  finalBad: { label: 'Финальный · отказ', dot: '#DC4646', bg: '#FCE3E3', fg: '#B83030' },
};

const MIDDLE_FALLBACK = FUNNEL_STAGE_TYPES.middle;

// Тип этапа выводится из позиции + is_terminal + stage_key — та же логика, что в форме вакансии.
function deriveStageType(stage: DefaultFunnelStage, index: number): StageTypeKey {
  if (index === 0) return 'start';
  if (stage.is_terminal) {
    return stage.stage_key === 'hired' || stage.label.toLowerCase().includes('нанят')
      ? 'finalOk'
      : 'finalBad';
  }
  if (PROTECTED_STAGE_KEYS.has(stage.stage_key)) return 'system';
  return 'middle';
}

// Описания канонических этапов (как в форме вакансии). Для кастомных — по типу.
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

function FunnelEditor() {
  const { data: stages = [], isLoading } = useDefaultFunnel();
  const addStageMutation = useAddDefaultFunnelStage();
  const renameStageMutation = useRenameDefaultFunnelStage();
  const deleteStageMutation = useDeleteDefaultFunnelStage();
  const reorderStagesMutation = useReorderDefaultFunnelStages();

  const handleMove = useCallback((index: number, direction: number) => {
    const j = index + direction;
    // Нельзя двигать первый этап и два последних финальных (эталонная логика).
    if (j < 1 || j > stages.length - 2) return;
    if (index === 0 || index >= stages.length - 2) return;

    const next = stages.slice();
    [next[index], next[j]] = [next[j], next[index]];

    reorderStagesMutation.mutate({ order: next.map(s => s.stage_key) });
  }, [stages, reorderStagesMutation]);

  const handleRename = useCallback((stageKey: string, label: string) => {
    const trimmed = label.trim().substring(0, 60); // ограничение бэка ≤60
    if (!trimmed) return;
    renameStageMutation.mutate({ stageKey, data: { label: trimmed } });
  }, [renameStageMutation]);

  const handleDelete = useCallback((stageKey: string) => {
    deleteStageMutation.mutate(stageKey);
  }, [deleteStageMutation]);

  const handleAddStage = useCallback(() => {
    addStageMutation.mutate({
      stage_key: `stage_${Date.now()}`,
      label: 'Новый этап',
      order_index: Math.max(stages.length - 2, 1), // перед двумя финальными
      is_terminal: false,
    });
  }, [stages.length, addStageMutation]);

  if (isLoading) {
    return <div>Загрузка...</div>;
  }

  return (
    <div className="funnel-editor">
      {stages.map((stage, idx) => {
        const type = deriveStageType(stage, idx);
        const stageType = FUNNEL_STAGE_TYPES[type] || MIDDLE_FALLBACK;
        const isFinal = type === 'finalOk' || type === 'finalBad';
        const isFirst = idx === 0;
        const isProtected = PROTECTED_STAGE_KEYS.has(stage.stage_key) || isFirst || isFinal;

        return (
          <div key={stage.stage_key} className={`fn-stage ${isFinal ? 'fn-final' : ''}`}>
            <div className="nv-fn-arrows">
              <button
                className="nv-fn-arr"
                disabled={isProtected || idx <= 1}
                title={isProtected ? 'Этап зафиксирован' : 'Выше'}
                onClick={() => handleMove(idx, -1)}
              >
                ▲
              </button>
              <button
                className="nv-fn-arr"
                disabled={isProtected || idx >= stages.length - 3}
                title={isProtected ? 'Этап зафиксирован' : 'Ниже'}
                onClick={() => handleMove(idx, 1)}
              >
                ▼
              </button>
            </div>
            <div className="fn-num">{idx + 1}</div>
            <div className="fn-body">
              <div className="fn-row1">
                <input
                  className="fn-name"
                  defaultValue={stage.label}
                  key={`${stage.stage_key}-${stage.label}`}
                  onBlur={(e) => {
                    if (e.target.value.trim() && e.target.value !== stage.label) {
                      handleRename(stage.stage_key, e.target.value);
                    }
                  }}
                  disabled={isProtected}
                />
                <span
                  className="stage-type-pill"
                  style={{ background: stageType.bg, color: stageType.fg }}
                >
                  <span className="st-dot" style={{ background: stageType.dot }} />
                  {stageType.label}
                </span>
                {isProtected && (
                  <span className="nv-locked-pill" title="Зафиксирован">
                    <Icon name="lock" size={11} />
                    закреплён
                  </span>
                )}
              </div>
              <div className="fn-desc">{stageDescription(stage.stage_key, type)}</div>
            </div>
            <button
              className="row-icon-btn"
              disabled={isProtected}
              onClick={() => handleDelete(stage.stage_key)}
              title={isProtected ? 'Этап нельзя удалить' : 'Удалить этап'}
            >
              <Icon name="x" size={14} />
            </button>
          </div>
        );
      })}

      <button className="fn-add" onClick={handleAddStage}>
        <Icon name="plus" size={14} />
        Добавить этап
      </button>
    </div>
  );
}

function RejectReasons() {
  const { data: reasons = [], isLoading } = useRejectReasons();
  const createReasonMutation = useCreateRejectReason();
  const deleteReasonMutation = useDeleteRejectReason();

  const candidateReasons = reasons.filter(r => r.side === 'candidate');
  const companyReasons = reasons.filter(r => r.side === 'company');

  const handleAddReason = useCallback((side: 'candidate' | 'company') => {
    createReasonMutation.mutate({
      label: 'Новая причина',
      side,
      order_index: side === 'candidate' ? candidateReasons.length : companyReasons.length
    });
  }, [candidateReasons.length, companyReasons.length, createReasonMutation]);

  const handleDeleteReason = useCallback((id: string) => {
    deleteReasonMutation.mutate(id);
  }, [deleteReasonMutation]);

  if (isLoading) {
    return <div>Загрузка...</div>;
  }

  const renderReasonChips = (reasonsList: typeof reasons, side: 'candidate' | 'company') => (
    <div className="reason-chips">
      {reasonsList.map((reason) => (
        <span key={reason.id} className={`reason-chip reason-chip-${side === 'candidate' ? 'cand' : 'co'}`}>
          <span className={`r-bullet ${side === 'company' ? 'co' : ''}`} />
          <span>{reason.label}</span>
          <button
            className="reason-chip-x"
            aria-label="Удалить"
            onClick={() => handleDeleteReason(reason.id)}
          >
            <Icon name="x" size={11} />
          </button>
        </span>
      ))}
      <button
        className="reason-chip-add"
        onClick={() => handleAddReason(side)}
      >
        <Icon name="plus" size={12} />
        Добавить
      </button>
    </div>
  );

  return (
    <div className="form-grid form-grid-2 reason-grid">
      <Card
        title="Причины отказа от кандидата"
        desc="Видны при нажатии «Отклонить» в карточке кандидата"
      >
        {renderReasonChips(candidateReasons, 'candidate')}
      </Card>
      <Card
        title="Причины отказа со стороны компании"
        desc="Используются в Аналитике (отчёт «Причины отказов»)"
      >
        {renderReasonChips(companyReasons, 'company')}
      </Card>
    </div>
  );
}

export function SettingsFunnel() {
  return (
    <div className="set-content-inner">
      <PageHead
        title="Воронка по умолчанию"
        subtitle="Базовый шаблон, который применяется при создании новой вакансии. Воронку можно изменить в любой вакансии после её создания"
      />

      <div className="info-banner">
        <Icon name="sparkle" size={16} />
        <div>
          <b>Это шаблон.</b> Изменения вступают в силу для <i>новых</i> вакансий.
          Существующие вакансии не затрагиваются — у каждой своя воронка.
        </div>
      </div>

      <Card
        title="Этапы воронки"
        desc="Используйте стрелки ▲▼ чтобы менять порядок. Первый и финальные этапы закреплены."
      >
        <FunnelEditor />
      </Card>

      <RejectReasons />
    </div>
  );
}
