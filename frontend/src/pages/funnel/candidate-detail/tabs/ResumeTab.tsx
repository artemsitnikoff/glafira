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

  function handleUploadClick() {
    fileInputRef.current?.click();
  }

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
    <div className="tab-content">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: '600' }}>Резюме</h2>
        <button
          className="candidate-toolbar__btn candidate-toolbar__btn--primary"
          onClick={handleUploadClick}
          disabled={uploadMutation.isPending}
        >
          <Icon name={uploadMutation.isPending ? "loader" : "upload"} size={16} />
          Загрузить новое резюме
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx"
          onChange={handleFileChange}
          style={{ display: 'none' }}
        />
      </div>

      {/* Experience */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: '16px', fontWeight: '600' }}>Опыт работы</h3>
        {candidate.experience && candidate.experience.length > 0 ? (
          <div>
            {candidate.experience.map((exp: any, index: number) => (
              <div key={index} className="experience-item">
                <div className="experience-item__header">
                  <h4 className="experience-item__title">{exp.position}</h4>
                  <p className="experience-item__company">{exp.company}</p>
                  <p className="experience-item__period">
                    {exp.period || 'Период не указан'}
                  </p>
                </div>
                {exp.description && (
                  <p className="experience-item__description">{exp.description}</p>
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
      </div>

      {/* Skills */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h3 style={{ margin: '0 0 var(--space-2) 0', fontSize: '16px', fontWeight: '600' }}>Навыки</h3>
        {candidate.skills && candidate.skills.length > 0 ? (
          <div className="chips-container">
            {candidate.skills.map((skill: any, index: number) => (
              <span key={index} className="chip">
                {skill}
              </span>
            ))}
          </div>
        ) : (
          <p style={{ color: 'var(--fg-3)' }}>Навыки не указаны</p>
        )}
      </div>

      {/* Tags */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h3 style={{ margin: '0 0 var(--space-2) 0', fontSize: '16px', fontWeight: '600' }}>Теги</h3>
        {candidate.tags && candidate.tags.length > 0 ? (
          <div className="chips-container">
            {candidate.tags.map((tag: any, index: number) => (
              <span key={index} className="chip" style={{ background: 'var(--brand-accent)', color: 'white' }}>
                {tag.name}
              </span>
            ))}
          </div>
        ) : (
          <p style={{ color: 'var(--fg-3)' }}>Теги не указаны</p>
        )}
      </div>

      {/* Resume Summary */}
      {candidate.resume_summary && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <h3 style={{ margin: '0 0 var(--space-2) 0', fontSize: '16px', fontWeight: '600' }}>Краткое описание</h3>
          <p style={{ color: 'var(--fg-2)', lineHeight: '1.5' }}>{candidate.resume_summary}</p>
        </div>
      )}

      {/* Extra */}
      {candidate.extra && (
        <div>
          <h3 style={{ margin: '0 0 var(--space-2) 0', fontSize: '16px', fontWeight: '600' }}>Дополнительная информация</h3>
          <div style={{ color: 'var(--fg-2)', lineHeight: '1.5' }}>
            <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
              {typeof candidate.extra === 'string' ? candidate.extra : JSON.stringify(candidate.extra, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}