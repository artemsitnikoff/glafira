import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { formatSalaryRange } from '@/lib/format';
import { useCandidateDetail } from '@/api/hooks/useCandidateDetail';
import type { ApplicationRow } from '@/api/aliases';
import { MessIconRound } from '@/components/ui/MessIconRound';
import { messengerChannel } from '@/lib/messengers';
import { ScoreLabel } from '@/components/ui/ScoreLabel';
import { PdnBadge } from '@/components/PdnBadge';
import { CandidateTagPicker } from '@/components/CandidateTagPicker';
import { SOURCE_CONFIG } from '@/lib/source-colors';
import { useAuthStore } from '@/store/authStore';
import { useHabrOpenContacts } from '@/api/mutations/habrIntegration';

type Props = {
  candidateId: string | null | undefined;
  application: ApplicationRow | null;
};

export function CandidateHeader({ candidateId, application }: Props) {
  const { data: candidate, isLoading } = useCandidateDetail(candidateId || null);
  const navigate = useNavigate();
  const userRole = useAuthStore((s) => s.user?.role);
  const isAdmin = userRole === 'admin';
  const openContactsMutation = useHabrOpenContacts();
  const [openContactsError, setOpenContactsError] = useState<string | null>(null);

  function handleOpenContacts() {
    if (!candidateId) return;
    setOpenContactsError(null);
    openContactsMutation.mutate(candidateId, {
      onSuccess: (data) => {
        if (data.merged) {
          // Кандидат слит с существующим дублём — переходим на survivor
          navigate(`/candidates/${data.candidate_id}`);
        }
        // Иначе — кэш инвалидирован в мутации, карточка перезагрузится автоматически
      },
      onError: (err: unknown) => {
        const axiosErr = err as { response?: { data?: { error?: { message?: string } } } };
        const msg = axiosErr?.response?.data?.error?.message;
        setOpenContactsError(msg || 'Не удалось открыть контакты. Проверьте лимит Хабра.');
      },
    });
  }

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
    const source = candidate?.source || 'hh';

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
      'linkedin': 'Отклик из LinkedIn',
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
  // «Найден Умным подбором» — флаг с бэка (резюме есть среди scored_candidates смарт-прогона;
  // работает и для smart-invite, и для импортированных откликов).
  const isSmartSearch = !!((candidate as any)?.from_smart_search);
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
              {formatSalaryRange(
                (candidate as any).salary_from ?? candidate.salary_expectation,
                (candidate as any).salary_to ?? candidate.salary_expectation,
                candidate.currency
              ) || '—'}
            </span>
            <span className="cd-salary-label">ожидания</span>
          </div>
          <div className="cd-tags-row">
            {candidateId && (
              <CandidateTagPicker candidateId={candidateId} assigned={candidate.tags ?? []} />
            )}
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
          <div className="cb-row">
            <span className="cb-label">Источник:</span>
            <span>{SOURCE_CONFIG[candidate.source]?.label || candidate.source || '—'}</span>
            {isSmartSearch && (
              <span
                title="Кандидат найден через Умный подбор"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '4px',
                  marginLeft: '8px', padding: '1px 8px', borderRadius: '999px',
                  fontSize: '11px', fontWeight: 600,
                  background: 'var(--ark-blue-100)', color: 'var(--accent)',
                }}
              >
                <Icon name="sparkles" size={11} /> Умный подбор
              </span>
            )}
          </div>
          {/* Блок «Открыть контакты» — только для хабр-кандидатов без открытых контактов */}
          {candidate.source === 'habr' && !candidate.habr_contacts_opened && (
            <div className="cb-row cb-habr-contacts-row">
              {isAdmin ? (
                <div className="cb-habr-contacts">
                  <button
                    className="cb-habr-btn"
                    onClick={handleOpenContacts}
                    disabled={openContactsMutation.isPending}
                    title="Откроет контакты кандидата на Хабре — спишется лимит открытий компании"
                  >
                    <Icon name="open" size={14} />
                    {openContactsMutation.isPending ? 'Открываем…' : 'Открыть контакты'}
                  </button>
                  <span className="cb-habr-hint">Спишется лимит открытий Хабра</span>
                  {openContactsError && (
                    <span className="cb-habr-error">{openContactsError}</span>
                  )}
                </div>
              ) : (
                <span className="cb-habr-locked">
                  <Icon name="lock" size={13} />
                  Контакты не открыты (только для администратора)
                </span>
              )}
            </div>
          )}
          {(candidate as { source_url?: string | null }).source_url && (
            <div className="cb-row">
              <span className="cb-label">Резюме:</span>
              <a
                className="cd-resume-link"
                href={(candidate as { source_url?: string | null }).source_url!}
                target="_blank"
                rel="noopener noreferrer"
              >
                {candidate.source === 'hh' ? 'Открыть на hh.ru' : 'Открыть оригинал'}
                <Icon name="open" size={12} />
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}