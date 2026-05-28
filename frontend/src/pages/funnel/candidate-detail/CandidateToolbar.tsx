import { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { Button } from '@/components/ui/Button';
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
  id: string;
  name: string;
  order: number;
  is_terminal: boolean;
};

type RejectReason = {
  id: string;
  name: string;
  side: 'candidate' | 'company';
};

export function CandidateToolbar({ application, candidate, fromPool, onClose, onTabChange }: Props) {
  const navigate = useNavigate();
  const { vacancyId } = useParams();
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
      const response = await api.get(`/api/v1/vacancies/${vacancyId}/stages`);
      return response.data as Stage[];
    },
    enabled: !!vacancyId && movePopoverOpen,
  });

  // Fetch reject reasons
  const { data: rejectReasons } = useQuery({
    queryKey: ['settings', 'reject-reasons'],
    queryFn: async () => {
      const response = await api.get('/api/v1/settings/reject-reasons');
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

  function handleMoveToStage(stageId: string) {
    if (!application) return;

    moveMutation.mutate({
      id: application.id,
      data: { to_stage: stageId }
    });
    setMovePopoverOpen(false);
  }

  function handleRejectWithReason(reasonId: string) {
    if (!application) return;

    rejectMutation.mutate({
      id: application.id,
      data: { reason: reasonId, side: 'company' }
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

  // Group reject reasons by side
  const candidateReasons = rejectReasons?.filter(r => r.side === 'candidate') || [];
  const companyReasons = rejectReasons?.filter(r => r.side === 'company') || [];

  // fromPool mode - actions are in header, return null
  if (fromPool) {
    return null;
  }

  return (
    <div className="candidate-toolbar">
      <div className="toolbar-actions">
        {/* Move/Create Employee Button */}
        {!isRejected && (
          <div className="toolbar-dropdown" ref={moveRef}>
            {isHired ? (
              <Button
                variant="success"
                size="sm"
                onClick={handleCreateEmployee}
              >
                Создать сотрудника
              </Button>
            ) : (
              <Button
                variant="success"
                size="sm"
                onClick={() => setMovePopoverOpen(!movePopoverOpen)}
              >
                Перевести
                <Icon name="chevron-down" size={14} />
              </Button>
            )}

            {movePopoverOpen && !isHired && (
              <div className="popover">
                <div className="popover-content">
                  {availableStages.map(stage => (
                    <button
                      key={stage.id}
                      className="popover-item"
                      onClick={() => handleMoveToStage(stage.id)}
                      disabled={moveMutation.isPending}
                    >
                      {stage.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Reject/Restore Button */}
        {isRejected ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRestore}
            disabled={restoreMutation.isPending}
          >
            Восстановить
          </Button>
        ) : (
          <div className="toolbar-dropdown" ref={rejectRef}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setRejectPopoverOpen(!rejectPopoverOpen)}
            >
              Отклонить
              <Icon name="chevron-down" size={14} />
            </Button>

            {rejectPopoverOpen && (
              <div className="popover">
                <div className="popover-content">
                  {candidateReasons.length > 0 && (
                    <div className="popover-section">
                      <div className="popover-section-title">Кандидат</div>
                      {candidateReasons.map(reason => (
                        <button
                          key={reason.id}
                          className="popover-item"
                          onClick={() => handleRejectWithReason(reason.id)}
                          disabled={rejectMutation.isPending}
                        >
                          {reason.name}
                        </button>
                      ))}
                    </div>
                  )}
                  {companyReasons.length > 0 && (
                    <div className="popover-section">
                      <div className="popover-section-title">Компания</div>
                      {companyReasons.map(reason => (
                        <button
                          key={reason.id}
                          className="popover-item"
                          onClick={() => handleRejectWithReason(reason.id)}
                          disabled={rejectMutation.isPending}
                        >
                          {reason.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Comment Button */}
        <Button
          variant="secondary"
          size="sm"
          onClick={handleComment}
        >
          Комментарий
        </Button>

        {/* Consent Button */}
        {application && !application.has_pdn ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRequestConsent}
            disabled={consentMutation.isPending}
            title="Запросить согласие на обработку персональных данных"
          >
            <Icon name="shield" size={16} />
            ПдН
          </Button>
        ) : (
          <div className="consent-badge" title="Согласие на обработку ПдН получено">
            <Icon name="check-circle" size={16} />
            ПдН ✓
          </div>
        )}

        {/* Close Button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          className="toolbar-close"
        >
          <Icon name="x" size={16} />
        </Button>
      </div>
    </div>
  );
}