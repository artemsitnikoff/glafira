// Ветка В умного подбора — «Автоподбор» (сохранённые автопоиски hh.ru).
// ЧАНК A: шапка ветки + список автопоисков из реального бека (/smart/auto/*).
// ЧАНК B: список кандидатов выбранного автопоиска (пагинация/сегмент/сортировка)
//   + нижняя bottom-sheet превью-карточка (своя вёрстка на классах .cand-detail).
// Оценка AI и «забрать контакт» — wiring в чанке C (кнопки здесь DISABLED).
import { useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { ScoreLabel } from '@/components/ui/ScoreLabel';
import {
  useAutoAccess,
  useAutoCandidates,
  useAutoSearches,
  useSyncAutoSearches,
  type AutoCandidate,
  type AutoSearch,
} from '@/api/hooks/useSmartSearch';
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

// ====== Вид: список автопоисков ======
function SSAutoSearchesView({ searches, onOpen }: {
  searches: AutoSearch[];
  onOpen: (id: string) => void;
}) {
  const totalNew = searches.reduce((s, x) => s + (x.new_count ?? 0), 0);
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
      </div>

      <div className="ssa-search-list">
        {searches.map((s) => {
          const name = stripQuotes(s.name);
          const bl = basisLabel(s.basis);
          const newCount = s.new_count ?? 0;
          return (
            <div key={s.id} className="ssa-search-card">
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
                  {/* Тумблер подписки — ОТОБРАЖЕНИЕ состояния (запись — в следующем чанке) */}
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
                  {/* Тумблер авто-оценки — ОТОБРАЖЕНИЕ состояния (запись — в следующем чанке) */}
                  <span className={`ss-switch ${s.auto_eval ? 'on' : ''}`} aria-label="Авто-оценка" />
                </div>
                {s.basis && bl && (
                  <div className="ssa-basis" title="Основа оценки">
                    <Icon name={s.basis.kind === 'vacancy' ? 'briefcase' : 'message-circle'} size={12} />
                    <span className="ssa-basis-text">
                      <span className="ssa-basis-k">{s.basis.kind === 'vacancy' ? 'против вакансии' : 'по промту'}</span>
                      <span className="ssa-basis-v">{bl}</span>
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
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

// ====== Вид: кандидаты выбранного автопоиска (чанк B) ======
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

  // Сортировка по AI-баллу недоступна, пока поток не оценён (score у всех null) — в этом
  // чанке оценки нет, поэтому опция всегда disabled (включится в чанке C).
  const sortScoreDisabled = true;

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

  return (
    <div className="ssa-cands" ref={rowsRef}>
      {/* Хлебные крошки */}
      <div className="ssa-cands-head">
        <button className="ssa-crumb" onClick={onBackToList}>
          <Icon name="chevron-left" size={13} /> Автопоиски
        </button>
        <span className="ssa-crumb-sep">/</span>
        <span className="ssa-crumb-cur">«{name}»</span>
        {search.region && <span className="ssa-crumb-region">{search.region}</span>}
        <div style={{ flex: 1 }} />
        {search.basis && bl && (
          <span className="ssa-basis ssa-basis-inline" title="Основа оценки">
            <Icon name={search.basis.kind === 'vacancy' ? 'briefcase' : 'message-circle'} size={12} />
            <span className="ssa-basis-text">
              <span className="ssa-basis-k">
                {search.basis.kind === 'vacancy' ? 'оценка против вакансии' : 'оценка по промту'}
              </span>
              <span className="ssa-basis-v">{bl}</span>
            </span>
          </span>
        )}
      </div>

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

        {/* Авто-оценка новых — ОТОБРАЖЕНИЕ состояния (wiring в чанке C) */}
        <div className="ssa-ae-inline">
          <span className="ssa-ae-inline-label">Авто-оценка новых</span>
          <span
            className={`ss-switch ${search.auto_eval ? 'on' : ''}`}
            aria-label="Авто-оценка"
          />
        </div>

        {/* Оценка топ-N — DISABLED в этом чанке (wiring оценки — чанк C) */}
        <button
          className="btn btn-primary btn-sm ssa-eval-btn"
          disabled
          title="Оценка подключается"
        >
          <Icon name="sparkles" size={14} /> Оценить {ssaFmt(segment === 'new' ? newCount : totalAll)}
        </button>
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
              <SSAutoRow key={c.hh_resume_id} c={c} onOpen={() => setOpenId(c.hh_resume_id)} />
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
          onClose={() => setOpenId(null)}
        />
      )}
    </div>
  );
}

// Строка кандидата в списке
function SSAutoRow({ c, onOpen }: { c: AutoCandidate; onOpen: () => void }) {
  const ageStr = c.age != null ? `${c.age} ${plural(c.age, 'год', 'года', 'лет')}` : null;
  const metaParts = [ageStr, c.city].filter(Boolean) as string[];
  const jobParts = [c.last_job, c.experience ? `опыт ${c.experience}` : null].filter(Boolean) as string[];
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
        {c.score != null ? (
          <ScoreLabel value={c.score} size="lg" title="AI-балл" />
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
  onClose,
}: {
  c: AutoCandidate;
  searchName: string;
  region: string | null;
  poolLeft: number | null;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<'resume' | 'ai'>('resume');
  const [shown, setShown] = useState(false);

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
            {/* Тулбар — действия Автоподбора DISABLED (wiring в чанке C) + рабочий крестик */}
            <div className="cd-toolbar">
              <button className="btn btn-primary btn-sm" disabled title="Подключаем">
                <Icon name="external-link" size={14} /> Забрать контакт
              </button>
              <button className="btn btn-success btn-sm" disabled title="Подключаем">
                <Icon name="arrow-right" size={14} /> Перевести <Icon name="chevron-down" size={12} />
              </button>
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
                    {c.score != null && <ScoreLabel value={c.score} size="lg" title="AI-балл" />}
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
              {tab === 'resume' ? <SSAutoResume c={c} /> : <SSAutoAI c={c} />}
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

// Таб Оценка AI — пустое состояние, пока резюме не оценено (оценка — чанк C)
function SSAutoAI({ c }: { c: AutoCandidate }) {
  if (c.score == null) {
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
          <button className="btn btn-primary btn-sm" disabled title="Подключаем">
            <Icon name="sparkles" size={14} /> Оценить относительно…
          </button>
        </div>
      </div>
    );
  }
  // score есть → минимальный вердикт (подробный разбор strengths/risks/criteria — из прогона, чанк C)
  return (
    <div className="ai-single">
      <div className="ssa-ai-scored">
        <ScoreLabel value={c.score} size="xl" title="AI-балл" />
        <div className="ssa-ai-scored-text">
          <h3>AI-балл: {c.score}</h3>
          <p>Подробный разбор (сильные/слабые стороны, критерии) появится после оценки.</p>
        </div>
      </div>
    </div>
  );
}
