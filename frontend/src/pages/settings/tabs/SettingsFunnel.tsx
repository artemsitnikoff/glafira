import { useCallback } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useDefaultFunnel } from '@/api/hooks/useDefaultFunnel';
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
  // useReorderRejectReasons
} from '@/api/mutations/settings';
import { PageHead, Card } from '../components/FormComponents';

const FUNNEL_STAGE_TYPES = {
  start: { label: 'Стартовый', dot: '#2A8AF0', bg: '#EAF3FE', fg: '#1865BE' },
  system: { label: 'Системный', dot: '#7E5CF0', bg: '#F0EAFE', fg: '#5C3FBE' },
  middle: { label: 'Промежуточный', dot: '#9AA3AE', bg: '#ECEFF2', fg: '#3A4452' },
  finalOk: { label: 'Финальный · успех', dot: '#16A34A', bg: '#DEF5E5', fg: '#128640' },
  finalBad: { label: 'Финальный · отказ', dot: '#DC4646', bg: '#FCE3E3', fg: '#B83030' },
};

function FunnelEditor() {
  const { data: stages = [], isLoading } = useDefaultFunnel();
  const addStageMutation = useAddDefaultFunnelStage();
  const renameStageMutation = useRenameDefaultFunnelStage();
  const deleteStageMutation = useDeleteDefaultFunnelStage();
  const reorderStagesMutation = useReorderDefaultFunnelStages();

  const handleMove = useCallback((index: number, direction: number) => {
    const newIndex = index + direction;
    if (newIndex < 1 || newIndex >= stages.length - 2) return; // Protect first and last 2 stages

    const newOrder = [...stages];
    [newOrder[index], newOrder[newIndex]] = [newOrder[newIndex], newOrder[index]];

    reorderStagesMutation.mutate({
      stage_keys: newOrder.map(s => s.key)
    });
  }, [stages, reorderStagesMutation]);

  const handleRename = useCallback((stageKey: string, name: string) => {
    renameStageMutation.mutate({
      stageKey,
      data: { name }
    });
  }, [renameStageMutation]);

  const handleDelete = useCallback((stageKey: string) => {
    deleteStageMutation.mutate(stageKey);
  }, [deleteStageMutation]);

  const handleAddStage = useCallback(() => {
    addStageMutation.mutate({
      name: 'Новый этап',
      type: 'middle',
      description: 'Опишите, что происходит на этом этапе.'
    });
  }, [addStageMutation]);

  if (isLoading) {
    return <div>Загрузка...</div>;
  }

  return (
    <div className="funnel-editor">
      {stages.map((stage, idx) => {
        const stageType = FUNNEL_STAGE_TYPES[stage.type];
        const isFinal = stage.type === 'finalOk' || stage.type === 'finalBad';
        const isFirst = idx === 0;
        const isProtected = stage.protected || isFirst || isFinal;

        return (
          <div key={stage.id} className={`fn-stage ${isFinal ? 'fn-final' : ''}`}>
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
                  defaultValue={stage.name}
                  onBlur={(e) => {
                    if (e.target.value !== stage.name) {
                      handleRename(stage.key, e.target.value);
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
              {stage.description && (
                <div className="fn-desc">{stage.description}</div>
              )}
            </div>
            <button
              className="row-icon-btn"
              disabled={isProtected}
              onClick={() => handleDelete(stage.key)}
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
  // const reorderReasonsMutation = useReorderRejectReasons();

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
          Для существующих — используйте тогглы «Применить ко всем активным» при сохранении.
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