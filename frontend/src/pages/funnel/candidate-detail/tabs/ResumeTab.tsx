import { useRef } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useCandidateDetail } from '@/api/hooks/useCandidateDetail';
import { useUploadDocument } from '@/api/mutations/candidateDetail';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
};

export function ResumeTab({ candidateId, candidate: candidateProps, fromPool }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const actualCandidateId = candidateId || candidateProps?.id;

  // If candidate is passed as prop (fromPool), use it; otherwise fetch
  const { data: candidateFromApi, isLoading } = useCandidateDetail(
    fromPool ? null : actualCandidateId
  );
  const candidate = fromPool ? candidateProps : candidateFromApi;

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

      <h3 className="cc-sec-title">Опыт работы</h3>
      {candidate.experience && candidate.experience.length > 0 ? (
        <div>
          {candidate.experience.map((exp: any, index: number) => (
            <div key={index} className="job">
              <div className="job-header">
                <div>
                  <div className="job-title">{exp.position || 'Должность не указана'}</div>
                  <div className="job-co">{exp.company || 'Компания не указана'}</div>
                </div>
                <div className="job-period">{exp.period || 'Период не указан'}</div>
              </div>
              {exp.description && (
                <div className="job-desc">{exp.description}</div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <Icon name="briefcase" size={24} className="empty-state__icon" />
          <p className="empty-state__text">Опыт работы не указан</p>
        </div>
      )}

      <h3 className="cc-sec-title">Навыки</h3>
      {candidate.skills && candidate.skills.length > 0 ? (
        <div className="skill-row">
          {candidate.skills.map((skill: any, index: number) => (
            <span key={index} className="skill-chip">
              {skill}
            </span>
          ))}
        </div>
      ) : (
        <p style={{ color: 'var(--fg-3)', margin: '8px 0' }}>Навыки не указаны</p>
      )}

      {candidate.education && candidate.education.length > 0 && (
        <>
          <h3 className="cc-sec-title">Образование</h3>
          {candidate.education.map((edu: any, index: number) => (
            <div key={index} className="edu-row">
              <div>
                <div className="job-title">{edu.institution || 'Учебное заведение'}</div>
                <div className="job-co">{edu.specialization || edu.degree || 'Специальность'}</div>
              </div>
              <div className="job-period">{edu.period || edu.year || 'Год не указан'}</div>
            </div>
          ))}
        </>
      )}

      {candidate.extra && (
        <>
          <h3 className="cc-sec-title">Дополнительно</h3>
          <div className="extra-grid">
            {typeof candidate.extra === 'object' ? (
              Object.entries(candidate.extra).map(([key, value]: [string, any]) => (
                <div key={key}>
                  <span className="extra-k">{key}:</span> {String(value)}
                </div>
              ))
            ) : (
              <div>{String(candidate.extra)}</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}