import React from 'react';
import { Icon } from '@/components/ui/Icon';
import type { components } from '@/api/types';

type VacancyStageCount = components['schemas']['VacancyStageCount'];

type Props = {
  stages: VacancyStageCount[];
  currentStage?: string;
  onStageSelect: (stage: string) => void;
};

export default function StageChipsBar({ stages, currentStage, onStageSelect }: Props) {
  // «Все» = полный total воронки, ВКЛЮЧАЯ «Отказ» и «Нанят» (бэкенд при выборе
  // «Все» отдаёт список со всеми этапами — счётчик должен совпадать со списком).
  const totalCount = stages.reduce((sum, s) => sum + s.count, 0);

  // Separate stages (включая «Добавлен» — туда попадают вручную добавленные кандидаты)
  const workflowStages = stages.filter(s => !s.is_terminal);
  const hiredStage = stages.find(s => s.stage_key === 'hired');
  const rejectedStage = stages.find(s => s.stage_key === 'rejected');

  return (
    <div className="funnel-row">
      {/* All chip */}
      <div
        className={`funnel-chip funnel-all ${currentStage === undefined || currentStage === 'all' ? 'active' : ''}`}
        onClick={() => onStageSelect('all')}
      >
        Все <span className="fc-count">{totalCount}</span>
      </div>

      {/* Workflow stages */}
      {workflowStages.map((stage) => (
        <React.Fragment key={stage.stage_key}>
          <div
            className={`funnel-chip ${currentStage === stage.stage_key ? 'active' : ''}`}
            onClick={() => onStageSelect(stage.stage_key)}
          >
            <span className="stage-dot" style={{ background: stage.color }} />
            {stage.label} <span className="fc-count">{stage.count}</span>
          </div>
          <Icon name="chevR" size={12} className="funnel-arrow" />
        </React.Fragment>
      ))}

      {/* Hired stage */}
      {hiredStage && (
        <div
          className={`funnel-chip funnel-hired ${currentStage === 'hired' ? 'active' : ''}`}
          onClick={() => onStageSelect('hired')}
        >
          <Icon name="check" size={12} />
          {hiredStage.label} <span className="fc-count">{hiredStage.count}</span>
        </div>
      )}

      {/* Gap before rejected */}
      <div className="funnel-gap" />

      {/* Rejected stage */}
      {rejectedStage && (
        <div
          className={`funnel-chip funnel-rejected ${currentStage === 'rejected' ? 'active' : ''}`}
          onClick={() => onStageSelect('rejected')}
        >
          <Icon name="x" size={12} />
          {rejectedStage.label} <span className="fc-count">{rejectedStage.count}</span>
        </div>
      )}
    </div>
  );
}