import { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import type { ApplicationRow, Candidate } from '@/api/aliases';
import { useMoveApplication, useRejectApplication, useRestoreApplication } from '@/api/mutations/applications';
import { useRequestConsent } from '@/api/mutations/candidateDetail';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

type Props = {
  application?: ApplicationRow;
  candidate?: Candidate;
  fromPool?: boolean;
  onClose: () => void;
  onTabChange?: (tab: string) => void;
};

type Stage = {
  stage_key: string;
  label: string;
  color: string;
  count: number;
  is_terminal: boolean;
};

type RejectReason = {
  id: string;
  side: 'candidate' | 'company';
  label: string;
};

export function CandidateToolbar({ application, candidate, fromPool, onClose, onTabChange }: Props) {
  const navigate = useNavigate();
  const { id: vacancyId } = useParams();
  const [movePopoverOpen, setMovePopoverOpen] = useState(false);
  const [rejectPopoverOpen, setRejectPopoverOpen] = useState(false);

  const moveRef = useRef<HTMLDivElement>(null);
  const rejectRef = useRef<HTMLDivElement>(null);

  const isHired = application?.stage === 'hired';
  const isRejected = application?.stage === 'rejected';

  // Fetch stages for move popover
  const { data: stages } = useQuery({
    queryKey: ['vacancies', vacancyId, 'stages'],
    queryFn: async () => {
      const response = await api.get(`/vacancies/${vacancyId}/stages`);
      return response.data as Stage[];
    },
    enabled: !!vacancyId && movePopoverOpen,
  });

  // Fetch reject reasons
  const { data: rejectReasons } = useQuery({
    queryKey: ['settings', 'reject-reasons'],
    queryFn: async () => {
      const response = await api.get('/settings/reject-reasons');
      return response.data as RejectReason[];
    },
    enabled: rejectPopoverOpen,
  });

  const moveMutation = useMoveApplication(vacancyId);
  const rejectMutation = useRejectApplication(vacancyId);
  const restoreMutation = useRestoreApplication(vacancyId);
  const consentMutation = useRequestConsent(candidate?.id || '');

  // Close popover on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (moveRef.current && !moveRef.current.contains(event.target as Node)) {
        setMovePopoverOpen(false);
      }
      if (rejectRef.current && !rejectRef.current.contains(event.target as Node)) {
        setRejectPopoverOpen(false);
      }
    }

    if (movePopoverOpen || rejectPopoverOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [movePopoverOpen, rejectPopoverOpen]);

  function handleMoveToStage(stageKey: string) {
    if (!application) return;

    // Не двигать на текущий этап
    if (stageKey === application.stage) {
      setMovePopoverOpen(false);
      return;
    }

    moveMutation.mutate({
      id: application.id,
      data: { to_stage: stageKey }
    });
    setMovePopoverOpen(false);
  }

  function handleRejectWithReason(reason: RejectReason) {
    if (!application) return;

    rejectMutation.mutate({
      id: application.id,
      data: { reason: reason.label, side: reason.side }
    });
    setRejectPopoverOpen(false);
  }

  function handleRestore() {
    if (!application) return;
    restoreMutation.mutate(application.id);
  }

  function handleComment() {
    if (onTabChange) {
      onTabChange('comments');
      // Scroll to textarea after tab switch
      setTimeout(() => {
        const textarea = document.querySelector('.comments-tab textarea');
        textarea?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    }
  }

  function handleRequestConsent() {
    if (!candidate) return;
    consentMutation.mutate({ channel: 'email' });
  }

  function handleCreateEmployee() {
    // Since backend auto-creates employee, navigate to Pulse with search filter
    if (candidate) {
      navigate(`/pulse?status=onboarding&q=${encodeURIComponent(candidate.full_name)}`);
    }
  }

  // Filter non-terminal stages for move popover
  const availableStages = stages?.filter(stage => !stage.is_terminal) || [];
  const curStageIdx = availableStages.findIndex(s => s.stage_key === application?.stage);

  // Group reject reasons by side
  const candidateReasons = rejectReasons?.filter(r => r.side === 'candidate') || [];
  const companyReasons = rejectReasons?.filter(r => r.side === 'company') || [];

  // fromPool mode - actions are in header, return null
  if (fromPool) {
    return null;
  }

  return (
    <div className="cd-toolbar">
      {/* Move/Create Employee Button */}
      {!isRejected && (
        <div className="cd-move-wrap" ref={moveRef}>
          {isHired ? (
            <button className="btn btn-success btn-sm" onClick={handleCreateEmployee}>
              <Icon name="arrow-right" size={14} />
              Создать сотрудника
            </button>
          ) : (
            <button className="btn btn-success btn-sm" onClick={() => setMovePopoverOpen(!movePopoverOpen)}>
              <Icon name="arrow-right" size={14} />
              Перевести
              <Icon name="chevron-down" size={12} />
            </button>
          )}

          {movePopoverOpen && !isHired && (
            <>
              <div className="cd-pop-backdrop" onClick={() => setMovePopoverOpen(false)} />
              <div className="cd-move-pop" role="menu">
                <div className="cd-pop-head">На какой этап?</div>
                {availableStages.map((stage, i) => (
                  <button
                    key={stage.stage_key}
                    className={`cd-pop-item ${stage.stage_key === application?.stage ? 'cur' : ''} ${i === curStageIdx + 1 ? 'next' : ''}`}
                    onClick={() => handleMoveToStage(stage.stage_key)}
                    disabled={moveMutation.isPending}
                  >
                    <span className="stage-dot" style={{ background: stage.color }} />
                    <span className="cd-pop-label">{stage.label}</span>
                    {stage.stage_key === application?.stage && <span className="cd-pop-tag">сейчас</span>}
                    {i === curStageIdx + 1 && <span className="cd-pop-tag cd-pop-tag-next">далее</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Reject/Restore Button */}
      {isRejected ? (
        <button
          className="btn btn-secondary btn-sm"
          onClick={handleRestore}
          disabled={restoreMutation.isPending}
        >
          Восстановить
        </button>
      ) : (
        <div className="cd-move-wrap" ref={rejectRef}>
          <button className="btn btn-secondary btn-sm" onClick={() => setRejectPopoverOpen(!rejectPopoverOpen)}>
            <Icon name="x" size={14} />
            Отклонить
            <Icon name="chevron-down" size={12} />
          </button>

          {rejectPopoverOpen && (
            <>
              <div className="cd-pop-backdrop" onClick={() => setRejectPopoverOpen(false)} />
              <div className="cd-move-pop cd-reject-pop" role="menu">
                <div className="cd-pop-head">Причина отказа</div>
                {candidateReasons.length > 0 && (
                  <>
                    <div className="cd-pop-group">От кандидата</div>
                    {candidateReasons.map(reason => (
                      <button
                        key={reason.id}
                        className="cd-pop-item cd-reject-item"
                        onClick={() => handleRejectWithReason(reason)}
                        disabled={rejectMutation.isPending}
                      >
                        <span className="r-bullet" />
                        <span className="cd-pop-label">{reason.label}</span>
                      </button>
                    ))}
                  </>
                )}
                {companyReasons.length > 0 && (
                  <>
                    <div className="cd-pop-group">Со стороны компании</div>
                    {companyReasons.map(reason => (
                      <button
                        key={reason.id}
                        className="cd-pop-item cd-reject-item"
                        onClick={() => handleRejectWithReason(reason)}
                        disabled={rejectMutation.isPending}
                      >
                        <span className="r-bullet co" />
                        <span className="cd-pop-label">{reason.label}</span>
                      </button>
                    ))}
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Comment Button */}
      <button className="btn btn-secondary btn-sm" onClick={handleComment}>
        <Icon name="message-square" size={14} />
        Комментарий
      </button>

      {/* Consent Button */}
      {application && !application.has_pdn ? (
        <button
          className="btn btn-secondary btn-sm cd-pdn-btn"
          onClick={handleRequestConsent}
          disabled={consentMutation.isPending}
          title="Запросить согласие на обработку персональных данных"
        >
          <Icon name="shield" size={14} />
          ПдН
        </button>
      ) : (
        <span className="cd-pdn-confirmed" title="Согласие на обработку ПдН получено">
          ПдН
          <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
            <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </span>
      )}

      <div style={{ flex: 1 }} />

      {/* Close Button */}
      <button className="icon-btn" onClick={onClose} title="Закрыть">
        <Icon name="x" size={18} />
      </button>
    </div>
  );
}