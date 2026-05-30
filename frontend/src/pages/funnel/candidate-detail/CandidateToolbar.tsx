import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useParams } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import type { ApplicationRow, Candidate } from '@/api/aliases';
import { useMoveApplication, useRejectApplication, useRestoreApplication } from '@/api/mutations/applications';
import { useRequestConsent } from '@/api/mutations/candidateDetail';
import { useVacancyStages } from '@/api/hooks/useVacancyStages';
import { useRejectReasons } from '@/api/hooks/useRejectReasons';

type Props = {
  application?: ApplicationRow;
  candidate?: Candidate;
  fromPool?: boolean;
  onClose: () => void;
  onTabChange?: (tab: string) => void;
  vacancyId?: string;
};

type RejectReason = {
  id: string;
  side: string;
  label: string;
};

export function CandidateToolbar({ application, candidate, fromPool, onClose, onTabChange, vacancyId: vacancyIdProp }: Props) {
  const navigate = useNavigate();
  const { id: routeVacancyId } = useParams();
  const vacancyId = vacancyIdProp || routeVacancyId;
  const [movePopoverOpen, setMovePopoverOpen] = useState(false);
  const [rejectPopoverOpen, setRejectPopoverOpen] = useState(false);
  const [movePopoverPosition, setMovePopoverPosition] = useState<{ top: number; left: number } | null>(null);
  const [rejectPopoverPosition, setRejectPopoverPosition] = useState<{ top: number; left: number } | null>(null);

  const moveRef = useRef<HTMLDivElement>(null);
  const rejectRef = useRef<HTMLDivElement>(null);
  const moveBtnRef = useRef<HTMLButtonElement>(null);
  const rejectBtnRef = useRef<HTMLButtonElement>(null);

  const isHired = application?.stage === 'hired';
  const isRejected = application?.stage === 'rejected';

  // Этапы воронки + причины отказа — те же хуки, что в BulkActionBar (грузятся на маунте,
  // данные готовы до открытия попапа). vacancyId приходит пропом из воронки.
  const { data: stages } = useVacancyStages(vacancyId || '');
  const { data: rejectReasons } = useRejectReasons();

  const moveMutation = useMoveApplication(vacancyId);
  const rejectMutation = useRejectApplication(vacancyId);
  const restoreMutation = useRestoreApplication(vacancyId);
  const consentMutation = useRequestConsent(candidate?.id || '');

  // Calculate popover position
  function calculatePopoverPosition(btnRef: React.RefObject<HTMLButtonElement>) {
    if (!btnRef.current) return null;

    const rect = btnRef.current.getBoundingClientRect();
    return {
      top: rect.bottom + 6,
      left: rect.left
    };
  }

  // Open move popover with positioning
  function openMovePopover() {
    const position = calculatePopoverPosition(moveBtnRef);
    if (position) {
      setMovePopoverPosition(position);
      setMovePopoverOpen(true);
    }
  }

  // Open reject popover with positioning
  function openRejectPopover() {
    const position = calculatePopoverPosition(rejectBtnRef);
    if (position) {
      setRejectPopoverPosition(position);
      setRejectPopoverOpen(true);
    }
  }

  // Close popover on outside click, scroll, and resize
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (moveRef.current && !moveRef.current.contains(event.target as Node)) {
        setMovePopoverOpen(false);
        setMovePopoverPosition(null);
      }
      if (rejectRef.current && !rejectRef.current.contains(event.target as Node)) {
        setRejectPopoverOpen(false);
        setRejectPopoverPosition(null);
      }
    }

    function handleScrollOrResize() {
      if (movePopoverOpen) {
        setMovePopoverOpen(false);
        setMovePopoverPosition(null);
      }
      if (rejectPopoverOpen) {
        setRejectPopoverOpen(false);
        setRejectPopoverPosition(null);
      }
    }

    if (movePopoverOpen || rejectPopoverOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      window.addEventListener('scroll', handleScrollOrResize, true);
      window.addEventListener('resize', handleScrollOrResize);

      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
        window.removeEventListener('scroll', handleScrollOrResize, true);
        window.removeEventListener('resize', handleScrollOrResize);
      };
    }
  }, [movePopoverOpen, rejectPopoverOpen]);

  function handleMoveToStage(stageKey: string) {
    if (!application) return;

    // Не двигать на текущий этап
    if (stageKey === application.stage) {
      setMovePopoverOpen(false);
      setMovePopoverPosition(null);
      return;
    }

    moveMutation.mutate({
      id: application.id,
      data: { to_stage: stageKey }
    });
    setMovePopoverOpen(false);
    setMovePopoverPosition(null);
  }

  function handleRejectWithReason(reason: RejectReason) {
    if (!application) return;

    rejectMutation.mutate({
      id: application.id,
      data: { reason: reason.label, side: reason.side }
    });
    setRejectPopoverOpen(false);
    setRejectPopoverPosition(null);
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

  // Render portaled popups
  const movePopup = movePopoverOpen && !isHired && movePopoverPosition && createPortal(
    <div className="cnd-funnel-wrap" style={{ position: 'fixed', top: 0, left: 0, width: 0, height: 0, zIndex: 2147483000 }}>
      <div className="cand-detail">
        <>
          <div
            className="cd-pop-backdrop"
            onClick={() => {
              setMovePopoverOpen(false);
              setMovePopoverPosition(null);
            }}
          />
          <div
            ref={moveRef}
            className="cd-move-pop"
            role="menu"
            style={{
              position: 'fixed',
              top: movePopoverPosition.top,
              left: movePopoverPosition.left,
              zIndex: 1000
            }}
          >
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
      </div>
    </div>,
    document.body
  );

  const rejectPopup = rejectPopoverOpen && rejectPopoverPosition && createPortal(
    <div className="cnd-funnel-wrap" style={{ position: 'fixed', top: 0, left: 0, width: 0, height: 0, zIndex: 2147483000 }}>
      <div className="cand-detail">
        <>
          <div
            className="cd-pop-backdrop"
            onClick={() => {
              setRejectPopoverOpen(false);
              setRejectPopoverPosition(null);
            }}
          />
          <div
            ref={rejectRef}
            className="cd-move-pop cd-reject-pop"
            role="menu"
            style={{
              position: 'fixed',
              top: rejectPopoverPosition.top,
              left: rejectPopoverPosition.left,
              zIndex: 1000
            }}
          >
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
      </div>
    </div>,
    document.body
  );

  return (
    <>
      {movePopup}
      {rejectPopup}
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
            <button
              ref={moveBtnRef}
              className="btn btn-success btn-sm"
              onClick={openMovePopover}
            >
              <Icon name="arrow-right" size={14} />
              Перевести
              <Icon name="chevron-down" size={12} />
            </button>
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
          <button
            ref={rejectBtnRef}
            className="btn btn-secondary btn-sm"
            onClick={openRejectPopover}
          >
            <Icon name="x" size={14} />
            Отклонить
            <Icon name="chevron-down" size={12} />
          </button>

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
    </>
  );
}