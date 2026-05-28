import { useState, useEffect } from 'react';
import { useRejectReasons } from '@/api/hooks/useRejectReasons';
import { useCreateRejectReason, useDeleteRejectReason } from '@/api/mutations/settings';
import { Icon } from '@/components/ui/Icon';

type Props = {
  onDirtyChange: (dirty: boolean) => void;
  onSaveHandler: (handler: (() => Promise<void>) | null) => void;
  onDiscardHandler: (handler: (() => void) | null) => void;
};

export function FunnelTab({ onDirtyChange, onSaveHandler, onDiscardHandler }: Props) {
  const { data: rejectReasons, isLoading } = useRejectReasons();
  const createRejectReason = useCreateRejectReason();
  const deleteRejectReason = useDeleteRejectReason();

  const [showAddCandidate, setShowAddCandidate] = useState(false);
  const [showAddCompany, setShowAddCompany] = useState(false);
  const [newCandidateReason, setNewCandidateReason] = useState('');
  const [newCompanyReason, setNewCompanyReason] = useState('');

  // FunnelTab doesn't have persistent dirty state
  useEffect(() => {
    onDirtyChange(false);
    onSaveHandler(null);
    onDiscardHandler(null);
  }, [onDirtyChange, onSaveHandler, onDiscardHandler]);

  const candidateReasons = rejectReasons?.filter(reason => reason.side === 'candidate') || [];
  const companyReasons = rejectReasons?.filter(reason => reason.side === 'company') || [];

  const handleAddCandidateReason = async () => {
    if (newCandidateReason.trim()) {
      await createRejectReason.mutateAsync({
        side: 'candidate',
        label: newCandidateReason.trim(),
        order_index: candidateReasons.length,
      });
      setNewCandidateReason('');
      setShowAddCandidate(false);
    }
  };

  const handleAddCompanyReason = async () => {
    if (newCompanyReason.trim()) {
      await createRejectReason.mutateAsync({
        side: 'company',
        label: newCompanyReason.trim(),
        order_index: companyReasons.length,
      });
      setNewCompanyReason('');
      setShowAddCompany(false);
    }
  };

  const handleDeleteReason = async (reasonId: string, reasonLabel: string) => {
    if (confirm(`Удалить причину отказа "${reasonLabel}"?`)) {
      await deleteRejectReason.mutateAsync(reasonId);
    }
  };

  if (isLoading) {
    return <div className="settings-loading">Загрузка...</div>;
  }

  return (
    <div className="settings-content-inner">
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Причины отказа</h2>
          <p className="settings-card-desc">
            Справочник причин отказа для стандартизации процессов найма.
            Изменения отразятся в воронке и карточках кандидатов.
          </p>
        </div>

        <div className="funnel-sections">
          {/* Candidate Reasons */}
          <div className="funnel-section">
            <h3 className="funnel-section-title">
              <span className="bullet bullet-candidate">●</span>
              По кандидату
            </h3>
            <div className="reasons-grid">
              {candidateReasons.map((reason) => (
                <div key={reason.id} className="reason-chip">
                  <span className="bullet bullet-candidate">●</span>
                  <span className="reason-label">{reason.label}</span>
                  <button
                    className="reason-remove"
                    onClick={() => handleDeleteReason(reason.id, reason.label)}
                    title="Удалить причину"
                  >
                    <Icon name="x" size={12} />
                  </button>
                </div>
              ))}

              {showAddCandidate ? (
                <div className="reason-input">
                  <input
                    type="text"
                    className="form-input form-input-sm"
                    value={newCandidateReason}
                    onChange={(e) => setNewCandidateReason(e.target.value)}
                    placeholder="Введите причину"
                    autoFocus
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        handleAddCandidateReason();
                      } else if (e.key === 'Escape') {
                        setShowAddCandidate(false);
                        setNewCandidateReason('');
                      }
                    }}
                    onBlur={() => {
                      if (!newCandidateReason.trim()) {
                        setShowAddCandidate(false);
                      }
                    }}
                  />
                  <div className="reason-input-actions">
                    <button
                      className="btn btn-ghost btn-xs"
                      onClick={() => {
                        setShowAddCandidate(false);
                        setNewCandidateReason('');
                      }}
                    >
                      <Icon name="x" size={12} />
                    </button>
                    <button
                      className="btn btn-primary btn-xs"
                      onClick={handleAddCandidateReason}
                      disabled={!newCandidateReason.trim()}
                    >
                      <Icon name="check" size={12} />
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  className="reason-add"
                  onClick={() => setShowAddCandidate(true)}
                >
                  <Icon name="plus" size={14} />
                  Добавить
                </button>
              )}
            </div>
          </div>

          {/* Company Reasons */}
          <div className="funnel-section">
            <h3 className="funnel-section-title">
              <span className="bullet bullet-company">●</span>
              Со стороны компании
            </h3>
            <div className="reasons-grid">
              {companyReasons.map((reason) => (
                <div key={reason.id} className="reason-chip">
                  <span className="bullet bullet-company">●</span>
                  <span className="reason-label">{reason.label}</span>
                  <button
                    className="reason-remove"
                    onClick={() => handleDeleteReason(reason.id, reason.label)}
                    title="Удалить причину"
                  >
                    <Icon name="x" size={12} />
                  </button>
                </div>
              ))}

              {showAddCompany ? (
                <div className="reason-input">
                  <input
                    type="text"
                    className="form-input form-input-sm"
                    value={newCompanyReason}
                    onChange={(e) => setNewCompanyReason(e.target.value)}
                    placeholder="Введите причину"
                    autoFocus
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        handleAddCompanyReason();
                      } else if (e.key === 'Escape') {
                        setShowAddCompany(false);
                        setNewCompanyReason('');
                      }
                    }}
                    onBlur={() => {
                      if (!newCompanyReason.trim()) {
                        setShowAddCompany(false);
                      }
                    }}
                  />
                  <div className="reason-input-actions">
                    <button
                      className="btn btn-ghost btn-xs"
                      onClick={() => {
                        setShowAddCompany(false);
                        setNewCompanyReason('');
                      }}
                    >
                      <Icon name="x" size={12} />
                    </button>
                    <button
                      className="btn btn-primary btn-xs"
                      onClick={handleAddCompanyReason}
                      disabled={!newCompanyReason.trim()}
                    >
                      <Icon name="check" size={12} />
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  className="reason-add"
                  onClick={() => setShowAddCompany(true)}
                >
                  <Icon name="plus" size={14} />
                  Добавить
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}