import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { components } from '@/api/types';
import { useCandidateDetail } from '@/api/hooks/useCandidateDetail';
import { Button } from '@/components/ui/Button';
import { CandidateLoader } from './CandidateLoader';
import { CandidateHeader } from './CandidateHeader';
import { CandidateToolbar } from './CandidateToolbar';
import { ResumeTab } from './tabs/ResumeTab';
import { EvaluationTab } from './tabs/EvaluationTab';
import { VerificationTab } from './tabs/VerificationTab';
import { ChatTab } from './tabs/ChatTab';
import { DocumentsTab } from './tabs/DocumentsTab';
import { CommentsTab } from './tabs/CommentsTab';
import { AllActionsTab } from './tabs/AllActionsTab';
import './CandidateDetail.css';

type ApplicationRow = components['schemas']['ApplicationRow'];

type Props = {
  application: ApplicationRow | null;
  onClose: () => void;
  isResolving?: boolean;
};

const TABS = [
  { id: 'resume', label: 'Резюме' },
  { id: 'evaluation', label: 'Оценка AI' },
  { id: 'verification', label: 'Верификация' },
  { id: 'chat', label: 'Чат' },
  { id: 'docs', label: 'Документы' },
  { id: 'comments', label: 'Комментарии' },
  { id: 'actions', label: 'Все действия' },
];

export function CandidateDetail({ application, onClose, isResolving }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);

  const activeTab = searchParams.get('tab') || 'resume';

  // Fetch candidate details for tabs that need them (only when we have application)
  const candidateDetailQuery = useCandidateDetail(application?.candidate_id || null);

  // Set active tab
  function setActiveTab(tab: string) {
    setSearchParams(prev => {
      prev.set('tab', tab);
      return prev;
    });
  }

  // Timer loader 850ms on candidateId change (like in etalon)
  useEffect(() => {
    if (application?.candidate_id) {
      setLoading(true);
      const timeout = setTimeout(() => setLoading(false), 850);
      return () => clearTimeout(timeout);
    }
  }, [application?.candidate_id]);

  // Handle Esc key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Show "not found" if we have finished loading but no application found
  if (!isResolving && !application) {
    return (
      <div className="candidate-detail">
        <div className="candidate-detail__loader">
          <p>Кандидат не найден в этой вакансии</p>
          <Button
            onClick={onClose}
            variant="primary"
            style={{ marginTop: 'var(--space-4)' }}
          >
            Назад к воронке
          </Button>
        </div>
      </div>
    );
  }

  // Extract IDs from confirmed application
  const candidateId = application?.candidate_id;
  const applicationId = application?.id;

  const showLoader = isResolving || (!application && candidateDetailQuery.isLoading) || loading;

  return (
    <div className="candidate-detail">
      <CandidateToolbar
        application={application || undefined}
        candidate={candidateDetailQuery.data || undefined}
        onClose={onClose}
        onTabChange={setActiveTab}
      />

      <CandidateHeader
        candidateId={candidateId}
        application={application}
      />

      <div className="cc-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`cc-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="cc-content" style={{ position: 'relative' }}>
        {candidateId && activeTab === 'resume' && <ResumeTab candidateId={candidateId} applicationId={applicationId} onOpenAI={() => setActiveTab('evaluation')} />}
        {candidateId && applicationId && activeTab === 'evaluation' && <EvaluationTab candidateId={candidateId} applicationId={applicationId} />}
        {candidateId && activeTab === 'verification' && <VerificationTab candidateId={candidateId} />}
        {candidateId && activeTab === 'chat' && <ChatTab candidateId={candidateId} />}
        {candidateId && activeTab === 'docs' && <DocumentsTab candidateId={candidateId} />}
        {candidateId && activeTab === 'comments' && <CommentsTab candidateId={candidateId} />}
        {candidateId && activeTab === 'actions' && <AllActionsTab candidateId={candidateId} />}

        {showLoader && (
          <div className="cd-loading" style={{
            position: 'absolute',
            inset: 0,
            background: 'rgba(255,255,255,.92)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            animation: 'cdLoadFade 240ms',
            zIndex: 10
          }}>
            <CandidateLoader />
          </div>
        )}
      </div>
    </div>
  );
}