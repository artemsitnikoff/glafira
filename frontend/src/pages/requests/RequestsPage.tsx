import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '../../components/ui/Icon';
import { Avatar } from '../../components/ui/Avatar';
import { useAuthStore } from '@/store/authStore';
import {
  useRequests, useRequest, useRequestStages,
  useMoveRequest, useRejectRequest, useRestoreRequest, useCloseRequest, useAddRequestComment,
  useRequestFormLink,
  type RequestListItem, type RequestDetail, type RequestStage,
} from '@/api/hooks/useRequests';
// Экран заявок переиспользует систему классов экрана «Кандидаты/Воронка» (всё скоупнуто
// под .cnd-funnel-wrap) — грузим её CSS, иначе структура/кнопки/панель без стилей.
import '../funnel/Funnel.css';
import '../funnel/candidate-detail/CandidateDetail.css';
import './requests.css';

const FALLBACK_COLORS: Record<string, string> = {
  new: '#2A8AF0', work: '#D9A514', sourcing: '#7E5CF0', done: '#16A34A', rejected: '#DC4646',
};

const posLabel = (n: number) => {
  const f = ['позиция', 'позиции', 'позиций'];
  const i = n % 10 === 1 && n % 100 !== 11 ? 0 : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 1 : 2;
  return `${n} ${f[i]}`;
};
const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('ru-RU') : '—');
const fmtDeadline = (iso: string | null) => (iso ? `до ${fmtDate(iso)}` : 'не срочно');

function badgeClass(stage: RequestStage | undefined): string {
  if (!stage) return 'custom';
  return ['new', 'work', 'sourcing', 'done', 'rejected'].includes(stage.key) ? stage.key : 'custom';
}

function ReqBadge({ status, stages }: { status: string; stages: RequestStage[] }) {
  const s = stages.find((x) => x.key === status);
  const color = s?.color || FALLBACK_COLORS[status] || '#9AA3AE';
  return (
    <span className={`req-badge ${badgeClass(s)}`}>
      <span className="stage-dot" style={{ background: color, marginRight: 5 }} />
      {s?.label || status}
    </span>
  );
}
const ReqUrgent = () => (
  <span className="req-urgent"><Icon name="flame" size={11} /> Срочно</span>
);

// ── Полоса этапов (Б24-стиль) ─────────────────────────────────────────────────
function ReqStageStrip({
  req, stages, onMove, onReject, readOnly,
}: { req: RequestDetail; stages: RequestStage[]; onMove: (t: string) => void; onReject: () => void; readOnly: boolean }) {
  const flow = stages.filter((s) => s.key !== 'rejected');
  const curIdx = flow.findIndex((s) => s.key === req.status);
  return (
    <div className="stage-strip">
      {flow.map((s, i) => {
        const passed = i < curIdx, active = i === curIdx;
        return (
          <button key={s.key}
            className={`ss-step ${passed ? 'passed' : ''} ${active ? 'active' : ''} ${i > curIdx ? 'upcoming' : ''}`}
            style={passed || active ? ({ '--ss-color': s.color } as React.CSSProperties) : {}}
            title={s.label} disabled={readOnly} onClick={() => onMove(s.key)}>
            <span className="ss-label">{s.label}</span>
          </button>
        );
      })}
      <button className="ss-step ss-final" title="Отклонить заявку" disabled={readOnly} onClick={onReject}>
        <span className="ss-label">{req.status === 'rejected' ? 'Отклонена' : 'Отклонить'}</span>
      </button>
    </div>
  );
}

function ReqRejectPop({ onClose, onConfirm }: { onClose: () => void; onConfirm: (r: string) => void }) {
  const [reason, setReason] = useState('');
  return (
    <>
      <div className="cd-pop-backdrop" onClick={onClose} />
      <div className="cd-move-pop req-reject-pop" role="menu">
        <div className="cd-pop-head">Причина отклонения — увидит менеджер</div>
        <textarea rows={3} autoFocus value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder="Например: бюджет не согласован, позиция дублируется…" />
        <div className="req-pop-foot">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary btn-sm req-btn-danger" disabled={!reason.trim()}
            onClick={() => onConfirm(reason.trim())}>Отклонить</button>
        </div>
      </div>
    </>
  );
}

// ── Панель заявки ─────────────────────────────────────────────────────────────
function RequestDetailPanel({
  requestId, stages, readOnly, onClose,
}: { requestId: string; stages: RequestStage[]; readOnly: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const { data: req, isLoading, isError } = useRequest(requestId);
  const moveM = useMoveRequest();
  const rejectM = useRejectRequest();
  const restoreM = useRestoreRequest();
  const closeM = useCloseRequest();
  const commentM = useAddRequestComment();
  const [moveOpen, setMoveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState<string | null>(null);

  if (isError) {
    return (
      <div className="cand-detail req-panel">
        <div className="cd-toolbar">
          <span className="req-ro-hint">Не удалось загрузить заявку</span>
          <div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} title="Закрыть"><Icon name="x" size={18} /></button>
        </div>
      </div>
    );
  }
  if (isLoading || !req) return <div className="cand-detail req-panel" />;

  const createVacancy = () => {
    navigate('/vacancies/new', {
      state: {
        requestPrefill: {
          request_id: req.id,
          name: req.title,
          city: req.city,
          deadline: req.deadline,
          positions_count: req.positions,
          salary_from: req.salary_from,
          salary_to: req.salary_to,
          description: req.description,
          department: req.department,
        },
      },
    });
  };

  const moveTo = (target: string) => {
    if (target === req.status) return;
    if (target === 'sourcing' && !req.vacancy_id) { createVacancy(); return; }
    setErr(null);
    // Терминалы идут своими путями: «Закрыта» → закрытие с итогом; «Отклонена» — кнопкой.
    if (target === 'done') {
      closeM.mutate({ id: req.id }, {
        onError: (e: any) => setErr(e?.response?.data?.error?.message || 'Не удалось закрыть заявку'),
      });
      return;
    }
    moveM.mutate({ id: req.id, target }, {
      onError: (e: any) => setErr(e?.response?.data?.error?.message || 'Не удалось перевести'),
    });
  };
  const reject = (reason: string) => {
    setRejectOpen(false);
    setErr(null);
    rejectM.mutate({ id: req.id, reason }, {
      onError: (e: any) => setErr(e?.response?.data?.error?.message || 'Не удалось отклонить заявку'),
    });
  };
  const restore = () => {
    setErr(null);
    restoreM.mutate(req.id, {
      onError: (e: any) => setErr(e?.response?.data?.error?.message || 'Не удалось вернуть заявку'),
    });
  };
  const send = () => {
    const text = msg.trim();
    if (!text) return;
    // НЕ чистим инпут до успеха — иначе при ошибке текст комментария теряется молча (§0).
    setErr(null);
    commentM.mutate({ id: req.id, body: text }, {
      onSuccess: () => setMsg(''),
      onError: (e: any) => setErr(e?.response?.data?.error?.message || 'Сообщение не отправлено — попробуйте ещё раз'),
    });
  };

  const flow = stages.filter((s) => s.key !== 'rejected');
  const curIdx = flow.findIndex((s) => s.key === req.status);
  const showThread = req.status === 'new' || req.status === 'work' || req.comments.length > 0;
  const canCreateVac = req.status === 'new' || req.status === 'work';

  return (
    <div className="cand-detail req-panel">
      {readOnly ? (
        <div className="cd-toolbar">
          <span className="req-ro-hint"><Icon name="lock" size={13} /> Заявка у рекрутинга — статус обновляется здесь автоматически</span>
          <div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} title="Закрыть"><Icon name="x" size={18} /></button>
        </div>
      ) : (
        <div className="cd-toolbar">
          <div className="cd-move-wrap">
            <button className="btn btn-success btn-sm" onClick={() => setMoveOpen((o) => !o)}>
              <Icon name="arrowRight" size={14} /> Перевести <Icon name="chevD" size={12} />
            </button>
            {moveOpen && (
              <>
                <div className="cd-pop-backdrop" onClick={() => setMoveOpen(false)} />
                <div className="cd-move-pop" role="menu">
                  <div className="cd-pop-head">На какой этап?</div>
                  {flow.map((s, i) => (
                    <button key={s.key}
                      className={`cd-pop-item ${s.key === req.status ? 'cur' : ''} ${i === curIdx + 1 ? 'next' : ''}`}
                      onClick={() => { setMoveOpen(false); moveTo(s.key); }}>
                      <span className="stage-dot" style={{ background: s.color }} />
                      <span className="cd-pop-label">{s.label}{s.key === 'sourcing' && !req.vacancy_id ? ' — создать вакансию' : ''}</span>
                      {s.key === req.status && <span className="cd-pop-tag">сейчас</span>}
                      {i === curIdx + 1 && <span className="cd-pop-tag cd-pop-tag-next">далее</span>}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="cd-move-wrap">
            <button className="btn btn-secondary btn-sm" onClick={() => setRejectOpen((o) => !o)}>
              <Icon name="x" size={14} /> Отклонить <Icon name="chevD" size={12} />
            </button>
            {rejectOpen && <ReqRejectPop onClose={() => setRejectOpen(false)} onConfirm={reject} />}
          </div>
          {canCreateVac && (
            <button className="btn btn-primary btn-sm" onClick={createVacancy}><Icon name="briefcase" size={14} /> Создать вакансию</button>
          )}
          {req.status === 'sourcing' && req.vacancy_id && (
            <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/vacancies/${req.vacancy_id}`)}><Icon name="open" size={14} /> Открыть вакансию</button>
          )}
          {req.status === 'rejected' && (
            <button className="btn btn-secondary btn-sm" onClick={restore}><Icon name="refresh" size={14} /> Вернуть в работу</button>
          )}
          <div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} title="Закрыть"><Icon name="x" size={18} /></button>
        </div>
      )}

      {err && <div className="error-banner" role="alert" style={{ margin: '8px 20px 0' }}>{err}</div>}

      <div className={`req-strip-row ${readOnly ? 'req-strip-ro' : ''}`}>
        <ReqStageStrip req={req} stages={stages} onMove={moveTo} onReject={() => setRejectOpen(true)} readOnly={readOnly} />
      </div>

      <div className="req-p-head">
        <div className="cd-context">
          <span className="src-pill">Заявка №{req.num}</span>
          {req.via === 'form' && <span className="src-pill req-pill-form"><Icon name="link" size={11} /> по ссылке-форме</span>}
          <span>{req.author_name || 'Заказчик'}{req.author_role ? ` · ${req.author_role}` : ''}</span>
          <span className="sep">·</span>
          <span>подана {fmtDate(req.created_at)}</span>
          <span className="sep">·</span>
          <span>срок: {fmtDeadline(req.deadline)}</span>
        </div>
        <div className="req-p-title">
          <h1>{req.title}</h1>
          <ReqBadge status={req.status} stages={stages} />
          {req.priority === 'high' && req.status !== 'done' && req.status !== 'rejected' && <ReqUrgent />}
        </div>
      </div>

      <div className="req-panel-body">
        <div className="req-grid">
          <div className="req-col">
            <div className="req-card">
              <div className="req-card-title">Описание от менеджера</div>
              <p className="req-desc">{req.description}</p>
            </div>
            {showThread && (
              <div className="req-card">
                <div className="req-card-title">Уточнения с заказчиком</div>
                {req.comments.length === 0 && (
                  <div className="req-thread-empty">
                    {readOnly
                      ? 'Вопросов от рекрутера пока нет. Напишите, если хотите что-то добавить к заявке.'
                      : req.status === 'new'
                        ? 'Пока вопросов не было. Если что-то неясно — спросите: заявка перейдёт «В работу».'
                        : 'Пока вопросов не было. Задайте вопрос менеджеру, если что-то неясно.'}
                  </div>
                )}
                {req.comments.map((c) => (
                  <div key={c.id} className={`req-msg ${c.side}`}>
                    <Avatar name={c.author_name || '—'} size="sm" />
                    <div className="req-msg-body">
                      <div className="req-msg-head">{c.author_name} <span>{new Date(c.created_at).toLocaleString('ru-RU')}</span></div>
                      <div className="req-msg-text">{c.body}</div>
                    </div>
                  </div>
                ))}
                {(req.status === 'new' || req.status === 'work' || req.status === 'sourcing') && (
                  <div className="req-thread-input">
                    <input value={msg} onChange={(e) => setMsg(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && send()}
                      placeholder={readOnly ? 'Написать рекрутеру…' : 'Вопрос менеджеру…'} />
                    <button className="btn btn-secondary btn-sm" disabled={!msg.trim()} onClick={send}>
                      <Icon name="send" size={14} /> Отправить
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="req-col req-col-side">
            <div className="req-card">
              <div className="req-card-title">Параметры</div>
              <div className="req-params">
                <div><span>Позиции</span><b>{posLabel(req.positions)}</b></div>
                <div><span>Город</span><b>{req.city || '—'}</b></div>
                <div><span>Отдел</span><b>{req.department || '—'}</b></div>
                <div><span>Срок</span><b>{fmtDeadline(req.deadline)}</b></div>
                {req.salary_from != null && (
                  <div><span>Вилка</span><b>{req.salary_from.toLocaleString('ru-RU')}{req.salary_to != null ? ` – ${req.salary_to.toLocaleString('ru-RU')}` : ''} ₽</b></div>
                )}
                <div><span>Приоритет</span><b>{req.priority === 'high' ? '🔥 Срочно' : 'Обычный'}</b></div>
                {req.author_contact && <div><span>Контакт</span><b>{req.author_contact}</b></div>}
              </div>
            </div>
            {req.status === 'sourcing' && req.progress && (
              <div className="req-card req-card-vac">
                <div className="req-card-title">Вакансия по заявке</div>
                <div className="req-vac-name" style={readOnly ? { cursor: 'default' } : undefined}
                  onClick={() => !readOnly && req.vacancy_id && navigate(`/vacancies/${req.vacancy_id}`)}>
                  {req.progress.vacancy_name} {!readOnly && <Icon name="chevR" size={14} />}
                </div>
                <div className="req-vac-stats">
                  <div><b>{req.progress.candidates}</b><span>кандидатов</span></div>
                  <div><b>+{req.progress.new_count}</b><span>новых</span></div>
                  <div><b>{req.progress.hired} из {req.progress.positions}</b><span>нанято</span></div>
                </div>
                <div className="req-vac-note">
                  <Icon name="sparkle" size={13} /> Заявка закроется сама, когда нанятых станет {req.progress.positions} из {req.progress.positions}.
                </div>
              </div>
            )}
            {req.status === 'done' && (
              <div className="req-card req-card-done">
                <div className="req-card-title">Итог</div>
                <div className="req-done-line"><Icon name="check" size={15} /> {req.closed_note || 'Заявка закрыта'}</div>
              </div>
            )}
            {req.status === 'rejected' && req.reject_reason && (
              <div className="req-card req-card-rej">
                <div className="req-card-title">Причина отклонения</div>
                <p className="req-desc">{req.reject_reason}</p>
              </div>
            )}
            <div className="req-card">
              <div className="req-card-title">История</div>
              <div className="req-tl">
                {[...req.history].reverse().map((h, i) => (
                  <div key={i} className="req-tl-row">
                    <span className="req-tl-dot" />
                    <div><div className="req-tl-label">{h.label}</div><div className="req-tl-time">{new Date(h.at).toLocaleString('ru-RU')}</div></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Экран списка ──────────────────────────────────────────────────────────────
export default function RequestsPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  // Гейт зеркалит бек, где «персонал» = admin+recruiter (`services/hiring_request.py:48`
  // `_is_staff`). Для manager сервер: author-scope'ит список (:102), отбивает управление
  // 403 (`assert_can_manage`, :62) и не отдаёт `/requests/form-link` (require_recruiter_or_admin).
  // При гейте только по hiring_manager у manager рендерились кнопки «Ссылка на форму»/
  // «Воронка», ведущие на /settings, откуда RoleGuard(['admin','recruiter']) выкидывает
  // на /home, и активный тулбар панели, дающий 403 — мёртвые контролы (CLAUDE.md §0).
  const isMgr = user?.role !== 'admin' && user?.role !== 'recruiter';
  const [searchParams, setSearchParams] = useSearchParams();
  const [stage, setStage] = useState('all');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Deep-link из чипа вакансии «по заявке №N» (/requests?open=<id>).
  useEffect(() => {
    const open = searchParams.get('open');
    if (open) {
      setSelectedId(open);
      searchParams.delete('open');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const { data: stagesData } = useRequestStages();
  const stages: RequestStage[] = stagesData || [];
  const { data, isLoading } = useRequests({ status: stage, query });
  const items: RequestListItem[] = data?.items || [];

  const formLink = useRequestFormLink(!isMgr);

  // Счётчики чипов — из АГРЕГАТА этапов (stage.count с бэка), НЕ из отфильтрованного
  // списка items: иначе клик по этапу схлопывал остальные счётчики в 0 (баг).
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    let all = 0;
    stages.forEach((s) => {
      c[s.key] = s.count ?? 0;
      all += s.count ?? 0;
    });
    c.all = all;
    return c;
  }, [stages]);

  const active = (counts['new'] || 0) + (counts['work'] || 0) + (counts['sourcing'] || 0);
  const nonTerminal = stages.filter((s) => !s.terminal);

  const copyLink = async () => {
    // Ссылка существует всегда (своя на компанию). Копируем; приём заявок включается в Настройках.
    const url = formLink.data?.url;
    if (!url) { navigate('/settings?tab=requests'); return; }
    try { await navigator.clipboard.writeText(url); } catch { /* clipboard недоступен — молча */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`cnd-funnel-wrap${selectedId ? ' detail-mode' : ''}`}>
      <div className="vac-header">
        <div className="vh-left">
          <h1 className="vh-title">{isMgr ? 'Мои заявки' : 'Заявки на подбор'}</h1>
          <div className="vh-meta">
            <span>{active} активных</span>
            <span className="sep">·</span>
            <span>{isMgr ? 'статусы и уточнения рекрутера — здесь, в реальном времени' : 'нанимающие менеджеры подают заявки из кабинета или по ссылке-форме'}</span>
          </div>
        </div>
        <div className="vh-actions">
          {!isMgr && (
            <button className="btn btn-secondary btn-sm" onClick={copyLink} title="Длинная непубличная ссылка на форму — заявки с неё помечаются">
              <Icon name={copied ? 'check' : 'link'} size={14} /> {copied ? 'Скопировано' : 'Ссылка на форму'}
            </button>
          )}
          {!isMgr && (
            <button className="btn btn-secondary btn-sm" onClick={() => navigate('/settings?tab=requests')} title="Этапы воронки заявок настраиваются в Настройках">
              <Icon name="funnel" size={14} /> Воронка
            </button>
          )}
          <button className="btn btn-primary btn-sm" onClick={() => navigate('/requests/new')}><Icon name="plus" size={14} /> Новая заявка</button>
        </div>
      </div>

      <div className="funnel-row">
        <div className={`funnel-chip funnel-all ${stage === 'all' ? 'active' : ''}`} onClick={() => { setStage('all'); setSelectedId(null); }}>
          Все <span className="fc-count">{counts.all}</span>
        </div>
        {nonTerminal.map((s) => (
          <div key={s.key} style={{ display: 'contents' }}>
            <div className={`funnel-chip ${stage === s.key ? 'active' : ''}`} onClick={() => { setStage(s.key); setSelectedId(null); }}>
              <span className="stage-dot" style={{ background: s.color }} />
              {s.label} <span className="fc-count">{counts[s.key] || 0}</span>
            </div>
            <Icon name="chevR" size={12} className="funnel-arrow" />
          </div>
        ))}
        <div className={`funnel-chip funnel-hired ${stage === 'done' ? 'active' : ''}`} onClick={() => { setStage('done'); setSelectedId(null); }}>
          <Icon name="check" size={12} /> Закрыта <span className="fc-count">{counts.done || 0}</span>
        </div>
        <div className="funnel-gap" />
        <div className={`funnel-chip funnel-rejected ${stage === 'rejected' ? 'active' : ''}`} onClick={() => { setStage('rejected'); setSelectedId(null); }}>
          <Icon name="x" size={12} /> Отклонена <span className="fc-count">{counts.rejected || 0}</span>
        </div>
      </div>

      <div className="cand-controls">
        <div className="submenu-search" style={{ width: 280, height: 30, background: '#fff', border: '1px solid var(--border-1)' }}>
          <Icon name="search" size={14} style={{ color: 'var(--fg-3)', flex: 'none' }} />
          <input placeholder="Поиск по заявкам…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div style={{ flex: 1 }} />
      </div>

      <div className="cand-body">
        <div className="cand-table">
          <div className="req-cards">
            {items.map((r) => {
              const s = stages.find((x) => x.key === r.status);
              const color = s?.color || FALLBACK_COLORS[r.status] || '#9AA3AE';
              return (
                <div key={r.id} className="req-cardrow"
                  style={{ '--stage-color': color } as React.CSSProperties}
                  onClick={() => setSelectedId(r.id)}>
                  <Avatar name={r.author_name || '—'} size="md" />
                  <div className="req-cr-main">
                    <div className="req-cr-title">
                      <span className="req-num">№{r.num}</span>
                      <span className="req-name">{r.title}</span>
                      {r.priority === 'high' && r.status !== 'done' && r.status !== 'rejected' && <ReqUrgent />}
                    </div>
                    <div className="req-cr-sub">{r.author_name || 'Заказчик'}{r.author_role ? ` · ${r.author_role}` : ''}</div>
                    <div className="req-cr-sub2">{[r.department, r.city].filter(Boolean).join(' · ') || '—'}</div>
                  </div>
                  <div className="req-cr-facts">
                    <div><span>Позиции</span><b>{r.positions}</b></div>
                    <div><span>Срок</span><b className="t-mono">{r.deadline ? fmtDate(r.deadline) : '—'}</b></div>
                    <div><span>Подана</span><b className="t-mono">{fmtDate(r.created_at)}</b></div>
                  </div>
                  <div className="req-cr-stage">
                    <ReqBadge status={r.status} stages={stages} />
                    {r.status === 'sourcing' && r.progress && (
                      <span className="req-mini">нанято {r.progress.hired} из {r.progress.positions} · {r.progress.candidates} канд.</span>
                    )}
                    {r.status === 'done' && r.progress && <span className="req-mini ok">нанято {r.progress.hired} из {r.progress.positions}</span>}
                  </div>
                  <Icon name="chevR" size={16} style={{ color: 'var(--fg-3)', flex: 'none' }} />
                </div>
              );
            })}
            {!isLoading && items.length === 0 && (
              <div className="empty-pane" style={{ height: 280 }}>
                <div className="empty-illust"><Icon name="inbox" size={36} /></div>
                <h3>{query ? 'Ничего не найдено' : 'Заявок пока нет'}</h3>
                <p>{query ? 'Попробуйте изменить запрос.' : isMgr ? 'Нажмите «Новая заявка», чтобы описать, кто вам нужен.' : 'Заявки появятся, когда менеджер подаст новую или вы внесёте её вручную.'}</p>
              </div>
            )}
          </div>
        </div>

        {/* Панель — прямой ребёнок .cand-body (якорь absolute-оверлея), как в воронке. */}
        {selectedId && (
          <RequestDetailPanel key={selectedId} requestId={selectedId} stages={stages} readOnly={!!isMgr}
            onClose={() => setSelectedId(null)} />
        )}
      </div>
    </div>
  );
}
