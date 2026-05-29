import { useState } from 'react';
import { useBulkMove, useBulkReject } from '@/api/mutations/applications';
import { useVacancyStages } from '@/api/hooks/useVacancyStages';
import { useRejectReasons } from '@/api/hooks/useRejectReasons';

type Props = {
  selectedIds: Set<string>;
  onClearSelection: () => void;
  vacancyId: string;
};

export default function BulkActionBar({ selectedIds, onClearSelection, vacancyId }: Props) {
  const [moveOpen, setMoveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);

  const { data: stages } = useVacancyStages(vacancyId);
  const { data: rejectReasons } = useRejectReasons();

  const bulkMoveMutation = useBulkMove(vacancyId);
  const bulkRejectMutation = useBulkReject(vacancyId);

  const handleMove = async (toStage: string) => {
    try {
      await bulkMoveMutation.mutateAsync({
        application_ids: Array.from(selectedIds),
        to_stage: toStage,
      });
      onClearSelection();
      setMoveOpen(false);
    } catch (error) {
      console.error('Failed to move applications:', error);
    }
  };

  const handleReject = async (reason: string, side: 'candidate' | 'company') => {
    try {
      await bulkRejectMutation.mutateAsync({
        application_ids: Array.from(selectedIds),
        reason,
        side,
      });
      onClearSelection();
      setRejectOpen(false);
    } catch (error) {
      console.error('Failed to reject applications:', error);
    }
  };

  const workflowStages = stages?.filter(s => !s.is_terminal) || [];
  const candidateReasons = rejectReasons?.filter(r => r.side === 'candidate') || [];
  const companyReasons = rejectReasons?.filter(r => r.side === 'company') || [];

  return (
    <div className="bulk-bar">
      <span className="bulk-count">{selectedIds.size} выбрано</span>

      {/* Move dropdown */}
      <div className="cd-move-wrap">
        <button className="btn btn-secondary btn-sm" onClick={() => setMoveOpen(!moveOpen)}>
          Перевести ▾
        </button>

        {moveOpen && (
          <>
            <div className="cd-pop-backdrop" onClick={() => setMoveOpen(false)} />
            <div className="cd-move-pop" role="menu">
              <div className="cd-pop-head">На какой этап?</div>
              {workflowStages.map(stage => (
                <button
                  key={stage.stage_key}
                  className="cd-pop-item"
                  onClick={() => handleMove(stage.stage_key)}
                >
                  <span className="stage-dot" style={{ background: stage.color }} />
                  <span className="cd-pop-label">{stage.label}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Reject dropdown */}
      <div className="cd-move-wrap">
        <button className="btn btn-secondary btn-sm" onClick={() => setRejectOpen(!rejectOpen)}>
          Отклонить ▾
        </button>

        {rejectOpen && (
          <>
            <div className="cd-pop-backdrop" onClick={() => setRejectOpen(false)} />
            <div className="cd-move-pop cd-reject-pop" role="menu">
              <div className="cd-pop-head">Причина отказа</div>

              <div className="cd-pop-group">От кандидата</div>
              {candidateReasons.map(reason => (
                <button
                  key={reason.id}
                  className="cd-pop-item cd-reject-item"
                  onClick={() => handleReject(reason.label, 'candidate')}
                >
                  <span className="r-bullet" />
                  <span className="cd-pop-label">{reason.label}</span>
                </button>
              ))}

              <div className="cd-pop-group">Со стороны компании</div>
              {companyReasons.map(reason => (
                <button
                  key={reason.id}
                  className="cd-pop-item cd-reject-item"
                  onClick={() => handleReject(reason.label, 'company')}
                >
                  <span className="r-bullet co" />
                  <span className="cd-pop-label">{reason.label}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
