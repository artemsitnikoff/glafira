import { useEffect } from 'react';
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
  { id: 'evaluation', label: 'AI-оценка' },
  { id: 'verification', label: 'Верификация' },
  { id: 'chat', label: 'Чат' },
  { id: 'docs', label: 'Документы' },
  { id: 'comments', label: 'Комментарии' },
  { id: 'actions', label: 'Действия' },
];

export function CandidateDetail({ application, onClose, isResolving }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();

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

  // Show loader while application is being resolved or candidate details are loading
  if (isResolving || (!application && candidateDetailQuery.isLoading)) {
    return (
      <div className="candidate-detail">
        <CandidateLoader />
      </div>
    );
  }

  // Show "not found" if we have finished loading but no application found
  if (!application) {
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
  const candidateId = application.candidate_id;
  const applicationId = application.id;

  return (
    <div className="candidate-detail">
      <div className="candidate-detail__header">
        <CandidateHeader
          candidateId={candidateId}
          application={application}
          onClose={onClose}
        />
      </div>

      <div className="candidate-detail__toolbar">
        <CandidateToolbar
          application={application}
          candidate={candidateDetailQuery.data}
          onClose={onClose}
          onTabChange={setActiveTab}
        />
      </div>

      <div className="candidate-detail__tabs">
        <div className="candidate-tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              className={`candidate-tabs__tab ${activeTab === tab.id ? 'candidate-tabs__tab--active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="candidate-detail__content">
        {activeTab === 'resume' && <ResumeTab candidateId={candidateId} />}
        {activeTab === 'evaluation' && <EvaluationTab candidateId={candidateId} applicationId={applicationId} />}
        {activeTab === 'verification' && <VerificationTab candidateId={candidateId} />}
        {activeTab === 'chat' && <ChatTab candidateId={candidateId} />}
        {activeTab === 'docs' && <DocumentsTab candidateId={candidateId} />}
        {activeTab === 'comments' && <CommentsTab candidateId={candidateId} />}
        {activeTab === 'actions' && <AllActionsTab candidateId={candidateId} />}
      </div>
    </div>
  );
}