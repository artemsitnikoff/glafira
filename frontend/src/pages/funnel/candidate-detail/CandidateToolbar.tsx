import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import type { ApplicationRow, Candidate } from '@/api/aliases';
import { useMoveApplication, useRejectApplication, useRestoreApplication } from '@/api/mutations/applications';
import { useRequestConsent } from '@/api/mutations/candidateDetail';
import { useVacancyStages } from '@/api/hooks/useVacancyStages';
import { useVacancyRejectReasons } from '@/api/hooks/useVacancyRejectReasons';
import { useResumeDownload } from '@/api/hooks/useResumeDownload';
import { useAuthStore } from '@/store/authStore';
import { OfferModal } from './OfferModal';

type Props = {
  application?: ApplicationRow;
  candidate?: Candidate;
  fromPool?: boolean;
  onClose: () => void;
  onTabChange?: (tab: string) => void;
  onEdit?: () => void;
  vacancyId?: string;
};

type RejectReason = {
  id: string;
  side: string;
  label: string;
};

export function CandidateToolbar({ application, candidate, fromPool, onClose, onTabChange, onEdit, vacancyId: vacancyIdProp }: Props) {
  const navigate = useNavigate();
  const { id: routeVacancyId } = useParams();
  const vacancyId = vacancyIdProp || routeVacancyId;
  // Менеджеры не редактируют кандидатов (бэк PATCH вернёт 403) — не показываем карандаш
  const canEdit = useAuthStore((s) => s.user?.role) !== 'manager';
  const [movePopoverOpen, setMovePopoverOpen] = useState(false);
  const [rejectPopoverOpen, setRejectPopoverOpen] = useState(false);
  const [downloadPopoverOpen, setDownloadPopoverOpen] = useState(false);
  // Шаг выбора даты выхода при найме (перевод в «Нанят»).
  const [pickingHire, setPickingHire] = useState(false);
  const [hireDate, setHireDate] = useState('');
  // Попап отправки оффера (контекстная кнопка на этапе «Оффер»).
  const [offerOpen, setOfferOpen] = useState(false);

  const isHired = application?.stage === 'hired';
  const isRejected = application?.stage === 'rejected';
  // Кнопка «Отправить оффер» видна СТРОГО на этапе 'offer' (этап удаляемый —
  // нет этапа → нет кнопки). Нет email → кнопка есть, но disabled с пояснением.
  const isOffer = application?.stage === 'offer';
  const hasEmail = !!candidate?.email;
  // Дата последней отправки оффера (из ApplicationRow.offer_sent_at). Формат ДД.ММ.ГГГГ
  // через ru-RU локаль. Поле может ещё не приходить от бека → бейджа просто нет.
  const offerSentDate = application?.offer_sent_at
    ? new Date(application.offer_sent_at).toLocaleDateString('ru-RU')
    : null;

  // Этапы воронки + причины отказа вакансии (привязаны к вакансии, не общие компании).
  const { data: stages } = useVacancyStages(vacancyId || '');
  const { data: rejectReasons } = useVacancyRejectReasons(vacancyId);

  const moveMutation = useMoveApplication(vacancyId);
  const rejectMutation = useRejectApplication(vacancyId);
  const restoreMutation = useRestoreApplication(vacancyId);
  const consentMutation = useRequestConsent(candidate?.id || '');
  const downloadMutation = useResumeDownload();

  function handleMoveToStage(stageKey: string) {
    if (!application) return;
    // Не двигать на текущий этап
    if (stageKey === application.stage) {
      setMovePopoverOpen(false);
      return;
    }
    moveMutation.mutate({ id: application.id, data: { to_stage: stageKey } });
    setMovePopoverOpen(false);
  }

  function handleHire() {
    if (!application || !hireDate) return;
    // hire_date → start_date сотрудника в Пульсе (openapi отстаёт → cast).
    moveMutation.mutate({
      id: application.id,
      data: { to_stage: 'hired', hire_date: hireDate } as { to_stage: string },
    });
    setMovePopoverOpen(false);
    setPickingHire(false);
  }

  function handleRejectWithReason(reason: RejectReason) {
    if (!application) return;
    rejectMutation.mutate({ id: application.id, data: { reason: reason.label, side: reason.side } });
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
    // Бэкенд авто-создаёт сотрудника при найме — ведём в Пульс с поиском по ФИО
    if (candidate) {
      navigate(`/pulse?status=onboarding&q=${encodeURIComponent(candidate.full_name)}`);
    }
  }

  function handleDownloadResume(format: 'pdf' | 'docx') {
    if (!candidate) return;

    const fileName = `${candidate.full_name}.${format}`;
    downloadMutation.mutate({
      candidateId: candidate.id,
      format,
      fileName
    });
    setDownloadPopoverOpen(false);
  }

  const availableStages = stages?.filter(stage => !stage.is_terminal) || [];
  const hiredStage = stages?.find((s) => s.stage_key === 'hired');
  const curStageIdx = availableStages.findIndex(s => s.stage_key === application?.stage);
  const candidateReasons = rejectReasons?.filter(r => r.side === 'candidate') || [];
  const companyReasons = rejectReasons?.filter(r => r.side === 'company') || [];

  // fromPool mode — actions are in header, return null
  if (fromPool) {
    return null;
  }

  return (
    <div className="cd-toolbar">
      {/* Перевести / Создать сотрудника */}
      {!isRejected && (
        <div className="cd-move-wrap">
          {isHired ? (
            <button className="btn btn-success btn-sm" onClick={handleCreateEmployee}>
              <Icon name="arrow-right" size={14} />
              Создать сотрудника
            </button>
          ) : (
            <button className="btn btn-success btn-sm" onClick={() => setMovePopoverOpen(o => !o)}>
              <Icon name="arrow-right" size={14} />
              Перевести
              <Icon name="chevron-down" size={12} />
            </button>
          )}

          {movePopoverOpen && !isHired && (
            <>
              <div className="cd-pop-backdrop" onClick={() => { setMovePopoverOpen(false); setPickingHire(false); }} />
              <div className="cd-move-pop" role="menu">
                {!pickingHire ? (
                  <>
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
                    {hiredStage && (
                      <button
                        className="cd-pop-item cd-pop-hire"
                        onClick={() => { setHireDate(new Date().toISOString().slice(0, 10)); setPickingHire(true); }}
                        disabled={moveMutation.isPending}
                      >
                        <span className="stage-dot" style={{ background: hiredStage.color }} />
                        <span className="cd-pop-label">{hiredStage.label}</span>
                        <span className="cd-pop-tag cd-pop-tag-hire">наём</span>
                      </button>
                    )}
                  </>
                ) : (
                  <>
                    <div className="cd-pop-head">Дата выхода</div>
                    <div style={{ padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <input
                        type="date"
                        value={hireDate}
                        onChange={(e) => setHireDate(e.target.value)}
                        style={{ fontSize: 13, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--ark-gray-300)' }}
                      />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-secondary btn-sm" onClick={() => setPickingHire(false)}>Назад</button>
                        <button
                          className="btn btn-success btn-sm"
                          disabled={!hireDate || moveMutation.isPending}
                          onClick={handleHire}
                        >
                          Нанять
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Отправить оффер — контекстная кнопка этапа «Оффер». canEdit скрывает её у
          роли manager: бек запрещает оффер (403) — кнопка ей была бы только ошибкой. */}
      {isOffer && canEdit && (
        <button
          className="btn btn-primary btn-sm"
          onClick={() => setOfferOpen(true)}
          disabled={!hasEmail}
          title={hasEmail ? 'Отправить оффер кандидату на email' : 'У кандидата не указан email'}
        >
          <Icon name="mail" size={14} />
          Отправить оффер
        </button>
      )}

      {/* Бейдж «Отправлен ✓ дата» — рядом с кнопкой (не вместо!), повторная отправка
          остаётся доступной; при ней дата в бейдже обновится. По образцу «ПдН ✓». */}
      {isOffer && offerSentDate && (
        <span className="cd-offer-sent" title={`Оффер отправлен ${offerSentDate}`}>
          Отправлен
          <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
            <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          {offerSentDate}
        </span>
      )}

      {/* Отклонить / Восстановить */}
      {isRejected ? (
        <button className="btn btn-secondary btn-sm" onClick={handleRestore} disabled={restoreMutation.isPending}>
          Восстановить
        </button>
      ) : (
        <div className="cd-move-wrap">
          <button className="btn btn-secondary btn-sm" onClick={() => setRejectPopoverOpen(o => !o)}>
            <Icon name="x" size={14} />
            Отклонить
            <Icon name="chevron-down" size={12} />
          </button>

          {rejectPopoverOpen && (
            <>
              <div className="cd-pop-backdrop" onClick={() => setRejectPopoverOpen(false)} />
              <div className="cd-move-pop cd-reject-pop" role="menu">
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
          )}
        </div>
      )}

      {/* Комментарий */}
      <button className="btn btn-secondary btn-sm" onClick={handleComment}>
        <Icon name="message-square" size={14} />
        Комментарий
      </button>

      {/* Скачать резюме */}
      {candidate && (
        <div className="cd-move-wrap">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setDownloadPopoverOpen(o => !o)}
            title="Сохранить резюме"
          >
            <Icon name="save" size={14} />
            Резюме
            <Icon name="chevron-down" size={12} />
          </button>

          {downloadPopoverOpen && (
            <>
              <div className="cd-pop-backdrop" onClick={() => setDownloadPopoverOpen(false)} />
              <div className="cd-move-pop cd-download-pop" role="menu">
                <div className="cd-pop-head">Формат файла</div>
                <button
                  className="cd-pop-item"
                  onClick={() => handleDownloadResume('pdf')}
                  disabled={downloadMutation.isPending}
                >
                  <Icon name="file" size={16} />
                  <span className="cd-pop-label">Скачать PDF</span>
                </button>
                <button
                  className="cd-pop-item"
                  onClick={() => handleDownloadResume('docx')}
                  disabled={downloadMutation.isPending}
                >
                  <Icon name="file-text" size={16} />
                  <span className="cd-pop-label">Скачать DOCX</span>
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ПдН */}
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

      {/* Редактировать кандидата (карандаш) — открывает форму правки (как создание) */}
      {candidate && onEdit && canEdit && (
        <button
          className="btn btn-secondary btn-sm"
          onClick={onEdit}
          title="Редактировать кандидата"
        >
          <Icon name="edit" size={14} />
          Изменить
        </button>
      )}

      <div style={{ flex: 1 }} />

      {/* Закрыть */}
      <button className="icon-btn" onClick={onClose} title="Закрыть">
        <Icon name="x" size={18} />
      </button>

      {/* Попап отправки оффера (fixed-оверлей) */}
      <OfferModal
        applicationId={application?.id ?? ''}
        candidateId={application?.candidate_id ?? ''}
        candidateName={candidate?.full_name ?? application?.full_name ?? ''}
        isOpen={offerOpen}
        onClose={() => setOfferOpen(false)}
      />
    </div>
  );
}
