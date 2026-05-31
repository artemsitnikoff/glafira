import { Icon } from '@/components/ui/Icon';
import { formatSalary } from '@/lib/format';
import { useCandidateDetail } from '@/api/hooks/useCandidateDetail';
import type { ApplicationRow } from '@/api/aliases';
import { MessIconRound } from '@/components/ui/MessIconRound';
import { messengerChannel } from '@/lib/messengers';
import { ScoreLabel } from '@/components/ui/ScoreLabel';
import { PdnBadge } from '@/components/PdnBadge';

type Props = {
  candidateId: string | null | undefined;
  application: ApplicationRow | null;
};

export function CandidateHeader({ candidateId, application }: Props) {
  const { data: candidate, isLoading } = useCandidateDetail(candidateId || null);

  if (isLoading || !candidate) {
    return (
      <div className="cd-header">
        <div className="candidate-header__avatar">
          <Icon name="user" size={24} />
        </div>
        <div className="candidate-header__info">
          <div style={{ width: '200px', height: '24px', background: 'var(--bg-3)', borderRadius: 'var(--radius-md)' }} />
        </div>
      </div>
    );
  }

  // Real data mapping for context display
  const getSourceInfo = () => {
    const source = candidate?.source || (application as any)?.source || 'hh';

    const sourceMap: Record<string, string> = {
      'hh': 'hh',
      'telegram': 'tg',
      'avito': 'avito',
      'pool': 'pool'
    };
    const sourceClass = sourceMap[source] || 'hh';

    const labelMap: Record<string, string> = {
      'hh': 'Отклик с HeadHunter',
      'telegram': 'Отклик из Telegram',
      'avito': 'Отклик с Авито',
      'pool': 'Из пула'
    };

    return {
      className: `src-pill src-${sourceClass}`,
      label: labelMap[source] || 'Отклик'
    };
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return null;
    try {
      return new Date(dateStr).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' });
    } catch {
      return null;
    }
  };

  const sourceInfo = getSourceInfo();
  const formattedDate = (application as any)?.created_at ? formatDate((application as any).created_at) : null;

  return (
    <div className="cd-header">
      <div className="cd-context">
        {sourceInfo && (
          <span className={sourceInfo.className}>
            {sourceInfo.label}
          </span>
        )}
        {formattedDate && (
          <>
            <span>от {formattedDate}</span>
            <span className="sep">·</span>
          </>
        )}
        {(application as any)?.vacancy_title && (
          <span>{(application as any).vacancy_title}</span>
        )}
        {candidate.city && (
          <>
            <span className="sep">·</span>
            <span>{candidate.city}</span>
          </>
        )}
      </div>

      <div className="cd-h-main">
        <div className="cd-h-left">
          <div className="cd-name-row">
            <h1 className="cd-name">{candidate.full_name}</h1>
            {candidate.has_pdn && <PdnBadge size="md" />}
            {candidate.ai_score && <ScoreLabel value={candidate.ai_score} size="lg" />}
          </div>
          <div className="cd-exp-line">
            {/* Стаж на последнем месте · компания (эталон). last_tenure вычислен на беке
                из самой свежей записи опыта (experience[0] не годится — порядок не хронологический). */}
            {candidate.last_company && (
              <>
                {(candidate as any).last_tenure && `${(candidate as any).last_tenure} · `}
                {candidate.last_company}
              </>
            )}
          </div>
          <div className="cd-salary-line">
            <span className="cd-salary t-mono">
              {candidate.salary_expectation ? formatSalary(candidate.salary_expectation, candidate.currency) : '—'}
            </span>
            <span className="cd-salary-label">ожидания</span>
          </div>
          <div className="cd-tags-row">
            <button className="tag-add">+ Добавить тег</button>
          </div>
        </div>

        <div className="cd-contact-box">
          <div className="cb-row">
            <span className="cb-label">Телефон:</span>
            <span className="t-mono cb-strong">{candidate.phone || 'Не указан'}</span>
            <div className="mess-icons-row">
              {candidate.messengers?.map((m: any, i: number) => {
                const ch = messengerChannel(m); // messengers: строки (seed) ИЛИ {type,url} (форма)
                return <MessIconRound key={`${ch}-${i}`} channel={ch} size="sm" />;
              })}
            </div>
          </div>
          <div className="cb-row">
            <span className="cb-label">Город:</span>
            <span>{candidate.city || 'Не указан'}</span>
          </div>
          <div className="cb-row">
            <span className="cb-label">E-mail:</span>
            <span>{candidate.email || 'Не указан'}</span>
          </div>
        </div>
      </div>
    </div>
  );
}