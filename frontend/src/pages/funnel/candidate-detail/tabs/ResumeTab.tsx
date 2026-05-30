import { useRef } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useCandidateDetail } from '@/api/hooks/useCandidateDetail';
import { useEvaluation } from '@/api/hooks/useEvaluation';
import { useUploadDocument } from '@/api/mutations/candidateDetail';
import { AIVerdictCard } from '@/components/candidates/AIVerdictCard';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
  applicationId?: string;
  onOpenAI?: () => void;
};

export function ResumeTab({ candidateId, candidate: candidateProps, fromPool, applicationId, onOpenAI }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const actualCandidateId = candidateId || candidateProps?.id;

  // If candidate is passed as prop (fromPool), use it; otherwise fetch
  const { data: candidateFromApi, isLoading } = useCandidateDetail(
    fromPool ? null : actualCandidateId
  );
  const candidate = fromPool ? candidateProps : candidateFromApi;

  // Get evaluation for AI verdict card
  const { data: evaluation } = useEvaluation(actualCandidateId, applicationId);

  const uploadMutation = useUploadDocument(actualCandidateId);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate([file, 'resume']);
    }
    // Clear input для повторной загрузки того же файла
    e.target.value = '';
  }

  if (isLoading) {
    return (
      <div className="tab-content">
        <Icon name="loader" size={24} />
        <p>Загружается...</p>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div className="tab-content">
        <div className="empty-state">
          <Icon name="user" size={48} className="empty-state__icon" />
          <p className="empty-state__text">Данные кандидата не найдены</p>
        </div>
      </div>
    );
  }

  return (
    <div className="resume-single">
      {/* Hidden upload input - preserve upload functionality */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.doc,.docx"
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />

      {/* AI Verdict Card */}
      {evaluation && <AIVerdictCard evaluation={evaluation} onOpenAI={onOpenAI} />}

      {candidate.experience && candidate.experience.length > 0 && (
        <>
          <h3 className="cc-sec-title">Опыт работы</h3>
          {candidate.experience.map((exp: any, index: number) => (
            <div key={index} className="job">
              <div className="job-header">
                <div>
                  <div className="job-title">{exp.position}</div>
                  <div className="job-co">{exp.company}</div>
                </div>
                <div className="job-period">{exp.period}</div>
              </div>
              {exp.description && (
                <div className="job-desc">
                  {exp.description.split('\n\n').filter((para: string) => para.trim()).map((paragraph: string, pIndex: number) => (
                    <p key={pIndex} className="job-desc-p">{paragraph.trim()}</p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </>
      )}

      {candidate.skills && candidate.skills.length > 0 && (
        <>
          <h3 className="cc-sec-title">Навыки</h3>
          <div className="skill-row">
            {candidate.skills.map((skill: any, index: number) => (
              <span key={index} className="skill-chip">
                {skill}
              </span>
            ))}
          </div>
        </>
      )}

      {candidate.education && candidate.education.length > 0 && (
        <>
          <h3 className="cc-sec-title">Образование</h3>
          {candidate.education.map((edu: any, index: number) => (
            <div key={index} className="edu-row">
              <div>
                <div className="job-title">{edu.institution}</div>
                <div className="job-co">{edu.specialty}</div>
              </div>
              <div className="job-period">{edu.years}</div>
            </div>
          ))}
        </>
      )}

      {candidate.extra && candidate.extra.languages && candidate.extra.languages.length > 0 && (
        <>
          <h3 className="cc-sec-title">Дополнительно</h3>
          <div className="extra-grid">
            <div><span className="extra-k">Языки:</span> {candidate.extra.languages.join(' · ')}</div>
          </div>
        </>
      )}
    </div>
  );
}