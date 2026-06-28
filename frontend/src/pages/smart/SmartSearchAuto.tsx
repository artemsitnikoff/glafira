// Ветка В умного подбора — «Автоподбор» (сохранённые автопоиски hh.ru).
// ЧАНК A: шапка ветки + список автопоисков из реального бека (/smart/auto/*).
// ЧАНК B: список кандидатов выбранного автопоиска (пагинация/сегмент/сортировка)
//   + нижняя bottom-sheet превью-карточка (своя вёрстка на классах .cand-detail).
// ЧАНК C: основа оценки (vacancy/промт) + AI-оценка в фоне (поллинг) + реальный разбор в табе Оценка AI.
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/ui/Icon';
import { ScoreLabel } from '@/components/ui/ScoreLabel';
import { useVacancies } from '@/api/hooks/useVacancies';
import {
  useAutoAccess,
  useAutoCandidates,
  useAutoSearches,
  useSyncAutoSearches,
  useSetAutoBasis,
  useToggleAutoEval,
  useRunAutoEval,
  useAutoEvalRun,
  useAutoTake,
  type AutoCandidate,
  type AutoSearch,
  type AutoSearchBasis,
  type AutoScored,
  type AutoTakeResp,
} from '@/api/hooks/useSmartSearch';
import type { components } from '@/api/types';
import './SmartSearchAuto.css';
// CSS-классы карточки соискателя (.cd-toolbar/.cd-header/.resume-single/.ai-single/...)
// переиспользуем в bottom-sheet — как в CandidatePoolDetailPage. Сам компонент
// CandidateDetail НЕ монтируем (он завязан на application/candidate_id из БД).
import '../funnel/candidate-detail/CandidateDetail.css';

// Форматирование чисел с разделителями (зеркало ssFmt из SmartSearchPage)
function ssaFmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString('ru-RU');
}

// Имя автопоиска приходит от hh иногда В КАВЫЧКАХ (`"Business upgrade"`) —
// срезаем ведущие/замыкающие кавычки перед обёрткой в «…».
function stripQuotes(name: string): string {
  return name.replace(/^["«»\s]+|["«»\s]+$/g, '');
}

// Короткая сводка основы оценки (вакансия/промт)
function basisLabel(b: AutoSearch['basis']): string | null {
  if (!b) return null;
  if (b.kind === 'vacancy') return 'против вакансии';
  const t = (b.prompt || '').trim();
  if (!t) return 'по промту';
  return t.length > 40 ? t.slice(0, 40) + '…' : t;
}

// Русское склонение числительного (год/года/лет)
function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

// Локальный тип ответа с ошибкой (ApiError envelope)
interface ApiErrEnvelope {
  error?: { code?: string; message?: string };
}

// Хелпер текста ошибки для тоста (учитывает ApiError envelope из client.ts)
function takeErrorText(e: unknown): string {
  const env = e as ApiErrEnvelope;
  const code = env?.error?.code;
  const msg = env?.error?.message;
  if (code === 'SUBSCRIPTION_EXPIRED' || code === '402') return 'Нет платного доступа к базе hh';
  if (code === '429' || (typeof msg === 'string' && msg.toLowerCase().includes('pool'))) {
    return 'Пул контактов исчерпан. Пополните в кабинете hh';
  }
  if (msg) return msg;
  if (e instanceof Error) return e.message;
  return 'Не удалось забрать контакт';
}

// Тип вакансии для поповера «Перевести»
type VacItem = Pick<components['schemas']['VacancyDetail'], 'id' | 'name'>;

// windowed список страниц: [1, '…', 4, 5, 6, '…', 65] (порт saPager из прототипа).
// Возвращает позиции 1-based; '…' — разделитель.
function saPager(cur: number, count: number): (number | '…')[] {
  const out: (number | '…')[] = [];
  for (let p = 1; p <= count; p++) {
    if (p === 1 || p === count || (p >= cur - 1 && p <= cur + 1)) {
      out.push(p);
    } else if (out[out.length - 1] !== '…') {
      out.push('…');
    }
  }
  return out;
}

// ====== Диалог выбора основы оценки (вакансия или промт) ======
type BasisDialogProps = {
  searchName: string;
  current: AutoSearchBasis | null;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: (basis: AutoSearchBasis) => void;
};

function SSAutoBasisDialog({ searchName, current, confirmLabel, onCancel, onConfirm }: BasisDialogProps) {
  const [kind, setKind] = useState<'vacancy' | 'prompt'>(current?.kind ?? 'vacancy');
  const [vacId, setVacId] = useState<string | null>(
    current?.kind === 'vacancy' ? (current.vacancy_id ?? null) : null,
  );
  const [text, setText] = useState(current?.kind === 'prompt' ? (current.prompt ?? '') : '');

  const { data: vacData, isLoading: vacLoading } = useVacancies({ status: 'active', page_size: 100 });

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onCancel]);

  const canConfirm = kind === 'vacancy' ? !!vacId : text.trim().length >= 3;

  function handleConfirm() {
    if (!canConfirm) return;
    if (kind === 'vacancy') {
      onConfirm({ kind: 'vacancy', vacancy_id: vacId! });
    } else {
      onConfirm({ kind: 'prompt', prompt: text.trim() });
    }
  }

  return (
    <>
      <div className="ssa-modal-backdrop" onClick={onCancel} />
      <div className="ssa-modal" role="dialog" aria-label="Основа оценки">
        <div className="ssa-modal-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="ssa-modal-title">Относительно чего оценивать?</div>
            <div className="ssa-modal-sub">
              Оценка кандидата — относительная. Глафира сравнит резюме из автопоиска «{searchName}» с вашей
              вакансией или с описанием идеального кандидата.
            </div>
          </div>
          <button className="icon-btn" onClick={onCancel} title="Закрыть">
            <Icon name="x" size={18} />
          </button>
        </div>

        <div className="ssa-modal-body">
          {/* Метод 1 — по вакансии */}
          <div
            className={`ssb-method ${kind === 'vacancy' ? 'is-active' : 'is-dim'}`}
            onClick={() => setKind('vacancy')}
          >
            <div className="ssb-method-head ssb-method-toggle">
              <span className="ssb-radio" data-on={kind === 'vacancy' ? 'true' : 'false'} />
              <div className="ssb-method-titles">
                <div className="ssb-method-title">По открытой вакансии</div>
                <div className="ssb-method-desc">Глафира возьмёт требования вакансии как эталон.</div>
              </div>
            </div>
            {kind === 'vacancy' && (
              <div className="ssa-vac-list" onClick={(e) => e.stopPropagation()}>
                {vacLoading && <span className="ssa-vac-loading">Загрузка вакансий…</span>}
                {vacData?.items?.map((v) => (
                  <button
                    key={v.id}
                    className={`ssa-vac-opt ${vacId === v.id ? 'sel' : ''}`}
                    onClick={() => setVacId(v.id)}
                    type="button"
                  >
                    <Icon name="briefcase" size={15} className="ssa-vac-ic" />
                    <span className="ssa-vac-name">{v.name}</span>
                    {vacId === v.id && <Icon name="check" size={15} className="ssa-vac-check" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="ssb-or"><span>или</span></div>

          {/* Метод 2 — промт */}
          <div
            className={`ssb-method ${kind === 'prompt' ? 'is-active' : 'is-dim'}`}
            onClick={() => setKind('prompt')}
          >
            <div className="ssb-method-head ssb-method-toggle">
              <span className="ssb-radio" data-on={kind === 'prompt' ? 'true' : 'false'} />
              <div className="ssb-method-titles">
                <div className="ssb-method-title">По описанию (промт)</div>
                <div className="ssb-method-desc">Опишите словами, кто вам нужен — это станет эталоном оценки.</div>
              </div>
            </div>
            {kind === 'prompt' && (
              <textarea
                className="ssb-textarea ssa-basis-textarea"
                placeholder="Например: DevOps с Kubernetes и CI/CD, от 3 лет, опыт on-call, готов выйти быстро…"
                value={text}
                rows={3}
                onChange={(e) => setText(e.target.value)}
                onClick={(e) => e.stopPropagation()}
              />
            )}
          </div>
        </div>

        <div className="ssa-modal-foot">
          <button className="btn btn-secondary btn-sm" onClick={onCancel} type="button">
            Отмена
          </button>
          <button className="btn btn-primary btn-sm" onClick={handleConfirm} disabled={!canConfirm} type="button">
            <Icon name="sparkles" size={14} /> {confirmLabel}
          </button>
        </div>
      </div>
    </>
  );
}

export function SmartSearchAuto({ onBack }: { onBack: () => void }) {
  const { data: access } = useAutoAccess();
  const { data: searches = [], isLoading, isError, error } = useAutoSearches();
  const syncMutation = useSyncAutoSearches();

  // Выбранный автопоиск → показываем его кандидатов (чанк B).
  const [searchId, setSearchId] = useState<string | null>(null);
  const selected = searches.find((s) => s.id === searchId) ?? null;

  // Нет доступа к автопоискам hh (нет привязки / 402 / 403)
  const noAccess = access && access.has_access === false;

  return (
    <div className="ss-page ssa-page">
      <SSAutoHeader onBack={onBack} poolLeft={access?.pool_left ?? null} />

      {noAccess ? (
        <SSAutoNoAccess reason={access?.reason ?? null} />
      ) : isLoading ? (
        <div className="ssa-state ssa-state-loading">
          <span className="ssa-spin" /> Загрузка автопоисков…
        </div>
      ) : isError ? (
        <div className="ssa-state ssa-state-error">
          <Icon name="alert-circle" size={16} />
          Не удалось загрузить автопоиски{error?.message ? `: ${error.message}` : '.'}
        </div>
      ) : searches.length === 0 ? (
        <div className="ssa-state ssa-state-empty">
          <Icon name="radio" size={26} className="ssa-state-ic" />
          <div className="ssa-state-title">Автопоиски не найдены</div>
          <div className="ssa-state-sub">
            Настройте сохранённый поиск на hh.ru и подпишитесь на новые резюме — он появится здесь.
          </div>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
          >
            {syncMutation.isPending
              ? <><span className="ssa-spin dark" /> Синхронизация…</>
              : <><Icon name="refresh-cw" size={14} /> Синхронизировать</>}
          </button>
        </div>
      ) : selected ? (
        // Кандидаты выбранного автопоиска (чанк B)
        <SSAutoCandidatesView
          search={selected}
          poolLeft={access?.pool_left ?? null}
          onBackToList={() => setSearchId(null)}
        />
      ) : (
        <SSAutoSearchesView
          searches={searches}
          onOpen={(id) => setSearchId(id)}
        />
      )}
    </div>
  );
}

// ====== Шапка ветки ======
function SSAutoHeader({ onBack, poolLeft }: { onBack: () => void; poolLeft: number | null }) {
  return (
    <div>
      <button className="ss-back" onClick={onBack}>
        <Icon name="chevron-left" size={14} /> Выбор источника
      </button>
      <div className="ss-head">
        <div className="ss-head-mark ssa-mark">💃</div>
        <div className="ss-head-text">
          <h1>
            Автоподбор <span className="ss-beta">beta</span>
            <span className="ssa-hh-pill"><Icon name="radio" size={12} /> пока через hh</span>
          </h1>
          <div className="ss-sub">
            Ваши <b>автопоиски на hh.ru</b>: фильтры настроены и подписаны — новые подходящие резюме
            приходят в поток. Глафира забирает их, оценивает AI-матчингом и даёт открыть контакт.
          </div>
        </div>
        <div className="ssa-pool" title="Остаток контактов в пуле hh">
          <div className="ssa-pool-num t-mono">{poolLeft ?? '—'}</div>
          <div className="ssa-pool-cap">контактов<br />в пуле</div>
        </div>
      </div>
    </div>
  );
}

// ====== Карточка одного автопоиска в списке (выделена в отдельный компонент для хуков) ======
function SSAutoSearchCard({ s, onOpen }: { s: AutoSearch; onOpen: (id: string) => void }) {
  const name = stripQuotes(s.name);
  const bl = basisLabel(s.basis);
  const newCount = s.new_count ?? 0;

  const toggleEval = useToggleAutoEval(s.id);
  const setBasis = useSetAutoBasis(s.id);

  // Локальный диалог смены основы в карточке
  const [dialog, setDialog] = useState<boolean>(false);

  function handleToggleAutoEval(e: React.MouseEvent) {
    e.stopPropagation();
    if (s.auto_eval) {
      toggleEval.mutate(false);
    } else {
      if (s.basis) {
        toggleEval.mutate(true);
      } else {
        setDialog(true);
      }
    }
  }

  function handleBasisClick(e: React.MouseEvent) {
    e.stopPropagation();
    setDialog(true);
  }

  return (
    <div className="ssa-search-card">
      {dialog && (
        <SSAutoBasisDialog
          searchName={name}
          current={s.basis}
          confirmLabel="Сохранить основу"
          onCancel={() => setDialog(false)}
          onConfirm={(basis) => {
            setBasis.mutate(basis, { onSuccess: () => setDialog(false) });
          }}
        />
      )}

      <div className="ssa-sc-main">
        <div className="ssa-sc-head">
          <span className="ssa-sc-name">«{name}»</span>
          <button className="ssa-sc-edit" title="Изменить автопоиск на hh">
            <Icon name="external-link" size={13} />
          </button>
          {s.region && (
            <span className="ssa-sc-region"><Icon name="pin" size={12} /> {s.region}</span>
          )}
          <div style={{ flex: 1 }} />
          {s.updated_at && <span className="ssa-sc-date t-mono">{s.updated_at}</span>}
        </div>

        <div className="ssa-sc-filters">
          <span
            className={`ssa-sub ${s.subscribed ? 'on' : 'off'}`}
            title="Подписка на новые резюме"
          >
            <span className="ssa-sub-dot" />
            {s.subscribed ? 'подписка активна' : 'подписка выключена'}
          </span>
        </div>

        <div className="ssa-sc-foot">
          <button className="ssa-sc-link all" onClick={() => onOpen(s.id)}>
            Показать соискателей <span className="t-mono">{ssaFmt(s.total)}</span>
          </button>
          {newCount > 0 ? (
            <button className="ssa-sc-link new" onClick={() => onOpen(s.id)}>
              <span className="ssa-new-dot" /> Новые <span className="t-mono">+{newCount}</span>
            </button>
          ) : (
            <span className="ssa-sc-nonew">новых нет</span>
          )}
        </div>
      </div>

      <div className="ssa-sc-aside">
        <div className="ssa-autoeval">
          <div className="ssa-ae-text">
            <div className="ssa-ae-title">Авто-оценка новых</div>
            <div className="ssa-ae-sub">
              {s.auto_eval ? 'новые приходят с AI-баллом' : 'оценивать вручную'}
            </div>
          </div>
          <span
            className={`ss-switch ${s.auto_eval ? 'on' : ''}`}
            aria-label="Авто-оценка"
            onClick={handleToggleAutoEval}
            title={s.auto_eval ? 'Выключить авто-оценку' : 'Включить авто-оценку'}
          />
        </div>
        {s.basis && bl ? (
          <button className="ssa-basis" title="Сменить основу оценки" onClick={handleBasisClick}>
            <Icon name={s.basis.kind === 'vacancy' ? 'briefcase' : 'message-circle'} size={12} />
            <span className="ssa-basis-text">
              <span className="ssa-basis-k">{s.basis.kind === 'vacancy' ? 'против вакансии' : 'по промту'}</span>
              <span className="ssa-basis-v">{bl}</span>
            </span>
          </button>
        ) : (
          <button className="ssa-sc-link all" style={{ fontSize: 12 }} onClick={handleBasisClick}>
            <Icon name="sparkles" size={12} /> Выбрать основу оценки
          </button>
        )}
      </div>
    </div>
  );
}

// ====== Вид: список автопоисков ======
function SSAutoSearchesView({ searches, onOpen }: {
  searches: AutoSearch[];
  onOpen: (id: string) => void;
}) {
  const totalNew = searches.reduce((s, x) => s + (x.new_count ?? 0), 0);

  // Ручная синхронизация автопоисков с hh (список кэшируется на 1ч —
  // даёт обновить сразу, без ожидания). Хук сам инвалидирует кэш в onSuccess.
  const syncMutation = useSyncAutoSearches();
  const [syncError, setSyncError] = useState<string | null>(null);

  function handleSync() {
    setSyncError(null);
    syncMutation.mutate(undefined, {
      onError: (e) => setSyncError(e?.message || 'Не удалось синхронизировать с hh'),
    });
  }

  return (
    <div className="ssa-searches">
      <div className="ssa-searches-bar">
        <div className="ssa-sb-left">
          <span className="ssa-sb-title">Автопоиски</span>
          <span className="ssa-sb-count t-mono">{searches.length}</span>
          {totalNew > 0 && <span className="ssa-sb-new">+{totalNew} новых</span>}
        </div>
        <div className="ssa-sb-sync">
          <span className="ssa-sync-dot" /> синхронизировано с hh
        </div>
        <button
          className="btn btn-secondary btn-sm ssa-sync-btn"
          onClick={handleSync}
          disabled={syncMutation.isPending}
          title="Подтянуть свежий список автопоисков с hh"
        >
          {syncMutation.isPending ? (
            <><span className="ssa-spin" /> Синхронизирую…</>
          ) : (
            <><Icon name="refresh-cw" size={14} /> Синхронизировать</>
          )}
        </button>
      </div>

      {syncError && (
        <div className="ssa-eval-err">
          <Icon name="alert-circle" size={14} />
          <span>{syncError}</span>
          <button className="icon-btn" onClick={() => setSyncError(null)} title="Закрыть">
            <Icon name="x" size={14} />
          </button>
        </div>
      )}

      <div className="ssa-search-list">
        {searches.map((s) => (
          <SSAutoSearchCard key={s.id} s={s} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

// ====== Нет доступа к автопоискам hh ======
function SSAutoNoAccess({ reason }: { reason: string | null }) {
  return (
    <div className="ssa-state ssa-state-noaccess">
      <Icon name="lock" size={26} className="ssa-state-ic" />
      <div className="ssa-state-title">Нет доступа к автопоискам hh</div>
      <div className="ssa-state-sub">
        {reason || 'Подключите hh.ru с платным доступом к базе резюме — тогда автопоиски станут доступны.'}
      </div>
    </div>
  );
}

// ====== Вид: кандидаты выбранного автопоиска (чанк B + C) ======
function SSAutoCandidatesView({
  search,
  poolLeft,
  onBackToList,
}: {
  search: AutoSearch;
  poolLeft: number | null;
  onBackToList: () => void;
}) {
  const name = stripQuotes(search.name);
  const bl = basisLabel(search.basis);
  const totalAll = search.total ?? 0;
  const newCount = search.new_count ?? 0;

  // Локальное состояние списка: сегмент / страница / сортировка / открытая карточка
  const [segment, setSegment] = useState<'all' | 'new'>('all');
  const [page, setPage] = useState(0); // 0-based (как у бека)
  const [sort, setSort] = useState<'updated' | 'score'>('updated');
  const [openId, setOpenId] = useState<string | null>(null);
  const rowsRef = useRef<HTMLDivElement | null>(null);

  // Стейт оценки (чанк C)
  const [runId, setRunId] = useState<string | null>(null);
  const [scoredMap, setScoredMap] = useState<Record<string, AutoScored>>({});
  const [evalError, setEvalError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<null | { confirmLabel: string; after: (basis: AutoSearchBasis) => void }>(null);

  // Стейт чанка C2: забор контакта / тосты / локальный трекер взятых
  type Toast = { kind: 'ok' | 'err'; text: string; action?: { label: string; to: string } } | null;
  const [toast, setToast] = useState<Toast>(null);
  const navigate = useNavigate();
  const takeMutation = useAutoTake(search.id);
  const [takenLocal, setTakenLocal] = useState<Record<string, 'pool' | 'vacancy'>>({});
  const { data: takeVacData } = useVacancies({ status: 'active', page_size: 100 });

  // Авто-скрытие тоста через 4000мс
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const qc = useQueryClient();
  const setBasis = useSetAutoBasis(search.id);
  const toggleEval = useToggleAutoEval(search.id);
  const runEval = useRunAutoEval(search.id);
  const runStatus = useAutoEvalRun(runId, !!runId);

  const { data, isLoading, isError, error, isFetching } = useAutoCandidates(search.id, {
    segment,
    page,
    sort,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? (segment === 'new' ? newCount : totalAll);
  const pages = data?.pages ?? 1;
  const perPage = data?.per_page ?? 20;
  // Диапазон «Показано N–M из T»
  const rangeStart = total === 0 ? 0 : page * perPage + 1;
  const rangeEnd = page * perPage + items.length;

  // У открытой карточки — берём кандидата из текущей страницы (sheet живёт поверх списка)
  const openCand = openId ? items.find((c) => c.hh_resume_id === openId) ?? null : null;

  // Сортировка по AI-баллу доступна, если уже есть оценённые
  const sortScoreDisabled = Object.keys(scoredMap).length === 0 && !items.some((c) => c.score != null);

  // Эффект: обработка завершения/ошибки прогона
  useEffect(() => {
    const status = runStatus.data?.status;
    if (!status || status === 'running') return;
    if (status === 'done') {
      const scored = runStatus.data?.scored_candidates ?? [];
      if (scored.length > 0) {
        setScoredMap((prev) => {
          const next = { ...prev };
          scored.forEach((s) => { next[s.hh_resume_id] = s; });
          return next;
        });
      }
      setRunId(null);
      qc.invalidateQueries({ queryKey: ['smart', 'auto', 'candidates', search.id] });
    } else if (status === 'error') {
      setEvalError(
        runStatus.data?.error || runStatus.data?.note || 'Не удалось оценить кандидатов',
      );
      setRunId(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runStatus.data?.status]);

  function openBasisDialog(confirmLabel: string, after: (basis: AutoSearchBasis) => void) {
    setDialog({ confirmLabel, after });
  }

  // doTake — забор контакта (⚠️ ПЛАТНО: списывает 1 контакт из пула hh)
  function doTake(
    c: AutoCandidate,
    target: 'pool' | 'vacancy',
    opts?: { vacancyId?: string; vacName?: string },
  ) {
    if (poolLeft === 0) {
      setToast({ kind: 'err', text: 'Пул контактов исчерпан. Пополните в кабинете hh.' });
      return; // БЕЗ запроса к беку
    }
    takeMutation.mutate(
      { resume_ids: [c.hh_resume_id], target, vacancy_id: opts?.vacancyId },
      {
        onSuccess: (resp: AutoTakeResp) => {
          const r = resp.results?.[0];
          if (r && r.status === 'error') {
            setToast({ kind: 'err', text: r.error || 'Не удалось забрать контакт' });
            return;
          }
          setTakenLocal((prev) => ({ ...prev, [c.hh_resume_id]: target }));
          const alreadyNote = r?.status === 'already' ? ' (уже в базе)' : '';
          if (target === 'pool') {
            setToast({
              kind: 'ok',
              text: `Кандидат добавлен в пул${alreadyNote}`,
              action: { label: 'Открыть базу', to: '/candidates' },
            });
          } else {
            setToast({
              kind: 'ok',
              text: `Кандидат в воронке «${opts?.vacName ?? ''}»${alreadyNote}`,
              action: {
                label: 'Открыть воронку',
                to: opts?.vacancyId ? `/vacancies/${opts.vacancyId}` : '/vacancies',
              },
            });
          }
        },
        onError: (e: unknown) => {
          setToast({ kind: 'err', text: takeErrorText(e) });
        },
      },
    );
  }

  function startEval() {
    function doRun() {
      runEval.mutate(
        { segment },
        {
          onSuccess: ({ run_id }) => setRunId(run_id),
          onError: (e) => setEvalError(e.message || 'Не удалось запустить оценку'),
        },
      );
    }
    if (search.basis) {
      doRun();
    } else {
      openBasisDialog('✨ Оценить', () => doRun());
    }
  }

  function handleToggleAutoEval() {
    if (search.auto_eval) {
      toggleEval.mutate(false);
    } else {
      if (search.basis) {
        toggleEval.mutate(true);
      } else {
        openBasisDialog('✨ Включить авто-оценку', () => toggleEval.mutate(true));
      }
    }
  }

  function scrollRowsTop() {
    const cont = rowsRef.current?.closest('.content');
    if (cont && rowsRef.current) {
      const delta = rowsRef.current.getBoundingClientRect().top - cont.getBoundingClientRect().top;
      cont.scrollTop += delta - 14;
    }
  }
  function goPage(p: number) {
    const np = Math.max(0, Math.min(pages - 1, p));
    setPage(np);
    requestAnimationFrame(scrollRowsTop);
  }
  function changeSegment(seg: 'all' | 'new') {
    setSegment(seg);
    setPage(0);
  }

  const isEvalRunning = !!runId || runEval.isPending;

  return (
    <div className="ssa-cands" ref={rowsRef}>
      {/* Диалог основы оценки */}
      {dialog && (
        <SSAutoBasisDialog
          searchName={name}
          current={search.basis}
          confirmLabel={dialog.confirmLabel}
          onCancel={() => setDialog(null)}
          onConfirm={(basis) => {
            const afterFn = dialog.after;
            setBasis.mutate(basis, {
              onSuccess: () => {
                setDialog(null);
                afterFn(basis);
              },
            });
          }}
        />
      )}

      {/* Хлебные крошки */}
      <div className="ssa-cands-head">
        <button className="ssa-crumb" onClick={onBackToList}>
          <Icon name="chevron-left" size={13} /> Автопоиски
        </button>
        <span className="ssa-crumb-sep">/</span>
        <span className="ssa-crumb-cur">«{name}»</span>
        {search.region && <span className="ssa-crumb-region">{search.region}</span>}
        <div style={{ flex: 1 }} />
        {search.basis && bl ? (
          <button
            className="ssa-basis ssa-basis-inline"
            title="Сменить основу оценки"
            onClick={() => openBasisDialog('Сохранить основу', () => {})}
          >
            <Icon name={search.basis.kind === 'vacancy' ? 'briefcase' : 'message-circle'} size={12} />
            <span className="ssa-basis-text">
              <span className="ssa-basis-k">
                {search.basis.kind === 'vacancy' ? 'оценка против вакансии' : 'оценка по промту'}
              </span>
              <span className="ssa-basis-v">{bl}</span>
            </span>
          </button>
        ) : (
          <button
            className="ssa-sc-link all"
            style={{ fontSize: 12 }}
            onClick={() => openBasisDialog('Сохранить основу', () => {})}
          >
            <Icon name="sparkles" size={12} /> Выбрать основу оценки
          </button>
        )}
      </div>

      {/* Ошибка оценки */}
      {evalError && (
        <div className="ssa-eval-err">
          <Icon name="alert-circle" size={14} />
          <span>{evalError}</span>
          <button className="icon-btn" onClick={() => setEvalError(null)} title="Закрыть">
            <Icon name="x" size={14} />
          </button>
        </div>
      )}

      {/* Панель: сегмент / сортировка / авто-оценка / кнопка оценить */}
      <div className="ssa-cands-bar">
        <div className="ssa-seg">
          <button
            className={`ssa-seg-btn ${segment === 'all' ? 'active' : ''}`}
            onClick={() => changeSegment('all')}
          >
            Все <span className="t-mono">{ssaFmt(totalAll)}</span>
          </button>
          <button
            className={`ssa-seg-btn new ${segment === 'new' ? 'active' : ''}`}
            onClick={() => changeSegment('new')}
            disabled={newCount === 0}
          >
            <span className="ssa-new-dot" /> Новые <span className="t-mono">{newCount}</span>
          </button>
        </div>

        <div style={{ flex: 1 }} />

        <label className="ssa-sort">
          <span>Сортировка</span>
          <select
            value={sort}
            onChange={(e) => {
              setSort(e.target.value as 'updated' | 'score');
              setPage(0);
            }}
          >
            <option value="updated">по обновлению</option>
            <option value="score" disabled={sortScoreDisabled}>
              по AI-баллу
            </option>
          </select>
        </label>

        {/* Авто-оценка новых — кликабельный тумблер */}
        <div className="ssa-ae-inline">
          <span className="ssa-ae-inline-label">Авто-оценка новых</span>
          <span
            className={`ss-switch ${search.auto_eval ? 'on' : ''}`}
            aria-label="Авто-оценка"
            onClick={handleToggleAutoEval}
            title={search.auto_eval ? 'Выключить авто-оценку' : 'Включить авто-оценку'}
          />
        </div>

        {/* Кнопка оценки / прогресс */}
        {runStatus.data?.status === 'running' ? (
          <div className="ssa-eval-progress">
            <span className="ssa-spin" />
            Глафира оценивает… {runStatus.data.evaluated}/{runStatus.data.to_evaluate}
          </div>
        ) : (
          <button
            className="btn btn-primary btn-sm ssa-eval-btn"
            onClick={startEval}
            disabled={isEvalRunning}
          >
            <Icon name="sparkles" size={14} /> Оценить {ssaFmt(segment === 'new' ? newCount : totalAll)}
          </button>
        )}
      </div>

      {segment === 'new' && (
        <div className="ssa-newnote">
          <Icon name="alert-triangle" size={14} />
          Показаны только новые с момента последнего просмотра. Открытие списка сбрасывает счётчик «+{newCount}» на hh.
        </div>
      )}

      {/* Список кандидатов */}
      {isLoading ? (
        <div className="ssa-state ssa-state-loading">
          <span className="ssa-spin" /> Загрузка кандидатов…
        </div>
      ) : isError ? (
        <div className="ssa-state ssa-state-error">
          <Icon name="alert-circle" size={16} />
          Не удалось загрузить кандидатов{error?.message ? `: ${error.message}` : '.'}
        </div>
      ) : items.length === 0 ? (
        <div className="ssa-rows-empty">Здесь пока пусто.</div>
      ) : (
        <>
          <div className={`ssa-rows ${isFetching ? 'is-fetching' : ''}`}>
            {items.map((c) => (
              <SSAutoRow
                key={c.hh_resume_id}
                c={c}
                score={scoredMap[c.hh_resume_id]?.score ?? c.score}
                onOpen={() => setOpenId(c.hh_resume_id)}
              />
            ))}
          </div>

          <div className="ssa-pager">
            <div className="ssa-pager-info">
              Показано <b>{rangeStart}–{rangeEnd}</b> из <b className="t-mono">{ssaFmt(total)}</b>
            </div>
            {pages > 1 && (
              <div className="ssa-pager-ctrls">
                <button
                  className="ssa-pg-nav"
                  disabled={page <= 0}
                  onClick={() => goPage(page - 1)}
                  aria-label="Назад"
                >
                  <Icon name="chevron-left" size={15} />
                </button>
                {saPager(page + 1, pages).map((p, i) =>
                  p === '…' ? (
                    <span key={`e${i}`} className="ssa-pg-ell">
                      …
                    </span>
                  ) : (
                    <button
                      key={p}
                      className={`ssa-pg ${p === page + 1 ? 'active' : ''}`}
                      onClick={() => goPage(p - 1)}
                    >
                      {p}
                    </button>
                  ),
                )}
                <button
                  className="ssa-pg-nav"
                  disabled={page >= pages - 1}
                  onClick={() => goPage(page + 1)}
                  aria-label="Вперёд"
                >
                  <Icon name="chevron-right" size={15} />
                </button>
              </div>
            )}
          </div>
        </>
      )}

      {/* Bottom-sheet превью кандидата */}
      {openCand && (
        <SSAutoSheet
          c={openCand}
          searchName={name}
          region={search.region}
          poolLeft={poolLeft}
          scored={scoredMap[openCand.hh_resume_id] ?? null}
          basis={search.basis}
          onRunScoring={startEval}
          running={isEvalRunning}
          onClose={() => setOpenId(null)}
          onTake={doTake}
          vacancies={(takeVacData?.items ?? []).map((v) => ({ id: v.id, name: v.name }))}
          takenTarget={takenLocal[openCand.hh_resume_id] ?? (openCand.taken ? 'pool' : undefined)}
          takePending={takeMutation.isPending}
        />
      )}

      {/* Тост (чанк C2) */}
      {toast && (
        <div className={`ssa-toast ssa-toast-${toast.kind}`}>
          <Icon name={toast.kind === 'ok' ? 'check' : 'alert-circle'} size={15} />
          <span>{toast.text}</span>
          {toast.action && (
            <button
              className="ssa-toast-act"
              onClick={() => {
                const to = toast.action!.to;
                setToast(null);
                navigate(to);
              }}
            >
              {toast.action.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// Строка кандидата в списке
function SSAutoRow({ c, score, onOpen }: { c: AutoCandidate; score?: number | null; onOpen: () => void }) {
  const ageStr = c.age != null ? `${c.age} ${plural(c.age, 'год', 'года', 'лет')}` : null;
  const metaParts = [ageStr, c.city].filter(Boolean) as string[];
  const jobParts = [c.last_job, c.experience ? `опыт ${c.experience}` : null].filter(Boolean) as string[];
  const displayScore = score ?? c.score;
  return (
    <div className={`ssa-row ${c.is_new ? 'is-new' : ''} ${c.taken ? 'is-taken' : ''}`} onClick={onOpen}>
      <div className="ssa-row-av">
        <SSAAnonAvatar />
        {c.is_new && <span className="ssa-row-newpip" title="Новое резюме" />}
      </div>
      <div className="ssa-row-main">
        <div className="ssa-row-title-line">
          <span className="ssa-row-title">{c.title || 'Без названия'}</span>
          {metaParts.length > 0 && <span className="ssa-row-meta">{metaParts.join(' · ')}</span>}
          {c.anonymous && (
            <span className="ssa-anon-tag" title="Анонимное резюме (скрытые поля)">
              <Icon name="lock" size={10} /> аноним
            </span>
          )}
        </div>
        {jobParts.length > 0 && <div className="ssa-row-job">{jobParts.join(' · ')}</div>}
        {/* Чипы навыков — только если skills непуст (из поиска hh они пустые) */}
        {c.skills.length > 0 && (
          <div className="ssa-row-chips">
            {c.skills.slice(0, 5).map((s, i) => (
              <span key={i} className="ssa-skill">
                {s}
              </span>
            ))}
            {c.skills.length > 5 && <span className="ssa-skill more">+{c.skills.length - 5}</span>}
          </div>
        )}
      </div>
      <div className="ssa-row-right">
        <div className="ssa-row-salary t-mono">
          {c.salary != null ? (
            `${ssaFmt(c.salary)} ₽`
          ) : (
            <span className="ssa-nosal">з/п не указана</span>
          )}
        </div>
        {c.updated_at && <div className="ssa-row-upd">обновлено {c.updated_at}</div>}
      </div>
      <div className="ssa-row-score">
        {displayScore != null ? (
          <ScoreLabel value={displayScore} size="lg" title="AI-балл" />
        ) : (
          <span className="ssa-score-empty" title="Не оценён">
            —
          </span>
        )}
      </div>
      {c.taken && (
        <span className="ssa-row-taken-flag">
          <Icon name="check" size={11} /> в пуле/воронке
        </span>
      )}
    </div>
  );
}

// Анонимный аватар (контакты закрыты на hh — силуэт всегда)
function SSAAnonAvatar({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const px = size === 'sm' ? 28 : size === 'lg' ? 44 : 38;
  return (
    <div className="ssa-anon-av" style={{ width: px, height: px }} title="Контакты закрыты">
      <Icon name="user" size={Math.round(px * 0.5)} />
    </div>
  );
}

// ====== bottom-sheet превью кандидата (СВОЯ вёрстка на классах .cand-detail) ======
function SSAutoSheet({
  c,
  searchName,
  region,
  poolLeft,
  scored,
  basis,
  onRunScoring,
  running,
  onClose,
  onTake,
  vacancies,
  takenTarget,
  takePending,
}: {
  c: AutoCandidate;
  searchName: string;
  region: string | null;
  poolLeft: number | null;
  scored: AutoScored | null;
  basis: AutoSearchBasis | null;
  onRunScoring: () => void;
  running: boolean;
  onClose: () => void;
  onTake: (c: AutoCandidate, target: 'pool' | 'vacancy', opts?: { vacancyId?: string; vacName?: string }) => void;
  vacancies: VacItem[];
  takenTarget?: 'pool' | 'vacancy';
  takePending: boolean;
}) {
  const [tab, setTab] = useState<'resume' | 'ai'>('resume');
  const [shown, setShown] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const navigate = useNavigate();

  const isTaken = !!takenTarget;

  // Приоритет: scored.score > c.score
  const displayScore = scored?.score ?? c.score;

  useEffect(() => {
    // setTimeout (не requestAnimationFrame — известная грабля throttling прототипа)
    const t = setTimeout(() => setShown(true), 16);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return (
    <>
      <div className={`ssa-sheet-backdrop ${shown ? 'is-open' : ''}`} onClick={onClose} />
      <div className={`ssa-sheet ${shown ? 'is-open' : ''}`} role="dialog" aria-label={`Резюме · ${c.title || ''}`}>
        <div className="ssa-sheet-grip" />
        <div className="cnd-funnel-wrap">
          <div className="cand-detail ssa-cd">
            {/* Тулбар — чанк C2: кнопки «Забрать контакт» / «Перевести» */}
            <div className="cd-toolbar">
              {/* «Забрать контакт» — только если ещё не взяли */}
              {!isTaken && (
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => onTake(c, 'pool')}
                  disabled={poolLeft === 0 || takePending}
                  title="Списать 1 контакт из пула hh"
                >
                  <Icon name="external-link" size={14} /> Забрать контакт
                </button>
              )}
              {/* «Перевести» — поповер с выбором пул/вакансия */}
              <div className="cd-move-wrap">
                <button
                  className={`btn btn-sm ${isTaken ? 'btn-secondary' : 'btn-success'}`}
                  onClick={() => setMoveOpen((o) => !o)}
                >
                  <Icon name="arrow-right" size={14} />
                  {isTaken ? (takenTarget === 'pool' ? 'В пуле' : 'В воронке') : 'Перевести'}
                  <Icon name="chevron-down" size={12} />
                </button>
                {moveOpen && (
                  <>
                    <div className="cd-pop-backdrop" onClick={() => setMoveOpen(false)} />
                    <div className="cd-move-pop" role="menu">
                      <div className="cd-pop-head">Куда перенести кандидата?</div>
                      <button
                        className="cd-pop-item"
                        disabled={takePending}
                        onClick={() => { onTake(c, 'pool'); setMoveOpen(false); }}
                      >
                        <span className="cd-pop-num"><Icon name="users" size={14} /></span>
                        <span className="cd-pop-label">В пул кандидатов</span>
                        {takenTarget === 'pool' && <span className="cd-pop-tag">сейчас</span>}
                      </button>
                      <div className="cd-pop-group">В воронку вакансии</div>
                      {vacancies.map((v) => (
                        <button
                          key={v.id}
                          className="cd-pop-item"
                          disabled={takePending}
                          onClick={() => { onTake(c, 'vacancy', { vacancyId: v.id, vacName: v.name }); setMoveOpen(false); }}
                        >
                          <span className="cd-pop-num"><Icon name="briefcase" size={14} /></span>
                          <span className="cd-pop-label">{v.name}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              {/* Чип «Контакт открыт» */}
              {isTaken && (
                <span className="cd-pdn-confirmed" title="Контакт списан из пула hh">
                  Контакт открыт
                  <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
                    <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
              )}
              <div style={{ flex: 1 }} />
              <button className="icon-btn" onClick={onClose} title="Закрыть (Esc)">
                <Icon name="x" size={18} />
              </button>
            </div>

            {/* Шапка — контакт закрыт, имя = title резюме */}
            <div className="cd-header">
              <div className="cd-context">
                <span className="src-pill src-hh">hh · Автопоиск «{searchName}»</span>
                {c.updated_at && <span>обновлено {c.updated_at}</span>}
                {region && (
                  <>
                    <span className="sep">·</span>
                    <span>{region}</span>
                  </>
                )}
              </div>

              <div className="cd-h-main">
                <div className="cd-h-left">
                  <div className="cd-name-row">
                    <h1 className="cd-name">{c.title || 'Без названия'}</h1>
                    {displayScore != null && <ScoreLabel value={displayScore} size="lg" title="AI-балл" />}
                    {c.is_new && (
                      <span className="ssa-newpill">
                        <span className="ssa-new-dot" /> новое
                      </span>
                    )}
                  </div>
                  <div className="cd-exp-line">
                    {[c.last_job, c.experience ? `опыт ${c.experience}` : null].filter(Boolean).join(' · ') || '—'}
                  </div>
                  <div className="cd-salary-line">
                    <span className="cd-salary t-mono">{c.salary != null ? `${ssaFmt(c.salary)} ₽` : '—'}</span>
                    <span className="cd-salary-label">{c.salary != null ? 'ожидания' : 'з/п не указана'}</span>
                  </div>
                  {/* Чипы навыков — только если непусто */}
                  {c.skills.length > 0 && (
                    <div className="cd-tags-row">
                      {c.skills.slice(0, 6).map((s, i) => (
                        <span key={i} className="skill-chip skill-chip-sm">
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Контакт-бокс: разные версии для взятого/невзятого */}
                {isTaken ? (
                  <div className="cd-contact-box ssa-cb-opened">
                    <div className="cb-row">
                      <span className="cb-label">Контакт:</span>
                      <span className="ssa-opened">
                        <Icon name="check" size={12} /> открыт — кандидат {takenTarget === 'vacancy' ? 'в воронке' : 'в пуле'}
                      </span>
                    </div>
                    {c.city && (
                      <div className="cb-row">
                        <span className="cb-label">Город:</span>
                        <span>{c.city}</span>
                      </div>
                    )}
                    <div className="ssa-cb-note">
                      Реальные контакты (телефон, e-mail) видны в карточке кандидата.{' '}
                      <button
                        className="ssa-open-card"
                        onClick={() => navigate(takenTarget === 'vacancy' ? '/vacancies' : '/candidates')}
                      >
                        Открыть карточку
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="cd-contact-box ssa-cb-locked">
                    <div className="cb-row">
                      <span className="cb-label">Контакты:</span>
                      <span className="ssa-locked">
                        <Icon name="lock" size={12} /> закрыты на hh
                      </span>
                    </div>
                    <div className="cb-row">
                      <span className="cb-label">Телефон:</span>
                      <span className="ssa-mask">+7 ••• ••• •• ••</span>
                    </div>
                    {c.city && (
                      <div className="cb-row">
                        <span className="cb-label">Город:</span>
                        <span>{c.city}</span>
                      </div>
                    )}
                    <div className="ssa-cb-note">
                      Откроется после списания 1 контакта из пула
                      {poolLeft != null && (
                        <>
                          {' '}
                          (осталось <span className="t-mono">{poolLeft}</span>)
                        </>
                      )}
                      .
                      {c.anonymous && (
                        <span className="ssa-cb-warn"> Резюме анонимное — ФИО и телефон могут не прийти.</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Табы — только Резюме и Оценка AI */}
            <div className="cc-tabs">
              <button
                className={`cc-tab ${tab === 'resume' ? 'active' : ''}`}
                onClick={() => setTab('resume')}
              >
                Резюме
              </button>
              <button className={`cc-tab ${tab === 'ai' ? 'active' : ''}`} onClick={() => setTab('ai')}>
                Оценка AI
              </button>
            </div>

            <div className="cc-content">
              {tab === 'resume' ? (
                <SSAutoResume c={c} />
              ) : (
                <SSAutoAI scored={scored} basis={basis} onRunScoring={onRunScoring} running={running} />
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// Таб Резюме — компактная сводка по ДОСТУПНЫМ полям (полное резюме — после «Забрать контакт»)
function SSAutoResume({ c }: { c: AutoCandidate }) {
  const ageStr = c.age != null ? `${c.age} ${plural(c.age, 'год', 'года', 'лет')}` : null;
  const extra: { k: string; v: string }[] = [];
  if (c.city) extra.push({ k: 'Город', v: c.city });
  if (ageStr) extra.push({ k: 'Возраст', v: ageStr });
  if (c.experience) extra.push({ k: 'Опыт', v: c.experience });
  extra.push({ k: 'Источник', v: 'hh.ru · автопоиск' });

  return (
    <div className="resume-single">
      <div className="ssa-unscored-note">
        <Icon name="sparkles" size={15} />
        Показаны открытые поля резюме. Полное резюме и контакты — после «Забрать контакт».
      </div>

      <h3 className="cc-sec-title">Последнее место</h3>
      {c.last_job || c.experience ? (
        <div className="job">
          <div className="job-when">
            {c.experience && <div className="job-period">опыт {c.experience}</div>}
          </div>
          <div className="job-main">
            <div className="job-co">{c.last_job || '—'}</div>
            {c.title && <div className="job-title">{c.title}</div>}
          </div>
        </div>
      ) : (
        <div className="job">
          <div className="job-when" />
          <div className="job-main">
            <div className="job-co">{c.title || '—'}</div>
          </div>
        </div>
      )}

      {/* Навыки — только если непусто */}
      {c.skills.length > 0 && (
        <>
          <h3 className="cc-sec-title">Навыки</h3>
          <div className="skill-row">
            {c.skills.map((s, i) => (
              <span key={i} className="skill-chip">
                {s}
              </span>
            ))}
          </div>
        </>
      )}

      <h3 className="cc-sec-title">Дополнительно</h3>
      <div className="extra-grid">
        {extra.map((e, i) => (
          <div key={i}>
            <span className="extra-k">{e.k}:</span> {e.v}
          </div>
        ))}
      </div>
    </div>
  );
}

// Таб Оценка AI — реальный разбор из прогона (чанк C)
function SSAutoAI({
  scored,
  basis,
  onRunScoring,
  running,
}: {
  scored: AutoScored | null;
  basis: AutoSearchBasis | null;
  onRunScoring: () => void;
  running: boolean;
}) {
  if (scored == null) {
    return (
      <div className="ai-single">
        <div className="ssa-ai-empty">
          <div className="ssa-ai-empty-ic">
            <Icon name="sparkles" size={26} />
          </div>
          <h3>Резюме ещё не оценено</h3>
          <p>
            Оценка относительна: Глафира сравнивает резюме с конкретной вакансией или с описанием
            идеального кандидата. Выберите основу — и она выставит балл.
          </p>
          <button
            className="btn btn-primary btn-sm"
            onClick={onRunScoring}
            disabled={running}
          >
            {running ? (
              <><span className="ssa-spin dark" /> Оцениваю…</>
            ) : (
              <><Icon name="sparkles" size={14} /> Оценить относительно…</>
            )}
          </button>
        </div>
      </div>
    );
  }

  // Реальный разбор из прогона
  const totalPts = scored.requirements_match?.reduce((s, m) => s + m.points, 0) ?? 0;
  const totalMax = scored.requirements_match?.reduce((s, m) => s + m.weight, 0) ?? 0;

  return (
    <div className="ai-single">
      {/* Вердикт */}
      <div className="filo-card filo-card-compact">
        <div className="filo-head">
          <div className="filo-ai-mark filo-glafira">
            <span className="glafira-emoji">👩🏻</span>
          </div>
          <div className="filo-head-body">
            <div className="filo-title-row">
              <span className="filo-title">Оценка от Глафиры</span>
            </div>
            {scored.verdict && <div className="filo-sub">{scored.verdict}</div>}
            {basis && (
              <div className="filo-screening">
                Сравнила резюме{' '}
                {basis.kind === 'vacancy' ? (
                  <>с выбранной вакансией</>
                ) : (
                  <>с запросом <b>«{basis.prompt}»</b></>
                )}
                . Совпадение — {scored.score}%.
                {scored.summary && <> {scored.summary}</>}
              </div>
            )}
          </div>
          <ScoreLabel value={scored.score} size="xl" title="AI-балл" />
        </div>
      </div>

      <h3 className="cc-sec-title">Анализ AI</h3>

      {/* Сильные стороны */}
      {scored.strengths?.length > 0 && (
        <div className="msg ai-msg ai-msg-good" style={{ maxWidth: '100%' }}>
          <div className="ai-name ai-name-good">
            <span className="cc-sec-emoji">✅</span> Сильные стороны
          </div>
          <ul className="ai-msg-list">
            {scored.strengths.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}

      {/* Слабые стороны */}
      {scored.risks?.length > 0 && (
        <div className="msg ai-msg ai-msg-warn" style={{ maxWidth: '100%', marginTop: 8 }}>
          <div className="ai-name ai-name-warn">
            <span className="cc-sec-emoji">⚠️</span> Слабые стороны
          </div>
          <ul className="ai-msg-list">
            {scored.risks.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      {/* Вопросы */}
      {scored.questions?.length > 0 && (
        <div className="msg ai-msg ai-msg-q" style={{ maxWidth: '100%', marginTop: 8 }}>
          <div className="ai-name ai-name-q">
            <span className="cc-sec-emoji">💬</span> Вопросы для первого контакта
          </div>
          <ol className="ai-msg-list ai-msg-list-num">
            {scored.questions.map((q, i) => <li key={i}>{q}</li>)}
          </ol>
        </div>
      )}

      {/* Разбор по критериям */}
      {scored.requirements_match?.length > 0 && (
        <>
          <h3 className="cc-sec-title">
            Разбор по критериям{' '}
            <span className="crit-total">
              <span className="t-mono">{totalPts}</span> / <span className="t-mono">{totalMax}</span>
            </span>
          </h3>
          <div className="crit-list">
            {scored.requirements_match.map((match, i) => {
              const pct = match.weight ? Math.round((match.points / match.weight) * 100) : 0;
              const color = match.weight === 0 ? 'gray' : pct >= 80 ? 'green' : pct >= 40 ? 'yellow' : 'red';
              return (
                <div key={i} className={`crit-row crit-${color}`}>
                  <div className="crit-head">
                    <span className="crit-label">{match.criterion}</span>
                    <span className="crit-pts t-mono">
                      {match.points}<span className="crit-pts-max"> / {match.weight || '—'}</span>
                    </span>
                  </div>
                  <div className="crit-bar"><span style={{ width: `${pct}%` }} /></div>
                  {match.comment && <div className="crit-comment">{match.comment}</div>}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Прогноз */}
      {scored.forecast && (
        <p className="ssa-ai-forecast">{scored.forecast}</p>
      )}
    </div>
  );
}
